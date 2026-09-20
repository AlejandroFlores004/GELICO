from decimal import Decimal

from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_POST
from weasyprint import HTML

from catalogo.models import Bono
from escuela.models import Escuela
from .forms import AsignacionForm, FiltrarAsignacionesForm
from .models import Abono, Asignacion, Recibo
from .utils import a_decimal, a_entero, a_texto_codigo, indice_columna, indices_columna, leer_filas_excel


def _asignaciones_filtradas(request):
    filtro_form = FiltrarAsignacionesForm(request.GET or None)

    asignaciones_list = Asignacion.objects.select_related('escuela', 'bono').order_by(
        'escuela__nombre_corto', 'bono__nombre'
    )

    if filtro_form.is_valid():
        escuela = filtro_form.cleaned_data.get('escuela')
        bono = filtro_form.cleaned_data.get('bono')

        if escuela:
            asignaciones_list = asignaciones_list.filter(escuela=escuela)
        if bono:
            asignaciones_list = asignaciones_list.filter(bono=bono)

    return filtro_form, asignaciones_list


def _filtrar_asignaciones(request):
    filtro_form, asignaciones_list = _asignaciones_filtradas(request)

    paginator = Paginator(asignaciones_list, 20)
    asignaciones = paginator.get_page(request.GET.get('page'))

    return filtro_form, asignaciones


def asignacionHomeView(request):
    filtro_form, asignaciones = _filtrar_asignaciones(request)

    return render(
        request,
        "asignacion/asignacionHome.html",
        {
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

    if request.method == "POST":
        form = AsignacionForm(request.POST, instance=instance, prefix="asignacion")
        if form.is_valid():
            form.save()
            _, asignaciones = _filtrar_asignaciones(request)
            return render(
                request,
                "partials/asignacion/_modal_form_success.html",
                {"asignaciones": asignaciones},
            )
    else:
        form = AsignacionForm(instance=instance, prefix="asignacion")

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
    recibos = instance.recibo_set.order_by('id').prefetch_related('abono_set')

    return render(
        request,
        "partials/asignacion/_detalle.html",
        {"recibos": recibos},
    )


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
                "\"monto_asignado\", \"codigo_requerimiento\", \"estado_trans\" y dos "
                "columnas \"monto\" (una para el recibo y otra para el abono)."
            )
        }

    escuelas = {str(e.codigo).strip(): e for e in Escuela.objects.all()}
    bonos = {b.id_sistema: b for b in Bono.objects.exclude(id_sistema=None)}

    asignaciones_cache = {}
    recibos_cache = {}
    maximo_indice = max(indices.values())

    contadores = {
        "asignaciones_creadas": 0,
        "asignaciones_existentes": 0,
        "recibos_creados": 0,
        "recibos_existentes": 0,
        "abonos_creados": 0,
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

        if monto_recibo is None or monto_abono is None or estado is None or not requerimiento:
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

        Abono.objects.create(
            recibo=recibo,
            monto=monto_abono,
            requerimiento=requerimiento,
            estado=estado,
        )
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
