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
from django.utils.text import slugify
from django.views.decorators.http import require_POST
from django_htmx.http import HttpResponseClientRedirect
from weasyprint import HTML

from escuela.models import Encargado, Escuela
from .forms import AbonoForm, AsignacionForm, AsignacionValorForm, BonoForm, FiltrarAsignacionesForm, ObservacionForm, ReciboForm
from .models import ESTADO_LIQUIDACION_CHOICES, Abono, Asignacion, Bono, Observacion, Recibo
from .utils import a_decimal, a_entero, a_texto_codigo, extraer_anio, indice_columna, indices_columna, leer_filas_excel


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
        return 'pendiente_revision'
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
        anio = filtro_form.cleaned_data.get('anio')
        estado = filtro_form.cleaned_data.get('estado')

        if distrito:
            asignaciones_list = asignaciones_list.filter(escuela__distrito=distrito)
        if escuela:
            asignaciones_list = asignaciones_list.filter(escuela=escuela)
        if bono:
            asignaciones_list = asignaciones_list.filter(bono=bono)
        if anio:
            asignaciones_list = asignaciones_list.filter(bono__anio=anio)
        if estado:
            # El estado se calcula a partir de las observaciones (no es un campo de BD),
            # así que hay que evaluar el queryset y filtrar en Python.
            asignaciones_list = [
                asignacion for asignacion in asignaciones_list
                if _estado_liquidacion(list(asignacion.recibo_set.all())) == estado
            ]

    return filtro_form, asignaciones_list


def _hay_filtros(filtro_form):
    return filtro_form.is_valid() and any(filtro_form.cleaned_data.values())


def _filtrar_asignaciones(request):
    filtro_form, asignaciones_list = _asignaciones_filtradas(request)

    # Sin filtros no se lista nada: la página arranca solo con el buscador.
    if not _hay_filtros(filtro_form):
        return filtro_form, None

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


def asignacion_imprimir(request, pk):
    instance = get_object_or_404(
        Asignacion.objects.select_related('escuela__distrito', 'bono').prefetch_related(
            Prefetch(
                'escuela__encargado_set',
                queryset=Encargado.objects.filter(estado=True).order_by('apellido', 'nombre').prefetch_related('telefonos'),
                to_attr='encargados_activos',
            ),
        ),
        pk=pk,
    )
    recibos = list(instance.recibo_set.order_by('id').prefetch_related('observacion_set'))

    etiquetas_estado = dict(ESTADO_LIQUIDACION_CHOICES)
    total_recibido = Decimal('0')
    for recibo in recibos:
        recibo.observaciones_lista = list(recibo.observacion_set.all())
        recibo.estado_liquidacion = _estado_liquidacion([recibo])
        recibo.estado_etiqueta = etiquetas_estado[recibo.estado_liquidacion]
        total_recibido += recibo.monto

    estado_liquidacion = _estado_liquidacion(recibos)

    nombre_reporte = f"{instance.escuela.codigo}_{slugify(instance.bono.nombre)}"

    html_string = render_to_string(
        "partials/asignacion/_reporte_pdf.html",
        {
            "instance": instance,
            "escuela": instance.escuela,
            "recibos": recibos,
            "total_recibido": total_recibido,
            "diferencia": instance.valor - total_recibido,
            "estado_liquidacion": estado_liquidacion,
            "estado_etiqueta": etiquetas_estado[estado_liquidacion],
            "fecha_generacion": timezone.localdate(),
            "fecha_impresion": timezone.localtime(),
            "nombre_reporte": nombre_reporte,
        },
    )
    pdf = HTML(
        string=html_string,
        base_url=request.build_absolute_uri("/"),
    ).write_pdf()

    nombre_archivo = f"{nombre_reporte}.pdf"
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{nombre_archivo}"'
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
        Asignacion.objects.select_related('escuela__distrito', 'bono').prefetch_related(
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
        recibo.estado_liquidacion = _estado_liquidacion([recibo])
        total_recibido += recibo.monto

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


def _bonos_filtrados(request):
    """Queryset filtrado, SIN paginar. Lo reutiliza tanto el listado como el imprimir."""
    search = request.GET.get('q', '').strip()
    anio = request.GET.get('anio', '').strip()
    bonos = Bono.objects.all().order_by('-anio', 'nombre')
    if search:
        filtro = Q(nombre__icontains=search) | Q(descripcion__icontains=search)
        if search.isdigit():
            filtro |= Q(id_sistema=int(search))
        bonos = bonos.filter(filtro)
    if anio.isdigit():
        bonos = bonos.filter(anio=int(anio))
    return search, anio, bonos


def _filtrar_bonos(request):
    search, anio, bonos_list = _bonos_filtrados(request)
    paginator = Paginator(bonos_list, 20)
    bonos = paginator.get_page(request.GET.get('page'))
    return search, anio, bonos


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
            "anios": Bono.objects.order_by('-anio').values_list('anio', flat=True).distinct(),
        },
    )


