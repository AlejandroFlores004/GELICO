from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from . import forms
from escuela.models import Escuela, Encargado
from .models import Asignacion
from .models import Asignacion

# Create your views here.


#Liquidaciones views


#Liquidaciones views
def home_liquidaciones(request):


    seleccionarEscuelas = forms.SeleccionarEscuelaForm(request.GET or None)
    seleccionarBono = forms.SeleccionarBonoForm()

    breadcrumbs = [
        {'name': 'Inicio', 'url': reverse('home')},
        {'name': 'Liquidaciones', 'url': reverse('home_liquidaciones')},
    ]

    return render(
        request, 
        'liquidacion/liquidacionHome.html', 
        {
            'breadcrumbs': breadcrumbs,
            'seleccionarEscuelas': seleccionarEscuelas,
            'seleccionarBono': seleccionarBono,
            'form_media': seleccionarEscuelas.media + seleccionarBono.media,
        }
    )


def buscar_escuela(request):
    seleccionarEscuelas = forms.SeleccionarEscuelaForm(request.GET or None)

    if seleccionarEscuelas.is_valid():
        escuela = seleccionarEscuelas.cleaned_data['escuela']
        encargado = Encargado.objects.filter(escuela=escuela).first()
        seleccionarBono = forms.SeleccionarBonoForm(escuela=escuela)
        return render(
            request,
            'partials/liquidacion/_escuela_info_result.html',
            {'escuela': escuela, 'encargado': encargado}
        )

    return render(request, 'partials/liquidacion/_escuela_info.html', {})

#Asignaciones views
def _filtrar_asignaciones(request):
    filtro_form = forms.FiltrarAsignacionesForm(request.GET or None)

    asignaciones_list = Asignacion.objects.select_related(
        'escuela', 'escuela__distrito', 'bono'
    ).order_by('-fecha')

    if filtro_form.is_valid():
        distrito = filtro_form.cleaned_data.get('distrito')
        escuela = filtro_form.cleaned_data.get('escuela')
        bono = filtro_form.cleaned_data.get('bono')
        fecha = filtro_form.cleaned_data.get('fecha')


        if distrito:
            asignaciones_list = asignaciones_list.filter(escuela__distrito=distrito)
        if escuela:
            asignaciones_list = asignaciones_list.filter(escuela=escuela)
        if bono:
            asignaciones_list = asignaciones_list.filter(bono=bono)
        if fecha:
            asignaciones_list = asignaciones_list.filter(fecha=fecha)

    paginator = Paginator(asignaciones_list, 20)
    asignaciones = paginator.get_page(request.GET.get('page'))

    return filtro_form, asignaciones


def home_asignaciones(request):
    breadcrumbs = [
        {'name': 'Inicio', 'url': reverse('home')},
        {'name': 'Asignaciones', 'url': reverse('home_asignaciones')},
    ]

    filtro_form, asignaciones = _filtrar_asignaciones(request)

    return render(
        request,
        'asignacion/asignacionHome.html',
        {
            'breadcrumbs': breadcrumbs,
            'asignaciones': asignaciones,
            'filtro_form': filtro_form,
            'form_media': filtro_form.media,
        }
    )


def buscar_asignaciones(request):
    _, asignaciones = _filtrar_asignaciones(request)

    return render(
        request,
        'partials/asignacion/_listado_asignaciones.html',
        {'asignaciones': asignaciones}
    )


def asignacion_form(request, pk=None):
    instance = get_object_or_404(Asignacion, pk=pk) if pk else None

    if request.method == 'POST':
        form = forms.AsignacionForm(request.POST, instance=instance, prefix='asignacion')
        if form.is_valid():
            form.save()
            _, asignaciones = _filtrar_asignaciones(request)
            return render(
                request,
                'partials/asignacion/_asignacion_form_success.html',
                {'asignaciones': asignaciones}
            )
    else:
        form = forms.AsignacionForm(instance=instance, prefix='asignacion')

    return render(
        request,
        'partials/asignacion/_asignacion_form_modal.html',
        {'form': form, 'instance': instance}
    )


def asignacion_eliminar(request, pk):
    instance = get_object_or_404(Asignacion, pk=pk)

    if request.method == 'POST':
        instance.delete()
        _, asignaciones = _filtrar_asignaciones(request)
        return render(
            request,
            'partials/liquidacion/_escuela_info_result.html',
            {'escuela': escuela, 'encargado': encargado, 'seleccionarBono': seleccionarBono}
        )
    return render(request, 'partials/liquidacion/_escuela_info.html', {})

#Asignaciones views
def _filtrar_asignaciones(request):
    filtro_form = forms.FiltrarAsignacionesForm(request.GET or None)

    asignaciones_list = Asignacion.objects.select_related(
        'escuela', 'escuela__distrito', 'bono'
    ).order_by('-fecha')

    if filtro_form.is_valid():
        distrito = filtro_form.cleaned_data.get('distrito')
        escuela = filtro_form.cleaned_data.get('escuela')
        bono = filtro_form.cleaned_data.get('bono')
        fecha = filtro_form.cleaned_data.get('fecha')


        if distrito:
            asignaciones_list = asignaciones_list.filter(escuela__distrito=distrito)
        if escuela:
            asignaciones_list = asignaciones_list.filter(escuela=escuela)
        if bono:
            asignaciones_list = asignaciones_list.filter(bono=bono)
        if fecha:
            asignaciones_list = asignaciones_list.filter(fecha=fecha)

    paginator = Paginator(asignaciones_list, 20)
    asignaciones = paginator.get_page(request.GET.get('page'))

    return filtro_form, asignaciones


def home_asignaciones(request):
    breadcrumbs = [
        {'name': 'Inicio', 'url': reverse('home')},
        {'name': 'Asignaciones', 'url': reverse('home_asignaciones')},
    ]

    filtro_form, asignaciones = _filtrar_asignaciones(request)

    return render(
        request,
        'asignacion/asignacionHome.html',
        {
            'breadcrumbs': breadcrumbs,
            'asignaciones': asignaciones,
            'filtro_form': filtro_form,
            'form_media': filtro_form.media,
        }
    )


def buscar_asignaciones(request):
    _, asignaciones = _filtrar_asignaciones(request)

    return render(
        request,
        'partials/asignacion/_listado_asignaciones.html',
        {'asignaciones': asignaciones}
    )


def asignacion_form(request, pk=None):
    instance = get_object_or_404(Asignacion, pk=pk) if pk else None

    if request.method == 'POST':
        form = forms.AsignacionForm(request.POST, instance=instance, prefix='asignacion')
        if form.is_valid():
            form.save()
            _, asignaciones = _filtrar_asignaciones(request)
            return render(
                request,
                'partials/asignacion/_asignacion_form_success.html',
                {'asignaciones': asignaciones}
            )
    else:
        form = forms.AsignacionForm(instance=instance, prefix='asignacion')

    return render(
        request,
        'partials/asignacion/_asignacion_form_modal.html',
        {'form': form, 'instance': instance}
    )


def asignacion_eliminar(request, pk):
    instance = get_object_or_404(Asignacion, pk=pk)

    if request.method == 'POST':
        instance.delete()
        _, asignaciones = _filtrar_asignaciones(request)
        return render(
            request,
            'partials/liquidacion/_escuela_info_result.html',
            {'escuela': escuela, 'encargado': encargado, 'seleccionarBono': seleccionarBono}
        )
    return render(request, 'partials/liquidacion/_escuela_info.html', {})