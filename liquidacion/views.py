from decimal import Decimal

from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from weasyprint import HTML
from . import forms
from escuela.models import Escuela, Encargado
from .models import Asignacion, Transferencia

# Create your views here.

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
            {'escuela': escuela, 'encargado': encargado, 'seleccionarBono': seleccionarBono}
        )
    return render(request, 'partials/liquidacion/_escuela_info.html', {})

#Asignaciones views
def _asignaciones_filtradas(request):
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

    return filtro_form, asignaciones_list


def _filtrar_asignaciones(request):
    filtro_form, asignaciones_list = _asignaciones_filtradas(request)

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
            'partials/asignacion/_asignacion_form_success.html',
            {'asignaciones': asignaciones}
        )

    return render(
        request,
        'partials/asignacion/_asignacion_delete_modal.html',
        {'instance': instance}
    )


def asignacion_imprimir(request):
    _, asignaciones = _asignaciones_filtradas(request)

    total = sum((asignacion.valor for asignacion in asignaciones), Decimal('0'))

    html_string = render_to_string(
        'partials/asignacion/_asignacion_reporte_pdf.html',
        {
            'asignaciones': asignaciones,
            'total': total,
            'fecha_generacion': timezone.localdate(),
        }
    )

    pdf = HTML(string=html_string, base_url=request.build_absolute_uri('/')).write_pdf()

    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="asignaciones.pdf"'
    return response

#Transferencia views
def _transferencias_filtradas(request):
    filtro_form = forms.FiltrarTransferenciasForm(request.GET or None)

    transferencias_list = Transferencia.objects.select_related(
        'asignacion', 'asignacion__escuela', 'asignacion__escuela__distrito', 'asignacion__bono'
    ).order_by('-fecha')

    if filtro_form.is_valid():
        distrito = filtro_form.cleaned_data.get('distrito')
        escuela = filtro_form.cleaned_data.get('escuela')
        bono = filtro_form.cleaned_data.get('bono')
        fecha = filtro_form.cleaned_data.get('fecha')

        if distrito:
            transferencias_list = transferencias_list.filter(asignacion__escuela__distrito=distrito)
        if escuela:
            transferencias_list = transferencias_list.filter(asignacion__escuela=escuela)
        if bono:
            transferencias_list = transferencias_list.filter(asignacion__bono=bono)
        if fecha:
            transferencias_list = transferencias_list.filter(fecha=fecha)

    return filtro_form, transferencias_list


def _filtrar_transferencias(request):
    filtro_form, transferencias_list = _transferencias_filtradas(request)

    paginator = Paginator(transferencias_list, 20)
    transferencias = paginator.get_page(request.GET.get('page'))

    return filtro_form, transferencias


def home_transferencias(request):
    breadcrumbs = [
        {'name': 'Inicio', 'url': reverse('home')},
        {'name': 'Transferencias', 'url': reverse('home_transferencias')},
    ]

    filtro_form, transferencias = _filtrar_transferencias(request)

    return render(
        request,
        'transferencia/transferenciaHome.html',
        {
            'breadcrumbs': breadcrumbs,
            'transferencias': transferencias,
            'filtro_form': filtro_form,
            'form_media': filtro_form.media,
        }
    )


def buscar_transferencias(request):
    _, transferencias = _filtrar_transferencias(request)

    return render(
        request,
        'partials/transferencia/_listado_transferencias.html',
        {'transferencias': transferencias}
    )


def transferencia_asignaciones_por_escuela(request):
    escuela_id = request.GET.get('transferencia-escuela')
    escuela = Escuela.objects.filter(pk=escuela_id).first() if escuela_id else None

    form = forms.TransferenciaForm(escuela=escuela, prefix='transferencia')

    return render(
        request,
        'partials/transferencia/_transferencia_asignacion_select.html',
        {'form': form}
    )


def transferencia_form(request, pk=None):
    instance = get_object_or_404(Transferencia, pk=pk) if pk else None

    if request.method == 'POST':
        form = forms.TransferenciaForm(request.POST, instance=instance, prefix='transferencia')
        if form.is_valid():
            form.save()
            _, transferencias = _filtrar_transferencias(request)
            return render(
                request,
                'partials/transferencia/_transferencia_form_success.html',
                {'transferencias': transferencias}
            )
    else:
        form = forms.TransferenciaForm(instance=instance, prefix='transferencia')

    return render(
        request,
        'partials/transferencia/_transferencia_form_modal.html',
        {'form': form, 'instance': instance}
    )


def transferencia_eliminar(request, pk):
    instance = get_object_or_404(Transferencia, pk=pk)

    if request.method == 'POST':
        instance.delete()
        _, transferencias = _filtrar_transferencias(request)
        return render(
            request,
            'partials/transferencia/_transferencia_form_success.html',
            {'transferencias': transferencias}
        )

    return render(
        request,
        'partials/transferencia/_transferencia_delete_modal.html',
        {'instance': instance}
    )