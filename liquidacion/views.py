from decimal import Decimal

from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import DecimalField, F, Prefetch, Q, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django_htmx.http import HttpResponseClientRedirect
from weasyprint import HTML

from catalogo.models import Bono
from escuela.models import Encargado, Escuela
from .forms import AbonoForm, AsignacionForm, AsignacionValorForm, FiltrarAsignacionesForm, ObservacionForm, ReciboForm
from .models import Abono, Asignacion, Observacion, Recibo
from .utils import a_decimal, a_entero, a_texto_codigo, indice_columna, indices_columna, leer_filas_excel


def _cerrar_y_recargar(request, asignacion_pk):
    """Cierra el modal actual y recarga la página de gestión de la asignación."""
    url = reverse('asignacion_gestionar', args=[asignacion_pk])
    if request.htmx:
        return HttpResponseClientRedirect(url)
    return redirect(url)


def _estado_liquidacion(recibos):
    """Calcula el estado de liquidación de una asignación según sus observaciones."""
    observaciones = [obs for recibo in recibos for obs in recibo.observacion_set.all()]
    if not observaciones:
        return 'pendiente_observacion'
    if all(obs.resuelta for obs in observaciones):
        return 'liquidado'
    return 'liquidado_con_observaciones'


def _asignar_estado_liquidacion(asignaciones):
    for asignacion in asignaciones:
        asignacion.estado_liquidacion = _estado_liquidacion(list(asignacion.recibo_set.all()))


def _asignaciones_filtradas(request):
    filtro_form = FiltrarAsignacionesForm(request.GET or None)

    asignaciones_list = Asignacion.objects.select_related('escuela', 'bono').prefetch_related(
        Prefetch(
            'escuela__encargado_set',
            queryset=Encargado.objects.filter(estado=True),
            to_attr='encargados_activos',
        ),
        'recibo_set__observacion_set',
    ).annotate(
        total_recibido=Coalesce(
            Sum('recibo__monto'), Decimal('0'),
            output_field=DecimalField(max_digits=10, decimal_places=2),
        )
    ).annotate(
        diferencia=F('valor') - F('total_recibido')
    ).order_by(
        'escuela__nombre_corto', 'bono__nombre'
    )

    if filtro_form.is_valid():
        distrito = filtro_form.cleaned_data.get('distrito')
        escuela = filtro_form.cleaned_data.get('escuela')
        bono = filtro_form.cleaned_data.get('bono')
        estado = filtro_form.cleaned_data.get('estado')

        if distrito:
            asignaciones_list = asignaciones_list.filter(escuela__distrito=distrito)
        if escuela:
            asignaciones_list = asignaciones_list.filter(escuela=escuela)
        if bono:
            asignaciones_list = asignaciones_list.filter(bono=bono)
        if estado:
            # El estado se calcula a partir de las observaciones (no es un campo de BD),
            # así que hay que evaluar el queryset y filtrar en Python.
            asignaciones_list = [
                asignacion for asignacion in asignaciones_list
                if _estado_liquidacion(list(asignacion.recibo_set.all())) == estado
            ]

    return filtro_form, asignaciones_list


def _filtrar_asignaciones(request):
    filtro_form, asignaciones_list = _asignaciones_filtradas(request)

    paginator = Paginator(asignaciones_list, 20)
    asignaciones = paginator.get_page(request.GET.get('page'))
    _asignar_estado_liquidacion(asignaciones)

    return filtro_form, asignaciones


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


def buscar_asignaciones(request):
    _, asignaciones = _filtrar_asignaciones(request)

    return render(
        request,
        "partials/asignacion/_tabla.html",
        {"asignaciones": asignaciones},
    )


def asignacion_form(request, pk=None):
    instance = get_object_or_404(Asignacion, pk=pk) if pk else None
    form_class = AsignacionValorForm if instance else AsignacionForm

    if request.method == "POST":
        form = form_class(request.POST, instance=instance, prefix="asignacion")
        if form.is_valid():
            asignacion = form.save()
            if instance:
                return _cerrar_y_recargar(request, asignacion.pk)
            _, asignaciones = _filtrar_asignaciones(request)
            return render(
                request,
                "partials/asignacion/_modal_form_success.html",
                {"asignaciones": asignaciones},
            )
    else:
        form = form_class(instance=instance, prefix="asignacion")

    return render(
        request,
        "partials/asignacion/_modal_form.html",
        {"form": form, "instance": instance},
    )


