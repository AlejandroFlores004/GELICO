from django.shortcuts import render
from django.views.decorators.http import require_POST

from catalogo.models import Bono
from .utils import a_entero, indice_columna, leer_filas_excel


def home_asignaciones(request):
    return render(request, "asignacion/asignacionHome.html")


def home_recibos(request):
    return render(request, "recibo/reciboHome.html")


def home_abonos(request):
    return render(request, "abono/abonoHome.html")


def home_carga_excel(request):
    return render(request, "carga_excel/cargaExcelHome.html")


@require_POST
def carga_bonos_preview(request):
    archivo = request.FILES.get("archivo")

    if not archivo or not archivo.name.lower().endswith((".xlsx", ".xls")):
        return render(
            request,
            "partials/carga_excel/modal_bonos_preview.html",
            {"error": "Selecciona un archivo con formato .xlsx o .xls."},
        )

    try:
        encabezados, filas = leer_filas_excel(archivo)
    except Exception:
        return render(
            request,
            "partials/carga_excel/modal_bonos_preview.html",
            {"error": "No se pudo leer el archivo. Verifica que no esté dañado."},
        )

    col_id = indice_columna(encabezados, "id_bono")
    col_nombre = indice_columna(encabezados, "nombre_bono")

    if col_id is None or col_nombre is None:
        return render(
            request,
            "partials/carga_excel/modal_bonos_preview.html",
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
        "partials/carga_excel/modal_bonos_preview.html",
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
        "partials/carga_excel/modal_bonos_success.html",
        {"creados": creados, "omitidos": omitidos},
    )
