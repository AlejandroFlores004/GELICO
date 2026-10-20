from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from django_htmx.http import HttpResponseClientRedirect

from main.pdf import datos_filtro, respuesta_pdf
from main.permisos import permiso_formulario, permiso_requerido
from . import services
from .forms import AbonoForm, AsignacionForm, AsignacionValorForm, BonoForm, FiltrarAsignacionesForm, ObservacionForm, ReciboForm
from .models import Abono, Asignacion, Bono, Observacion, Recibo


def _cerrar_y_recargar(request, asignacion_pk, recibo_pk=None):
    """Cierra el modal actual y recarga la página de gestión de la asignación,
    dejando seleccionado el recibo con el que se estaba trabajando."""
    url = reverse('asignacion_gestionar', args=[asignacion_pk])
    if recibo_pk:
        url += f'?recibo={recibo_pk}'
    if request.htmx:
        return HttpResponseClientRedirect(url)
    return redirect(url)


# ===================== Asignaciones =====================

def _filtrar_asignaciones(request):
    filtro_form = FiltrarAsignacionesForm(request.GET or None)
    filtros = datos_filtro(filtro_form)

    # Sin filtros no se lista nada: la página arranca solo con el buscador.
    if not any(filtros.values()):
        return filtro_form, None

    paginator = Paginator(services.filtrar_asignaciones(filtros), 20)
    asignaciones = paginator.get_page(request.GET.get('page'))
    services.asignar_estado_liquidacion(asignaciones)

    return filtro_form, asignaciones


def _tabla_asignaciones(request):
    _, asignaciones = _filtrar_asignaciones(request)
    return render(
        request,
        "partials/asignacion/_modal_form_success.html",
        {"asignaciones": asignaciones},
    )


@permiso_requerido('liquidacion.view_asignacion')
def asignacionHomeView(request):
    filtro_form, asignaciones = _filtrar_asignaciones(request)

    breadcrumbs = [
        {'name': 'Inicio', 'url': reverse('home')},
        {'name': 'Liquidación'},
    ]

    return render(
        request,
        "asignacion/asignacionHome.html",
        {
            "breadcrumbs": breadcrumbs,
            "asignaciones": asignaciones,
            "filtro_form": filtro_form,
            "form_media": filtro_form.media,
        },
    )


@permiso_requerido('liquidacion.view_asignacion')
def buscar_asignaciones(request):
    _, asignaciones = _filtrar_asignaciones(request)

    return render(
        request,
        "partials/asignacion/_tabla.html",
        {"asignaciones": asignaciones},
    )


@permiso_formulario('liquidacion.asignacion')
def asignacion_form(request, pk=None):
    instance = get_object_or_404(Asignacion, pk=pk) if pk else None
    form_class = AsignacionValorForm if instance else AsignacionForm

    if request.method == "POST":
        form = form_class(request.POST, instance=instance, prefix="asignacion")
        if form.is_valid():
            asignacion = form.save()
            if instance:
                return _cerrar_y_recargar(request, asignacion.pk)
            return _tabla_asignaciones(request)
    else:
        form = form_class(instance=instance, prefix="asignacion")

    return render(
        request,
        "partials/asignacion/_modal_form.html",
        {"form": form, "instance": instance},
    )


@permiso_requerido('liquidacion.delete_asignacion')
def asignacion_eliminar(request, pk):
    instance = get_object_or_404(Asignacion, pk=pk)

    if request.method == "POST":
        instance.delete()
        return _tabla_asignaciones(request)

    return render(
        request,
        "partials/asignacion/_modal_delete.html",
        {"instance": instance},
    )


@permiso_requerido('liquidacion.view_asignacion')
def asignacion_imprimir(request, pk):
    instance = get_object_or_404(services.asignaciones_con_encargados(con_telefonos=True), pk=pk)
    contexto = services.reporte_asignacion(instance)
    return respuesta_pdf(
        request, "partials/asignacion/_reporte_pdf.html",
        contexto, f"{contexto['nombre_reporte']}.pdf",
    )