def asignacion_eliminar(request, pk):
    instance = get_object_or_404(Asignacion, pk=pk)

    if request.method == "POST":
        instance.delete()
        _, asignaciones = _filtrar_asignaciones(request)
        return render(
            request,
            "partials/asignacion/_modal_form_success.html",
            {"asignaciones": asignaciones},
        )

    return render(
        request,
        "partials/asignacion/_modal_delete.html",
        {"instance": instance},
    )


def asignacion_imprimir(request):
    _, asignaciones = _asignaciones_filtradas(request)
    html_string = render_to_string(
        "partials/asignacion/_reporte_pdf.html",
        {"asignaciones": asignaciones, "fecha_generacion": timezone.localdate()},
    )
    pdf = HTML(
        string=html_string,
        base_url=request.build_absolute_uri("/"),
    ).write_pdf()

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="asignaciones.pdf"'
    return response


def asignacion_detalle(request, pk):
    instance = get_object_or_404(Asignacion, pk=pk)
    recibos = list(
        instance.recibo_set.order_by('id').prefetch_related('abono_set', 'observacion_set')
    )

    for recibo in recibos:
        abonos = list(recibo.abono_set.all())
        recibo.abonos_lista = abonos
        recibo.total_abonado = sum((abono.monto for abono in abonos), Decimal('0'))
        recibo.diferencia = recibo.monto - recibo.total_abonado
        recibo.observaciones_lista = list(recibo.observacion_set.all())

    return render(
        request,
        "partials/asignacion/_detalle.html",
        {"instance": instance, "recibos": recibos},
    )


def recibo_abonos(request, pk):
    recibo = get_object_or_404(Recibo, pk=pk)
    abonos = list(recibo.abono_set.order_by('id'))
    total_abonado = sum((abono.monto for abono in abonos), Decimal('0'))

    return render(
        request,
        "partials/asignacion/_modal_abonos.html",
        {
            "recibo": recibo,
            "abonos": abonos,
            "total_abonado": total_abonado,
            "diferencia": recibo.monto - total_abonado,
        },
    )


def asignacion_gestionar(request, pk):
    instance = get_object_or_404(
        Asignacion.objects.select_related('escuela', 'bono').prefetch_related(
            Prefetch(
                'escuela__encargado_set',
                queryset=Encargado.objects.filter(estado=True),
                to_attr='encargados_activos',
            )
        ),
        pk=pk,
    )
    recibos = list(
        instance.recibo_set.order_by('id').prefetch_related('abono_set', 'observacion_set')
    )

    total_recibido = Decimal('0')
    for recibo in recibos:
        abonos = list(recibo.abono_set.all())
        recibo.abonos_lista = abonos
        recibo.total_abonado = sum((abono.monto for abono in abonos), Decimal('0'))
        recibo.diferencia = recibo.monto - recibo.total_abonado
        recibo.observaciones_lista = list(recibo.observacion_set.all())
        total_recibido += recibo.monto

    estado_liquidacion = _estado_liquidacion(recibos)

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
            "estado_liquidacion": estado_liquidacion,
            "recibos": recibos,
            "total_recibido": total_recibido,
            "diferencia": instance.valor - total_recibido,
        },
    )


def recibo_nuevo(request, asignacion_pk):
    asignacion = get_object_or_404(Asignacion, pk=asignacion_pk)

    if request.method == "POST":
        form = ReciboForm(request.POST, prefix="recibo")
        if form.is_valid():
            recibo = form.save(commit=False)
            recibo.asignacion = asignacion
            recibo.save()
            return _cerrar_y_recargar(request, asignacion.pk)
    else:
        form = ReciboForm(prefix="recibo")

    return render(
        request,
        "partials/asignacion/_modal_recibo_form.html",
        {"form": form, "instance": None, "asignacion": asignacion},
    )


def recibo_editar(request, pk):
    instance = get_object_or_404(Recibo, pk=pk)

    if request.method == "POST":
        form = ReciboForm(request.POST, instance=instance, prefix="recibo")
        if form.is_valid():
            form.save()
            return _cerrar_y_recargar(request, instance.asignacion_id)
    else:
        form = ReciboForm(instance=instance, prefix="recibo")

    return render(
        request,
        "partials/asignacion/_modal_recibo_form.html",
        {"form": form, "instance": instance, "asignacion": instance.asignacion},
    )


