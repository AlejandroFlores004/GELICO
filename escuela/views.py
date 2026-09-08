from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from weasyprint import HTML
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from . import forms
from .models import Encargado, Escuela

def _encargados_filtrados(request):
    # exactamente el cuerpo que ya tenías en _filtrar_encargados, PERO sin el Paginator
    filtro_form = forms.FiltrarEncargadosForm(request.GET or None)

    encargados_list = Encargado.objects.select_related(
        'escuela', 'escuela__distrito'
    ).prefetch_related('telefonos').order_by('escuela__nombre_corto', '-estado', 'apellido')

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
        formset = forms.TelefonoFormSet(request.POST, instance=instance, prefix='telefonos')
        if form.is_valid() and formset.is_valid():
            es_nuevo = instance is None
            encargado = form.save() #Guarda (crea o actualiza) en la bd
            formset.instance = encargado #Necesario cuando instance era None (creación)
            formset.save()
            if es_nuevo and encargado.estado:
                # Al crear un encargado nuevo (activo por defecto), desactiva
                # a los demás encargados activos de la misma escuela.
                Encargado.objects.filter(
                    escuela=encargado.escuela, estado=True
                ).exclude(pk=encargado.pk).update(estado=False)
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
        formset = forms.TelefonoFormSet(instance=instance, prefix='telefonos')

    return render(
         request,
       'partials/encargado/_encargado_form_modal.html',
         {'form': form, 'formset': formset, 'instance': instance}
     )

# Cambiar Encargado: Crea un nuevo encargado y desactiva el anterior.

def encargado_cambiar(request, pk):
    activo = get_object_or_404(Encargado, pk=pk)
    nuevo_instance = Encargado(escuela=activo.escuela)
    
    if request.method == 'POST':
        form = forms.EncargadoForm(request.POST, instance=nuevo_instance, prefix='encargado')
        #Siempre se bloquea la escuela
        form.fields['escuela'].disabled = True
        formset = forms.TelefonoFormSet(request.POST, instance=nuevo_instance, prefix='telefonos')

        if form.is_valid() and formset.is_valid():
            encargado = form.save() #Guarda al nuevo encargado
            formset.instance = encargado
            formset.save()
            activo.estado = False #El anterior encargado pasa a inactivo
            activo.save() # El anterior pasa a inactivo
            _, encargados = _filtrar_encargados(request)
            return render(request, 'partials/encargado/_encargado_form_success.html',
                          {'encargados': encargados}
            )
    else:
            form = forms.EncargadoForm(instance=nuevo_instance, prefix='encargado')
            form.fields['escuela'].disabled = True
            formset = forms.TelefonoFormSet(instance=nuevo_instance, prefix='telefonos')

    return render(
            request,
            'partials/encargado/_encargado_form_modal.html',
            {'form': form, 'formset': formset, 'instance': None, 'cambiar': True, 'activo': activo}
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


# ===================== Escuelas =====================

def _escuelas_filtradas(request):
    filtro_form = forms.FiltrarEscuelasForm(request.GET or None)

    escuelas_list = Escuela.objects.select_related('distrito').order_by('codigo')

    if filtro_form.is_valid():
        distrito = filtro_form.cleaned_data.get('distrito')
        estado = filtro_form.cleaned_data.get('estado')
        texto = filtro_form.cleaned_data.get('texto')

        if distrito:
            escuelas_list = escuelas_list.filter(distrito=distrito)
        if estado:
            escuelas_list = escuelas_list.filter(estado=(estado == '1'))
        if texto:
            escuelas_list = escuelas_list.filter(
                Q(codigo__icontains=texto) |
                Q(nombre__icontains=texto) |
                Q(nombre_corto__icontains=texto)
            )

    return filtro_form, escuelas_list


def _filtrar_escuelas(request):
    filtro_form, escuelas_list = _escuelas_filtradas(request)

    paginator = Paginator(escuelas_list, 20)
    escuelas = paginator.get_page(request.GET.get('page'))

    return filtro_form, escuelas


def escuela_imprimir(request):
    _, escuelas = _escuelas_filtradas(request)

    html_string = render_to_string(
        'partials/escuela/_escuela_reporte_pdf.html',
        {'escuelas': escuelas, 'fecha_generacion': timezone.localdate()}
    )
    pdf = HTML(string=html_string, base_url=request.build_absolute_uri('/')).write_pdf()

    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="Escuelas.pdf"'
    return response


def home_escuelas(request):
    breadcrumbs = [
        {'name': 'Inicio', 'url': reverse('home')},
        {'name': 'Escuelas', 'url': reverse('home_escuelas')},
    ]

    filtro_form, escuelas = _filtrar_escuelas(request)

    return render(
        request, 'escuela/escuelaHome.html',
        {
            'breadcrumbs': breadcrumbs,
            'escuelas': escuelas,
            'filtro_form': filtro_form,
            'form_media': filtro_form.media,
        }
    )


def buscar_escuelas(request):
    _, escuelas = _filtrar_escuelas(request)

    return render(
        request,
        'partials/escuela/_listado_escuelas.html',
        {'escuelas': escuelas}
    )


#Sirve para crear y Editar
def escuela_form(request, pk=None):
    instance = get_object_or_404(Escuela, pk=pk) if pk else None
    if request.method == 'POST':
        form = forms.EscuelaForm(request.POST, instance=instance, prefix='escuela')
        if form.is_valid():
            form.save()
            _, escuelas = _filtrar_escuelas(request)
            return render(
                request,
                'partials/escuela/_escuela_form_success.html',
                {'escuelas': escuelas}
            )
    else:
        form = forms.EscuelaForm(instance=instance, prefix='escuela')

    return render(
        request,
        'partials/escuela/_escuela_form_modal.html',
        {'form': form, 'instance': instance}
    )


def escuela_toggle_estado(request, pk):
    escuela = get_object_or_404(Escuela, pk=pk)

    if request.method == 'POST':
        escuela.estado = not escuela.estado
        escuela.save()

        _, escuelas = _filtrar_escuelas(request)

        return render(
            request,
            'partials/escuela/_escuela_form_success.html',
            {'escuelas': escuelas}
        )

        #Modal de confirmación para cambiar el estado de una escuela
    return render(
        request,
        'partials/escuela/_escuela_toggle_confirm.html',
        {'escuela': escuela}
    )