@permiso_requerido('liquidacion.view_asignacion')
def asignacion_detalle(request, pk):
    instance = get_object_or_404(Asignacion, pk=pk)

    return render(
        request,
        "partials/asignacion/_detalle.html",
        {"instance": instance, "recibos": services.recibos_con_abonos(instance)},
    )


@permiso_requerido('liquidacion.view_recibo', 'liquidacion.view_abono')
def recibo_abonos(request, pk):
    recibo = get_object_or_404(Recibo, pk=pk)

    return render(
        request,
        "partials/asignacion/_modal_abonos.html",
        {"recibo": recibo, **services.resumen_abonos(recibo)},
    )


@permiso_requerido('liquidacion.view_asignacion')
def asignacion_gestionar(request, pk):
    instance = get_object_or_404(services.asignaciones_con_encargados(), pk=pk)

    breadcrumbs = [
        {'name': 'Inicio', 'url': reverse('home')},
        {'name': 'Liquidación', 'url': reverse('home_asignaciones')},
        {'name': f"{instance.escuela.nombre_corto} · {instance.bono.nombre}"},
    ]

    return render(
        request,
        "asignacion/asignacionGestionar.html",
        {
            "breadcrumbs": breadcrumbs,
            "instance": instance,
            **services.gestion_asignacion(instance, request.GET.get('recibo')),
        },
    )


# ===================== Recibos, abonos y observaciones =====================
# Al crear, el formulario recibe una instancia que ya apunta a su recibo/asignación.

@permiso_requerido('liquidacion.add_recibo')
def recibo_nuevo(request, asignacion_pk):
    asignacion = get_object_or_404(Asignacion, pk=asignacion_pk)

    if request.method == "POST":
        form = ReciboForm(request.POST, instance=Recibo(asignacion=asignacion), prefix="recibo")
        if form.is_valid():
            recibo = form.save()
            return _cerrar_y_recargar(request, asignacion.pk, recibo.pk)
    else:
        form = ReciboForm(prefix="recibo")

    return render(
        request,
        "partials/asignacion/_modal_recibo_form.html",
        {"form": form, "instance": None, "asignacion": asignacion},
    )


@permiso_requerido('liquidacion.change_recibo')
def recibo_editar(request, pk):
    instance = get_object_or_404(Recibo, pk=pk)

    if request.method == "POST":
        form = ReciboForm(request.POST, instance=instance, prefix="recibo")
        if form.is_valid():
            form.save()
            return _cerrar_y_recargar(request, instance.asignacion_id, instance.pk)
    else:
        form = ReciboForm(instance=instance, prefix="recibo")

    return render(
        request,
        "partials/asignacion/_modal_recibo_form.html",
        {"form": form, "instance": instance, "asignacion": instance.asignacion},
    )


@permiso_requerido('liquidacion.delete_recibo')
def recibo_eliminar(request, pk):
    instance = get_object_or_404(Recibo, pk=pk)

    if request.method == "POST":
        instance.delete()
        return _cerrar_y_recargar(request, instance.asignacion_id)

    return render(
        request,
        "partials/asignacion/_modal_recibo_delete.html",
        {"instance": instance},
    )


@permiso_requerido('liquidacion.add_abono')
def abono_nuevo(request, recibo_pk):
    recibo = get_object_or_404(Recibo, pk=recibo_pk)

    if request.method == "POST":
        form = AbonoForm(request.POST, instance=Abono(recibo=recibo), prefix="abono")
        if form.is_valid():
            form.save()
            return _cerrar_y_recargar(request, recibo.asignacion_id, recibo.pk)
    else:
        form = AbonoForm(prefix="abono")

    return render(
        request,
        "partials/asignacion/_modal_abono_form.html",
        {"form": form, "instance": None, "recibo": recibo},
    )