def recibo_eliminar(request, pk):
    instance = get_object_or_404(Recibo, pk=pk)
    asignacion_pk = instance.asignacion_id

    if request.method == "POST":
        instance.delete()
        return _cerrar_y_recargar(request, asignacion_pk)

    return render(
        request,
        "partials/asignacion/_modal_recibo_delete.html",
        {"instance": instance},
    )


def abono_nuevo(request, recibo_pk):
    recibo = get_object_or_404(Recibo, pk=recibo_pk)

    if request.method == "POST":
        form = AbonoForm(request.POST, prefix="abono")
        if form.is_valid():
            abono = form.save(commit=False)
            abono.recibo = recibo
            abono.save()
            return _cerrar_y_recargar(request, recibo.asignacion_id)
    else:
        form = AbonoForm(prefix="abono")

    return render(
        request,
        "partials/asignacion/_modal_abono_form.html",
        {"form": form, "instance": None, "recibo": recibo},
    )


def abono_editar(request, pk):
    instance = get_object_or_404(Abono, pk=pk)

    if request.method == "POST":
        form = AbonoForm(request.POST, instance=instance, prefix="abono")
        if form.is_valid():
            form.save()
            return _cerrar_y_recargar(request, instance.recibo.asignacion_id)
    else:
        form = AbonoForm(instance=instance, prefix="abono")

    return render(
        request,
        "partials/asignacion/_modal_abono_form.html",
        {"form": form, "instance": instance, "recibo": instance.recibo},
    )


def abono_eliminar(request, pk):
    instance = get_object_or_404(Abono, pk=pk)
    asignacion_pk = instance.recibo.asignacion_id

    if request.method == "POST":
        instance.delete()
        return _cerrar_y_recargar(request, asignacion_pk)

    return render(
        request,
        "partials/asignacion/_modal_abono_delete.html",
        {"instance": instance},
    )


def observacion_nueva(request, recibo_pk):
    recibo = get_object_or_404(Recibo, pk=recibo_pk)

    if request.method == "POST":
        form = ObservacionForm(request.POST, prefix="observacion")
        if form.is_valid():
            observacion = form.save(commit=False)
            observacion.recibo = recibo
            observacion.save()
            return _cerrar_y_recargar(request, recibo.asignacion_id)
    else:
        form = ObservacionForm(prefix="observacion")

    return render(
        request,
        "partials/asignacion/_modal_observacion_form.html",
        {"form": form, "instance": None, "recibo": recibo},
    )


def observacion_editar(request, pk):
    instance = get_object_or_404(Observacion, pk=pk)

    if request.method == "POST":
        form = ObservacionForm(request.POST, instance=instance, prefix="observacion")
        if form.is_valid():
            form.save()
            return _cerrar_y_recargar(request, instance.recibo.asignacion_id)
    else:
        form = ObservacionForm(instance=instance, prefix="observacion")

    return render(
        request,
        "partials/asignacion/_modal_observacion_form.html",
        {"form": form, "instance": instance, "recibo": instance.recibo},
    )


def observacion_eliminar(request, pk):
    instance = get_object_or_404(Observacion, pk=pk)
    asignacion_pk = instance.recibo.asignacion_id

    if request.method == "POST":
        instance.delete()
        return _cerrar_y_recargar(request, asignacion_pk)

    return render(
        request,
        "partials/asignacion/_modal_observacion_delete.html",
        {"instance": instance},
    )


@require_POST
def observacion_toggle(request, pk):
    instance = get_object_or_404(Observacion, pk=pk)
    instance.resuelta = not instance.resuelta
    instance.save()

    if request.GET.get('origen') == 'detalle':
        return asignacion_detalle(request, instance.recibo.asignacion_id)

    return _cerrar_y_recargar(request, instance.recibo.asignacion_id)


def home_carga_excel(request):
    return render(request, "carga_excel/cargaExcelHome.html")