def buscar_bonos(request):
    _, _, bonos = _filtrar_bonos(request)

    return render(
        request,
        "partials/bono/_tabla.html",
        {"bonos": bonos},
    )


def bono_form(request, pk=None):
    instance = get_object_or_404(Bono, pk=pk) if pk else None

    if request.method == "POST":
        form = BonoForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            _, _, bonos = _filtrar_bonos(request)
            return render(
                request,
                "partials/bono/_modal_form_success.html",
                {"bonos": bonos},
            )
    else:
        form = BonoForm(instance=instance)

    return render(
        request,
        "partials/bono/_modal_form.html",
        {"form": form, "instance": instance},
    )


def bono_eliminar(request, pk):
    instance = get_object_or_404(Bono, pk=pk)

    if request.method == "POST":
        instance.delete()
        _, _, bonos = _filtrar_bonos(request)
        return render(
            request,
            "partials/bono/_modal_form_success.html",
            {"bonos": bonos},
        )

    return render(
        request,
        "partials/bono/_modal_delete.html",
        {"instance": instance, "total_asignaciones": instance.asignacion_set.count()},
    )


def bono_imprimir(request):
    _, _, bonos = _bonos_filtrados(request)
    html_string = render_to_string(
        "partials/bono/_reporte_pdf.html",
        {
            "bonos": bonos,
            "fecha_generacion": timezone.localdate(),
            "fecha_impresion": timezone.localtime(),
        },
    )
    pdf = HTML(
        string=html_string,
        base_url=request.build_absolute_uri("/"),
    ).write_pdf()

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="bonos.pdf"'
    return response


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


_SESION_ASIGNACIONES = "carga_excel_asignaciones"


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
    col_escuela = indice_columna(encabezados, "codigo_entidad")
    col_monto = indice_columna(encabezados, "monto_asignado")

    if None in (col_id, col_nombre, col_escuela, col_monto):
        return render(
            request,
            "partials/carga_excel/_modal_bonos_preview.html",
            {
                "error": (
                    "El archivo debe tener las columnas \"id_bono\", \"nombre_bono\", "
                    "\"codigo_entidad\" y \"monto_asignado\" en la primera fila."
                )
            },
        )

    maximo_indice = max(col_id, col_nombre, col_escuela, col_monto)
    vistos = {}
    # id_bono -> {codigo_entidad: monto_asignado}; una escuela puede repetirse
    # en varias filas del mismo bono, se toma el primer monto encontrado.
    asignaciones = {}
    for fila in filas:
        if len(fila) <= maximo_indice:
            continue

        id_bono = a_entero(fila[col_id])
        nombre_bono = fila[col_nombre]
        nombre_bono = str(nombre_bono).strip() if nombre_bono not in (None, "") else ""

        if id_bono is None or not nombre_bono:
            continue

        vistos.setdefault(id_bono, nombre_bono)

        codigo = a_texto_codigo(fila[col_escuela])
        monto = a_decimal(fila[col_monto])
        if codigo and monto is not None:
            asignaciones.setdefault(id_bono, {}).setdefault(codigo, monto)

    nombres_existentes = set(Bono.objects.values_list("nombre", flat=True))
    ids_existentes = set(
        Bono.objects.exclude(id_sistema=None).values_list("id_sistema", flat=True)
    )

    bonos = [
        {
            "id_bono": id_bono,
            "nombre_bono": nombre_bono,
            "anio": extraer_anio(nombre_bono),
            "ya_existe": id_bono in ids_existentes or nombre_bono in nombres_existentes,
            "total_asignaciones": len(asignaciones.get(id_bono, {})),
            "monto_total": sum(asignaciones.get(id_bono, {}).values(), Decimal("0")),
        }
        for id_bono, nombre_bono in vistos.items()
    ]

    # El archivo no viaja en la confirmación, así que las asignaciones se
    # guardan en la sesión hasta que el usuario confirme.
    request.session[_SESION_ASIGNACIONES] = {
        str(id_bono): {codigo: str(monto) for codigo, monto in por_escuela.items()}
        for id_bono, por_escuela in asignaciones.items()
    }

    return render(
        request,
        "partials/carga_excel/_modal_bonos_preview.html",
        {"bonos": bonos},
    )


