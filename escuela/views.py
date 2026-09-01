from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.dateparse import parse_date
from weasyprint import HTML
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from . import forms
from .models import Encargado, CDE

def _encargados_filtrados(request):
    # exactamente el cuerpo que ya tenías en _filtrar_encargados, PERO sin el Paginator
    filtro_form = forms.FiltrarEncargadosForm(request.GET or None)

    encargados_list = Encargado.objects.select_related(
        'escuela', 'escuela__distrito'
    ).order_by('escuela__nombre_corto', '-estado', 'apellido')

    if filtro_form.is_valid():
        escuela = filtro_form.cleaned_data.get('escuela')
        estado = filtro_form.cleaned_data.get('estado')
        texto = filtro_form.cleaned_data.get('texto')
        distrito = filtro_form.cleaned_data.get('distrito')

        if distrito:
            encargados_list = encargados_list.filter(escuela__distrito=distrito)
        if escuela:
            encargados_list = encargados_list.filter(escuela=escuela)
        if estado:
            encargados_list = encargados_list.filter(estado=(estado == '1'))
        if texto:
            encargados_list = encargados_list.filter(
                Q(nombre__icontains=texto) |
                Q(apellido__icontains=texto) |
                Q(email__icontains=texto)
            )

    return filtro_form, encargados_list


def _filtrar_encargados(request):
    # ahora esta SOLO agrega la paginación, reutilizando la de arriba
    filtro_form, encargados_list = _encargados_filtrados(request)

    paginator = Paginator(encargados_list, 20)
    encargados = paginator.get_page(request.GET.get('page'))

    return filtro_form, encargados

def encargado_imprimir(request):
    _, encargados = _encargados_filtrados(request)

    html_string = render_to_string(
        'partials/encargado/_encargado_reporte_pdf.html',
        {'encargados': encargados, 'fecha_generacion': timezone.localdate()}
    )
    pdf = HTML(string=html_string, base_url=request.build_absolute_uri('/')).write_pdf()

    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="Encargados.pdf"'
    return response


def home_encargados(request):
    breadcrumbs = [
        {'name': 'Inicio', 'url': reverse('home')},
        {'name': 'Encargados', 'url': reverse('home_encargados')},
    ]
    
    filtro_form, encargados = _filtrar_encargados(request)
    
    return render(
        request, 'encargado/encargadoHome.html',
        {
            'breadcrumbs': breadcrumbs,
            'encargados': encargados,
            'filtro_form': filtro_form,
            'form_media': filtro_form.media, ##JS,CSS que usa el Select2
        }
    )

#Se utilizacuando se oprime buscar

def buscar_encargados(request):
    _, encargados = _filtrar_encargados(request)
    
    return render(
        request,
        'partials/encargado/_listado_encargados.html',
        {'encargados': encargados}
    )
    
    
#Sirve para crear y Editar
def encargado_form(request, pk=None):
    #Si pk es None, se crea un nuevo encargado, si no, se edita el encargado 
    # con ese pk.
    instance = get_object_or_404(Encargado, pk=pk) if pk else None
    if request.method == 'POST':
        form = forms.EncargadoForm(request.POST, instance=instance, prefix='encargado')
        if form.is_valid():
            form.save() #Guarda (crea o actualiza) en la bd
            _, encargados = _filtrar_encargados(request)
            return render(
                request,
                'partials/encargado/_encargado_form_success.html',
                {'encargados': encargados}
            )
    else:
        #Primera vez que se carga el formulario, se crea el formulario 
        # con la instancia del encargado
        form = forms.EncargadoForm(instance=instance, prefix='encargado')
        
    return render(
         request,
       'partials/encargado/_encargado_form_modal.html',
         {'form': form, 'instance': instance}
     )

# Cambiar Encargado: Crea un nuevo encargado y desactiva el anterior.

def encargado_cambiar(request, pk):
    activo = get_object_or_404(Encargado, pk=pk)
    nuevo_instance = Encargado(escuela=activo.escuela)
    
    if request.method == 'POST':
        form = forms.EncargadoForm(request.POST, instance=nuevo_instance, prefix='encargado')
        #Siempre se bloquea la escuela
        form.fields['escuela'].disabled = True
        
        if form.is_valid():
            form.save() #Guarda al nuevo encargado
            activo.estado = False #El anterior encargado pasa a inactivo
            activo.save() # El anterior pasa a inactivo
            _, encargados = _filtrar_encargados(request)
            return render(request, 'partials/encargado/_encargado_form_success.html',
                          {'encargados': encargados}
            )
    else:
            form = forms.EncargadoForm(instance=nuevo_instance, prefix='encargado')
            form.fields['escuela'].disabled = True
            
    return render(
            request, 
            'partials/encargado/_encargado_form_modal.html',
            {'form': form, 'instance': None, 'cambiar': True, 'activo': activo}
        )
    