@permiso_requerido('liquidacion.change_abono')
def abono_editar(request, pk):
    instance = get_object_or_404(Abono, pk=pk)

    if request.method == "POST":
        form = AbonoForm(request.POST, instance=instance, prefix="abono")
        if form.is_valid():
            form.save()
            return _cerrar_y_recargar(request, instance.recibo.asignacion_id, instance.recibo_id)
    else:
        form = AbonoForm(instance=instance, prefix="abono")

    return render(
        request,
        "partials/asignacion/_modal_abono_form.html",
        {"form": form, "instance": instance, "recibo": instance.recibo},
    )


@permiso_requerido('liquidacion.delete_abono')
def abono_eliminar(request, pk):
    instance = get_object_or_404(Abono, pk=pk)
    asignacion_pk = instance.recibo.asignacion_id
    recibo_pk = instance.recibo_id

    if request.method == "POST":
        instance.delete()
        return _cerrar_y_recargar(request, asignacion_pk, recibo_pk)

    return render(
        request,
        "partials/asignacion/_modal_abono_delete.html",
        {"instance": instance},
    )


@permiso_requerido('liquidacion.add_observacion')
def observacion_nueva(request, recibo_pk):
    recibo = get_object_or_404(Recibo, pk=recibo_pk)

    if request.method == "POST":
        form = ObservacionForm(request.POST, instance=Observacion(recibo=recibo), prefix="observacion")
        if form.is_valid():
            form.save()
            return _cerrar_y_recargar(request, recibo.asignacion_id, recibo.pk)
    else:
        form = ObservacionForm(prefix="observacion")

    return render(
        request,
        "partials/asignacion/_modal_observacion_form.html",
        {"form": form, "instance": None, "recibo": recibo},
    )


@permiso_requerido('liquidacion.change_observacion')
def observacion_editar(request, pk):
    instance = get_object_or_404(Observacion, pk=pk)

    if request.method == "POST":
        form = ObservacionForm(request.POST, instance=instance, prefix="observacion")
        if form.is_valid():
            form.save()
            return _cerrar_y_recargar(request, instance.recibo.asignacion_id, instance.recibo_id)
    else:
        form = ObservacionForm(instance=instance, prefix="observacion")

    return render(
        request,
        "partials/asignacion/_modal_observacion_form.html",
        {"form": form, "instance": instance, "recibo": instance.recibo},
    )


@permiso_requerido('liquidacion.delete_observacion')
def observacion_eliminar(request, pk):
    instance = get_object_or_404(Observacion, pk=pk)
    asignacion_pk = instance.recibo.asignacion_id
    recibo_pk = instance.recibo_id

    if request.method == "POST":
        instance.delete()
        return _cerrar_y_recargar(request, asignacion_pk, recibo_pk)

    return render(
        request,
        "partials/asignacion/_modal_observacion_delete.html",
        {"instance": instance},
    )


@permiso_requerido('liquidacion.change_observacion')
@require_POST
def observacion_toggle(request, pk):
    instance = get_object_or_404(Observacion, pk=pk)
    services.alternar_observacion(instance)

    if request.GET.get('origen') == 'detalle':
        return asignacion_detalle(request, instance.recibo.asignacion_id)

    return _cerrar_y_recargar(request, instance.recibo.asignacion_id, instance.recibo_id)


# ===================== Bonos =====================

def _bonos_filtrados(request):
    """Texto, año y queryset filtrado, SIN paginar (lo reutiliza el imprimir)."""
    search = request.GET.get('q', '').strip()
    anio = request.GET.get('anio', '').strip()
    return search, anio, services.filtrar_bonos(search, anio)


def _filtrar_bonos(request):
    search, anio, bonos_list = _bonos_filtrados(request)
    bonos = Paginator(bonos_list, 20).get_page(request.GET.get('page'))
    return search, anio, bonos