@require_POST
def carga_bonos_preview(request):
    archivo = request.FILES.get("archivo")

    if not archivo or not archivo.name.lower().endswith((".xlsx", ".xls")):
        return render(
            request,
            "partials/carga_excel/_modal_bonos_preview.html",
            {"error": "Selecciona un archivo con formato .xlsx o .xls."},
        )

    try:
        encabezados, filas = leer_filas_excel(archivo)
    except Exception:
        return render(
            request,
            "partials/carga_excel/_modal_bonos_preview.html",
            {"error": "No se pudo leer el archivo. Verifica que no esté dañado."},
        )

    col_id = indice_columna(encabezados, "id_bono")
    col_nombre = indice_columna(encabezados, "nombre_bono")

    if col_id is None or col_nombre is None:
        return render(
            request,
            "partials/carga_excel/_modal_bonos_preview.html",
            {"error": "El archivo debe tener las columnas \"id_bono\" y \"nombre_bono\" en la primera fila."},
        )

    vistos = {}
    for fila in filas:
        if col_id >= len(fila) or col_nombre >= len(fila):
            continue

        id_bono = a_entero(fila[col_id])
        nombre_bono = fila[col_nombre]
        nombre_bono = str(nombre_bono).strip() if nombre_bono not in (None, "") else ""

        if id_bono is None or not nombre_bono:
            continue

        vistos.setdefault(id_bono, nombre_bono)

    nombres_existentes = set(Bono.objects.values_list("nombre", flat=True))
    ids_existentes = set(
        Bono.objects.exclude(id_sistema=None).values_list("id_sistema", flat=True)
    )

    bonos = [
        {
            "id_bono": id_bono,
            "nombre_bono": nombre_bono,
            "ya_existe": id_bono in ids_existentes or nombre_bono in nombres_existentes,
        }
        for id_bono, nombre_bono in vistos.items()
    ]

    return render(
        request,
        "partials/carga_excel/_modal_bonos_preview.html",
        {"bonos": bonos},
    )


@require_POST
def carga_bonos_confirmar(request):
    creados = 0
    omitidos = 0

    indices = {
        clave[len("id_bono_"):]
        for clave in request.POST
        if clave.startswith("id_bono_")
    }

    for indice in indices:
        if request.POST.get(f"seleccion_{indice}") != "on":
            continue

        id_bono = a_entero(request.POST.get(f"id_bono_{indice}"))
        nombre_bono = request.POST.get(f"nombre_bono_{indice}", "").strip()

        if id_bono is None or not nombre_bono:
            continue

        ya_existe = Bono.objects.filter(nombre=nombre_bono).exists() or Bono.objects.filter(id_sistema=id_bono).exists()
        if ya_existe:
            omitidos += 1
            continue

        Bono.objects.create(nombre=nombre_bono, id_sistema=id_bono)
        creados += 1

    return render(
        request,
        "partials/carga_excel/_modal_bonos_success.html",
        {"creados": creados, "omitidos": omitidos},
    )


def _columnas_reporte_recibos(encabezados):
    """Ubica las columnas del reporte transferido por recibo.

    "monto" aparece dos veces en el archivo: la primera es el monto del
    recibo y la última es el monto del abono de esa fila.
    """
    montos = indices_columna(encabezados, "monto")
    indices = {
        "codigo_entidad": indice_columna(encabezados, "codigo_entidad"),
        "id_bono": indice_columna(encabezados, "id_bono"),
        "monto_asignado": indice_columna(encabezados, "monto_asignado"),
        "codigo_requerimiento": indice_columna(encabezados, "codigo_requerimiento"),
        "estado_trans": indice_columna(encabezados, "estado_trans"),
        "id_planilla_parcial": indice_columna(encabezados, "id_planilla_parcial"),
    }

    if any(valor is None for valor in indices.values()) or len(montos) < 2:
        return None

    indices["monto_recibo"] = montos[0]
    indices["monto_abono"] = montos[-1]
    return indices