# Cambiar estado de un encargado, activo/inactivo
def encargado_toggle_estado(request, pk):
    encargado = get_object_or_404(Encargado, pk=pk)
    
    if request.method == 'POST':
        encargado.estado = not encargado.estado
        encargado.save()
        
        if encargado.estado:
            Encargado.objects.filter(
                escuela=encargado.escuela, estado=True
            ).exclude(pk=encargado.pk).update(estado=False)
            
        _, encargados = _filtrar_encargados(request)
        
        return render( request,
                      'partials/encargado/_encargado_form_success.html',
                      {'encargados': encargados}
        )
        
        #Modal de confirmación para cambiar el estado de un encargado
    return render( request,
                      'partials/encargado/_encargado_toggle_confirm.html',
                      {'encargado': encargado}
        )


def _cdes_filtrados(request):
    filtro_form = forms.CDEFilterForm(request.GET or None)

    cdes = CDE.objects.select_related('escuela', 'escuela__distrito').order_by('FechaInicio', 'escuela__nombre_corto')

    if filtro_form.is_valid():
        escuela = filtro_form.cleaned_data.get('escuela')
        distrito = filtro_form.cleaned_data.get('distrito')
        search = (filtro_form.cleaned_data.get('q') or '').strip()
        fecha_inicio = filtro_form.cleaned_data.get('fecha_inicio')
        fecha_fin = filtro_form.cleaned_data.get('fecha_fin')

        if distrito:
            cdes = cdes.filter(escuela__distrito=distrito)
        if escuela:
            cdes = cdes.filter(escuela=escuela)
        if search:
            cdes = cdes.filter(
                Q(escuela__nombre__icontains=search) |
                Q(escuela__codigo__icontains=search) |
                Q(escuela__nombre_corto__icontains=search) |
                Q(escuela__distrito__nombre__icontains=search)
            )
        if fecha_inicio:
            cdes = cdes.filter(FechaInicio__gte=fecha_inicio)
        if fecha_fin:
            cdes = cdes.filter(FechaFin__lte=fecha_fin)
    else:
        search = (request.GET.get('q', '') or '').strip()
        fecha_inicio = request.GET.get('fecha_inicio', '').strip()
        fecha_fin = request.GET.get('fecha_fin', '').strip()

    return filtro_form, search, fecha_inicio, fecha_fin, cdes


def _filtrar_cdes(request):
    filtro_form, search, fecha_inicio, fecha_fin, cdes_list = _cdes_filtrados(request)
    paginator = Paginator(cdes_list, 20)
    cdes = paginator.get_page(request.GET.get('page'))
    return filtro_form, search, fecha_inicio, fecha_fin, cdes


def cdeHomeView(request):
    filtro_form, search, fecha_inicio, fecha_fin, cdes = _filtrar_cdes(request)

    return render(
        request,
        'cde/cdeHome.html',
        {
            'cdes': cdes,
            'search': search,
            'fecha_inicio': fecha_inicio,
            'fecha_fin': fecha_fin,
            'filtro_form': filtro_form,
            'form_media': filtro_form.media,
        },
    )


def buscar_cdes(request):
    _, _, _, _, cdes = _filtrar_cdes(request)

    return render(
        request,
        'partials/cde/tabla.html',
        {'cdes': cdes},
    )


def cde_form(request, pk=None):
    instance = get_object_or_404(CDE, pk=pk) if pk else None

    if request.method == 'POST':
        form = forms.CDEForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            _, _, _, _, cdes = _filtrar_cdes(request)
            return render(
                request,
                'partials/cde/modal_form_success.html',
                {'cdes': cdes},
            )
    else:
        form = forms.CDEForm(instance=instance)

    return render(
        request,
        'partials/cde/modal_form.html',
        {'form': form, 'instance': instance},
    )


def cde_eliminar(request, pk):
    instance = get_object_or_404(CDE, pk=pk)

    if request.method == 'POST':
        instance.delete()
        _, _, _, _, cdes = _filtrar_cdes(request)
        return render(
            request,
            'partials/cde/modal_form_success.html',
            {'cdes': cdes},
        )

    return render(
        request,
        'partials/cde/modal_delete.html',
        {'instance': instance},
    )


def cde_imprimir(request):
    _, _, _, _, cdes = _cdes_filtrados(request)
    html_string = render_to_string(
        'partials/cde/reporte_pdf.html',
        {'cdes': cdes},
    )
    pdf = HTML(string=html_string, base_url=request.build_absolute_uri('/')).write_pdf()

    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="cdes.pdf"'
    return response