def _tabla_bonos(request):
    _, _, bonos = _filtrar_bonos(request)
    return render(
        request,
        "partials/bono/_modal_form_success.html",
        {"bonos": bonos},
    )


@permiso_requerido('liquidacion.view_bono')
def bonoHomeView(request):
    search, anio, bonos = _filtrar_bonos(request)

    breadcrumbs = [
        {'name': 'Inicio', 'url': reverse('home')},
        {'name': 'Bonos'},
    ]

    return render(
        request,
        "bono/bonoHome.html",
        {
            "breadcrumbs": breadcrumbs,
            "bonos": bonos,
            "search": search,
            "anio": anio,
            "anios": services.anios_bonos(),
        },
    )


@permiso_requerido('liquidacion.view_bono')
def buscar_bonos(request):
    _, _, bonos = _filtrar_bonos(request)

    return render(
        request,
        "partials/bono/_tabla.html",
        {"bonos": bonos},
    )


@permiso_formulario('liquidacion.bono')
def bono_form(request, pk=None):
    instance = get_object_or_404(Bono, pk=pk) if pk else None

    if request.method == "POST":
        form = BonoForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            return _tabla_bonos(request)
    else:
        form = BonoForm(instance=instance)

    return render(
        request,
        "partials/bono/_modal_form.html",
        {"form": form, "instance": instance},
    )


@permiso_requerido('liquidacion.delete_bono')
def bono_eliminar(request, pk):
    instance = get_object_or_404(Bono, pk=pk)

    if request.method == "POST":
        instance.delete()
        return _tabla_bonos(request)

    return render(
        request,
        "partials/bono/_modal_delete.html",
        {"instance": instance, "total_asignaciones": instance.asignacion_set.count()},
    )


@permiso_requerido('liquidacion.view_bono')
def bono_imprimir(request):
    _, _, bonos = _bonos_filtrados(request)
    return respuesta_pdf(request, "partials/bono/_reporte_pdf.html", {"bonos": bonos}, "bonos.pdf")


# ===================== Carga de Excel =====================

@permiso_requerido('liquidacion.add_bono', 'liquidacion.add_recibo', cualquiera=True)
def home_carga_excel(request):
    breadcrumbs = [
        {'name': 'Inicio', 'url': reverse('home')},
        {'name': 'Carga de documentos Excel'},
    ]

    return render(
        request,
        "carga_excel/cargaExcelHome.html",
        {"breadcrumbs": breadcrumbs},
    )


@permiso_requerido('liquidacion.add_bono')
@require_POST
def carga_bonos_preview(request):
    return render(
        request,
        "partials/carga_excel/_modal_bonos_preview.html",
        services.previsualizar_bonos(request.FILES.get("archivo")),
    )


@permiso_requerido('liquidacion.add_bono')
@require_POST
def carga_bonos_confirmar(request):
    # Cada fila de la vista previa manda id_bono_<n>, nombre_bono_<n> y seleccion_<n> si está marcada.
    indices = {
        clave[len("id_bono_"):]
        for clave in request.POST
        if clave.startswith("id_bono_")
    }
    seleccionados = [
        (request.POST.get(f"id_bono_{indice}"), request.POST.get(f"nombre_bono_{indice}", ""))
        for indice in indices
        if request.POST.get(f"seleccion_{indice}") == "on"
    ]
    creados, omitidos = services.importar_bonos(seleccionados)

    return render(
        request,
        "partials/carga_excel/_modal_bonos_success.html",
        {"creados": creados, "omitidos": omitidos},
    )


@permiso_requerido('liquidacion.add_asignacion', 'liquidacion.add_recibo', 'liquidacion.add_abono')
@require_POST
def carga_recibos_procesar(request):
    return render(
        request,
        "partials/carga_excel/_modal_recibos_resultado.html",
        services.procesar_reporte_recibos(request.FILES.get("archivo")),
    )
