from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from weasyprint import HTML
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from . import forms
from .models import Encargado

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
        