def _procesar_reporte_recibos(archivo):
    try:
        encabezados, filas = leer_filas_excel(archivo)
    except Exception:
        return {"error": "No se pudo leer el archivo. Verifica que no esté dañado."}

    indices = _columnas_reporte_recibos(encabezados)
    if indices is None:
        return {
            "error": (
                "El archivo debe tener las columnas \"codigo_entidad\", \"id_bono\", "
                "\"monto_asignado\", \"codigo_requerimiento\", \"estado_trans\", "
                "\"id_planilla_parcial\" y dos columnas \"monto\" (una para el recibo "
                "y otra para el abono)."
            )
        }

    escuelas = {str(e.codigo).strip(): e for e in Escuela.objects.all()}
    bonos = {b.id_sistema: b for b in Bono.objects.exclude(id_sistema=None)}

    asignaciones_cache = {}
    recibos_cache = {}
    abonos_por_recibo = {}
    maximo_indice = max(indices.values())

    contadores = {
        "asignaciones_creadas": 0,
        "asignaciones_existentes": 0,
        "recibos_creados": 0,
        "recibos_existentes": 0,
        "abonos_creados": 0,
        "abonos_existentes": 0,
        "filas_omitidas_escuela": 0,
        "filas_omitidas_bono": 0,
        "filas_omitidas_datos": 0,
    }

    for fila in filas:
        if not fila or all(valor in (None, "") for valor in fila):
            continue
        if len(fila) <= maximo_indice:
            contadores["filas_omitidas_datos"] += 1
            continue

        escuela = escuelas.get(a_texto_codigo(fila[indices["codigo_entidad"]]))
        if escuela is None:
            contadores["filas_omitidas_escuela"] += 1
            continue

        bono = bonos.get(a_entero(fila[indices["id_bono"]]))
        if bono is None:
            contadores["filas_omitidas_bono"] += 1
            continue

        monto_recibo = a_decimal(fila[indices["monto_recibo"]])
        monto_abono = a_decimal(fila[indices["monto_abono"]])
        estado = a_entero(fila[indices["estado_trans"]])
        requerimiento_val = fila[indices["codigo_requerimiento"]]
        requerimiento = str(requerimiento_val).strip() if requerimiento_val not in (None, "") else ""
        id_planilla_parcial = a_entero(fila[indices["id_planilla_parcial"]])

        if (
            monto_recibo is None
            or monto_abono is None
            or estado is None
            or not requerimiento
            or id_planilla_parcial is None
        ):
            contadores["filas_omitidas_datos"] += 1
            continue

        clave_asignacion = (escuela.id, bono.id)
        if clave_asignacion not in asignaciones_cache:
            asignacion = Asignacion.objects.filter(escuela=escuela, bono=bono).first()
            if asignacion is None:
                valor = a_decimal(fila[indices["monto_asignado"]]) or Decimal("0")
                asignacion = Asignacion.objects.create(escuela=escuela, bono=bono, valor=valor)
                contadores["asignaciones_creadas"] += 1
            else:
                contadores["asignaciones_existentes"] += 1
            asignaciones_cache[clave_asignacion] = asignacion
        asignacion = asignaciones_cache[clave_asignacion]

        clave_recibo = (clave_asignacion, monto_recibo)
        if clave_recibo not in recibos_cache:
            recibo = Recibo.objects.filter(asignacion=asignacion, monto=monto_recibo).first()
            if recibo is None:
                recibo = Recibo.objects.create(asignacion=asignacion, monto=monto_recibo)
                contadores["recibos_creados"] += 1
            else:
                contadores["recibos_existentes"] += 1
            recibos_cache[clave_recibo] = recibo
        recibo = recibos_cache[clave_recibo]

        if recibo.id not in abonos_por_recibo:
            abonos_por_recibo[recibo.id] = set(
                Abono.objects.filter(recibo=recibo).values_list("id_planilla_parcial", flat=True)
            )

        if id_planilla_parcial in abonos_por_recibo[recibo.id]:
            contadores["abonos_existentes"] += 1
            continue

        Abono.objects.create(
            recibo=recibo,
            monto=monto_abono,
            requerimiento=requerimiento,
            estado=estado,
            id_planilla_parcial=id_planilla_parcial,
        )
        abonos_por_recibo[recibo.id].add(id_planilla_parcial)
        contadores["abonos_creados"] += 1

    return {"contadores": contadores}


@require_POST
def carga_recibos_procesar(request):
    archivo = request.FILES.get("archivo")

    if not archivo or not archivo.name.lower().endswith((".xlsx", ".xls")):
        return render(
            request,
            "partials/carga_excel/_modal_recibos_resultado.html",
            {"error": "Selecciona un archivo con formato .xlsx o .xls."},
        )

    with transaction.atomic():
        resultado = _procesar_reporte_recibos(archivo)

    return render(
        request,
        "partials/carga_excel/_modal_recibos_resultado.html",
        resultado,
    )