def _cargar_asignaciones_bono(bono, por_escuela, escuelas, contadores):
    existentes = set(
        Asignacion.objects.filter(bono=bono).values_list("escuela_id", flat=True)
    )
    nuevas = []
    for codigo, monto in por_escuela.items():
        escuela = escuelas.get(codigo)
        if escuela is None:
            contadores["escuelas_no_encontradas"] += 1
            continue
        if escuela.id in existentes:
            contadores["asignaciones_existentes"] += 1
            continue
        nuevas.append(Asignacion(escuela=escuela, bono=bono, valor=Decimal(monto)))
        existentes.add(escuela.id)

    Asignacion.objects.bulk_create(nuevas)
    contadores["asignaciones_creadas"] += len(nuevas)


@require_POST
def carga_bonos_confirmar(request):
    asignaciones = request.session.pop(_SESION_ASIGNACIONES, {})
    escuelas = {str(e.codigo).strip(): e for e in Escuela.objects.all()}

    contadores = {
        "creados": 0,
        "omitidos": 0,
        "asignaciones_creadas": 0,
        "asignaciones_existentes": 0,
        "escuelas_no_encontradas": 0,
    }

    indices = {
        clave[len("id_bono_"):]
        for clave in request.POST
        if clave.startswith("id_bono_")
    }

    with transaction.atomic():
        for indice in indices:
            if request.POST.get(f"seleccion_{indice}") != "on":
                continue

            id_bono = a_entero(request.POST.get(f"id_bono_{indice}"))
            nombre_bono = request.POST.get(f"nombre_bono_{indice}", "").strip()

            if id_bono is None or not nombre_bono:
                continue

            bono = Bono.objects.filter(Q(id_sistema=id_bono) | Q(nombre=nombre_bono)).first()
            if bono is not None:
                contadores["omitidos"] += 1
            else:
                anio = extraer_anio(nombre_bono)
                if anio is None:
                    continue
                bono = Bono.objects.create(nombre=nombre_bono, id_sistema=id_bono, anio=anio)
                contadores["creados"] += 1

            _cargar_asignaciones_bono(
                bono, asignaciones.get(str(id_bono), {}), escuelas, contadores
            )

    return render(
        request,
        "partials/carga_excel/_modal_bonos_success.html",
        contadores,
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
        "no_requerimiento": indice_columna(encabezados, "no_requerimiento"),
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
                "\"no_requerimiento\", \"estado_trans\", "
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
        "recibos_creados": 0,
        "recibos_existentes": 0,
        "abonos_creados": 0,
        "abonos_existentes": 0,
        "filas_omitidas_escuela": 0,
        "filas_omitidas_bono": 0,
        "filas_omitidas_asignacion": 0,
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
        requerimiento_val = fila[indices["no_requerimiento"]]
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

        # Las asignaciones se crean desde el archivo de transferencias; aquí
        # solo se usan las que ya existen.
        clave_asignacion = (escuela.id, bono.id)
        if clave_asignacion not in asignaciones_cache:
            asignaciones_cache[clave_asignacion] = Asignacion.objects.filter(
                escuela=escuela, bono=bono
            ).first()
        asignacion = asignaciones_cache[clave_asignacion]
        if asignacion is None:
            contadores["filas_omitidas_asignacion"] += 1
            continue

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
