from collections import defaultdict
from datetime import timedelta
from urllib.parse import urlencode

from django.http import HttpResponse, HttpResponseNotAllowed, HttpResponseRedirect
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.formats import date_format
from django.utils.text import capfirst
from weasyprint import HTML

from main.permisos import permiso_formulario, permiso_requerido
from .agenda import (
    MODOS, Agenda, agenda_de_convocatoria, auxiliares_asignados, con_conteos, convocatoria_por_defecto, convocatorias_agrupadas,
    cubren_en_jornada, estado_convocatoria, etiqueta_jornada, otras_convocatorias, rango_visible,
    resumen_estados, sumar_meses, tono_convocatoria, tonos_por_auxiliar,
)

from .forms import (
    AsignarAuxiliaresDiaForm, AuxiliarForm, AusenciaForm, ConvocatoriaForm, HorarioForm, ProgramacionEstadoForm,
    ProgramacionFiltroForm, ProgramacionForm,
)
from .models import ORDEN_JORNADA, Auxiliar, Ausencia, Convocatoria, Horario, Jornada, Programacion


def _programaciones_filtradas(request, paginar=True):
    filtro_form = ProgramacionFiltroForm(request.GET or None)
    programaciones = Programacion.objects.select_related(
        'convocatoria', 'escuela'
    ).order_by('-fecha_programada', ORDEN_JORNADA.desc())

    if filtro_form.is_valid():
        search = filtro_form.cleaned_data.get('q', '').strip()
        convocatoria = filtro_form.cleaned_data.get('convocatoria')
        escuela = filtro_form.cleaned_data.get('escuela')

        if convocatoria:
            programaciones = programaciones.filter(convocatoria=convocatoria)
        if escuela:
            programaciones = programaciones.filter(escuela=escuela)
        if search:
            programaciones = programaciones.filter(
                Q(convocatoria__nombre__icontains=search)
                | Q(escuela__nombre__icontains=search)
                | Q(escuela__nombre_corto__icontains=search)
                | Q(estado__icontains=search)
            )

    if paginar:
        paginator = Paginator(programaciones, 20)
        programaciones = paginator.get_page(request.GET.get('page'))
    return filtro_form, programaciones


SECCIONES = ('calendario', 'convocatorias', 'programaciones')
# Evento htmx que los calendarios escuchan para volver a pintarse tras guardar algo en un modal.
EVENTO_AGENDA = 'agenda-actualizada'
FORMATO_DIA = 'l j \\d\\e F \\d\\e Y'
FORMATO_FECHA = 'j \\d\\e F Y'


def _origen(request):
    """Desde dónde se abrió un modal: 'calendario' (mes de convocatorias), 'convocatoria' (su agenda) o una lista."""
    return request.GET.get('origen', '')


def _desde_calendario(request):
    return _origen(request) in ('calendario', 'convocatoria')


def _respuesta_guardado(request, plantilla, contexto):
    """Cierra el modal. Desde una lista refresca su tabla; desde un calendario lo avisa con un evento."""
    respuesta = render(request, plantilla, {**contexto, 'desde_calendario': _desde_calendario(request)})
    respuesta['HX-Trigger'] = EVENTO_AGENDA
    return respuesta


def _redirigir_htmx(url):
    respuesta = HttpResponse()
    respuesta['HX-Redirect'] = url
    return respuesta


def _fecha(valor):
    try:
        return parse_date(valor or '')
    except ValueError:
        return None


def _por_id(modelo, valor):
    return modelo.objects.filter(pk=valor).first() if valor and str(valor).isdigit() else None


def _titulo_periodo(modo, dia):
    if modo == 'dia':
        return capfirst(date_format(dia, FORMATO_DIA))
    if modo == 'mes':
        return capfirst(date_format(dia, 'F Y'))
    inicio, fin = rango_visible('semana', dia)
    if inicio.month == fin.month:
        return f"{inicio.day} – {fin.day} de {date_format(fin, 'F Y')}"
    if inicio.year == fin.year:
        return f"{inicio.day} de {date_format(inicio, 'F')} – {fin.day} de {date_format(fin, 'F Y')}"
    return f"{date_format(inicio, FORMATO_FECHA)} – {date_format(fin, FORMATO_FECHA)}"


# ---------------------------------------------------------------------------
# Calendario: agenda semanal por jornadas de la convocatoria elegida
# ---------------------------------------------------------------------------

def _url_agenda(convocatoria, modo, dia, auxiliar=None):
    parametros = {'convocatoria': convocatoria.pk, 'modo': modo, 'fecha': dia.isoformat()}
    if auxiliar:
        parametros['auxiliar'] = auxiliar.pk
    return f"{reverse('home_programacion')}?{urlencode(parametros)}"


def _contexto_agenda(request):
    hoy = timezone.localdate()
    convocatoria = _por_id(Convocatoria, request.GET.get('convocatoria')) or convocatoria_por_defecto(hoy)
    if convocatoria is None:
        return {'convocatoria': None}
    convocatoria = con_conteos(Convocatoria.objects.filter(pk=convocatoria.pk)).get()
    convocatoria.tono = tono_convocatoria(convocatoria)
    en_periodo = convocatoria.fecha_inicio <= hoy <= convocatoria.fecha_fin

    modo = request.GET.get('modo')
    modo = modo if modo in MODOS else 'semana'
    # Sin fecha, se abre en hoy si la convocatoria está en curso; si no, en su primer día.
    dia = _fecha(request.GET.get('fecha')) or (hoy if en_periodo else convocatoria.fecha_inicio)
    auxiliares = list(auxiliares_asignados(convocatoria))
    # Solo se filtra por auxiliares asignados a algún día de la convocatoria.
    auxiliar = next((a for a in auxiliares if str(a.pk) == request.GET.get('auxiliar')), None)

    def url(modo_destino, dia_destino):
        return _url_agenda(convocatoria, modo_destino, dia_destino, auxiliar)

    if modo == 'mes':
        anterior, siguiente = sumar_meses(dia, -1), sumar_meses(dia, 1)
    else:
        paso = timedelta(weeks=1) if modo == 'semana' else timedelta(days=1)
        anterior, siguiente = dia - paso, dia + paso
    inicio_visible, fin_visible = rango_visible(modo, dia)

    tonos = tonos_por_auxiliar(auxiliares)
    mostrados = [auxiliar] if auxiliar else auxiliares
    calendario = agenda_de_convocatoria(convocatoria, modo, dia, mostrados, tonos, solo_las_que_cubren=bool(auxiliar))
    for columna in calendario.get('columnas', []):
        columna['url_dia'] = url('dia', columna['fecha'])
    for semana in calendario.get('semanas', []):
        for dia_mes in semana:
            dia_mes['url_dia'] = url('dia', dia_mes['fecha'])

    programaciones = convocatoria.programacion_set.all()
    # Cobertura de todo el periodo, para el contador de visitas que ningún auxiliar cubre.
    periodo = Agenda(convocatoria, convocatoria.fecha_inicio, convocatoria.fecha_fin, auxiliares)
    dias_asignados = dict(
        convocatoria.asignaciones.values('auxiliar').annotate(dias=Count('fecha')).values_list('auxiliar', 'dias')
    )

    return {
        'convocatoria': convocatoria,
        'convocatorias_agrupadas': convocatorias_agrupadas(hoy),
        'otras_convocatorias': [
            {'convocatoria': otra, 'tono': tono_convocatoria(otra), 'url': _url_agenda(otra, modo, dia, auxiliar)}
            for otra in otras_convocatorias(inicio_visible, fin_visible, convocatoria)
        ],
        'estado_convocatoria': estado_convocatoria(convocatoria, hoy),
        'duracion': (convocatoria.fecha_fin - convocatoria.fecha_inicio).days + 1,
        'dias_restantes': (convocatoria.fecha_fin - hoy).days,
        'estados': resumen_estados(programaciones),
        'sin_cobertura': sum(not programacion.cubierta for programacion in periodo.programaciones),
        'escuelas_visitadas': programaciones.values('escuela').distinct().count(),
        'modo': modo,
        'dia': dia,
        'hoy': hoy,
        'auxiliar': auxiliar,
        'auxiliares': auxiliares,
        'calendario': calendario,
        'titulo_periodo': _titulo_periodo(modo, dia),
        'url_actual': url(modo, dia),
        # No se navega más allá del periodo de la convocatoria.
        'url_anterior': url(modo, anterior) if inicio_visible > convocatoria.fecha_inicio else None,
        'url_siguiente': url(modo, siguiente) if fin_visible < convocatoria.fecha_fin else None,
        'url_hoy': url(modo, hoy) if en_periodo else None,
        'url_primer_dia': url(modo, convocatoria.fecha_inicio),
        'modos': [(clave, etiqueta, url(clave, dia)) for clave, etiqueta in (('semana', 'Semana'), ('dia', 'Día'), ('mes', 'Mes'))],
        'leyenda': [
            {'auxiliar': aux, 'tono': tonos[aux.pk], 'dias': dias_asignados.get(aux.pk, 0)} for aux in auxiliares
        ],
    }


@permiso_requerido('programacion.view_programacion')
def programacionHomeView(request):
    seccion = request.GET.get('seccion')
    if seccion not in SECCIONES:
        seccion = 'calendario'

    contexto = {
        'seccion': seccion,
        'breadcrumbs': [
            {'name': 'Inicio', 'url': reverse('home')},
            {'name': 'Programación', 'url': reverse('home_programacion')},
        ],
    }
    form_media = ProgramacionForm().media
    if seccion == 'calendario':
        contexto.update(_contexto_agenda(request))
    elif seccion == 'programaciones':
        filtro_form, programaciones = _programaciones_filtradas(request)
        contexto.update({'filtro_form': filtro_form, 'programaciones': programaciones})
        form_media += filtro_form.media
    else:
        search, fecha_inicio, fecha_fin, convocatorias = _convocatorias_filtradas(request)
        contexto.update({
            'convocatorias': convocatorias, 'search': search,
            'fecha_inicio': fecha_inicio, 'fecha_fin': fecha_fin,
        })
    contexto['form_media'] = form_media
    return render(request, 'programacion/programacionHome.html', contexto)


@permiso_requerido('programacion.view_programacion')
def calendario_programaciones(request):
    """Ruta anterior del calendario: ahora es la sección principal de Programación."""
    return HttpResponseRedirect(reverse('home_programacion'))


@permiso_requerido('programacion.view_programacion')
def convocatoria_agenda(request, pk):
    """Enlace directo a una convocatoria: abre el calendario con ella elegida."""
    convocatoria = get_object_or_404(Convocatoria, pk=pk)
    return HttpResponseRedirect(f"{reverse('home_programacion')}?{urlencode({'convocatoria': convocatoria.pk})}")


# ---------------------------------------------------------------------------
# Impresión de la agenda: convocatoria, semana, día, hoja de ruta por auxiliar...
# ---------------------------------------------------------------------------

ALCANCES_IMPRESION = ('convocatoria', 'semana', 'dia', 'auxiliar', 'sin_cobertura', 'pendientes')


@permiso_requerido('programacion.view_programacion')
def agenda_imprimir(request):
    convocatoria = get_object_or_404(Convocatoria, pk=request.GET.get('convocatoria') or 0)
    alcance = request.GET.get('alcance')
    alcance = alcance if alcance in ALCANCES_IMPRESION else 'convocatoria'
    dia = _fecha(request.GET.get('fecha')) or convocatoria.fecha_inicio
    auxiliar = _por_id(Auxiliar, request.GET.get('auxiliar'))

    programaciones = convocatoria.programacion_set.select_related(
        'escuela__distrito',
    ).order_by('fecha_programada', ORDEN_JORNADA, 'escuela__nombre')
    inicio, fin = convocatoria.fecha_inicio, convocatoria.fecha_fin
    subtitulo = f"Del {date_format(inicio, FORMATO_FECHA)} al {date_format(fin, FORMATO_FECHA)}"

    if alcance == 'semana':
        semana_inicio, semana_fin = rango_visible('semana', dia)
        # La semana se recorta al periodo de la convocatoria.
        inicio, fin = max(semana_inicio, inicio), min(semana_fin, fin)
        subtitulo = f"Semana: {_titulo_periodo('semana', dia)}"
    elif alcance == 'dia':
        inicio = fin = dia
        subtitulo = capfirst(date_format(dia, FORMATO_DIA))
    elif alcance == 'auxiliar' and auxiliar:
        subtitulo = f"Hoja de ruta de {auxiliar.nombre} {auxiliar.apellido}"
    elif alcance == 'sin_cobertura':
        subtitulo = 'Visitas que ningún auxiliar cubre'
    elif alcance == 'pendientes':
        programaciones = programaciones.filter(estado='pendiente')
        subtitulo = 'Visitas pendientes'
    programaciones = list(programaciones.filter(fecha_programada__range=(inicio, fin)))

    # Quién cubre cada visita: los auxiliares asignados a su día cuyo horario incluye su jornada.
    cobertura = Agenda(convocatoria, inicio, fin, con_visitas=False)
    for programacion in programaciones:
        programacion.cubren = cobertura.cubren_visita(programacion)
        programacion.cubierta = cobertura.visita_cubierta(programacion)
    if alcance == 'auxiliar' and auxiliar:
        # Hoja de ruta: las visitas de las jornadas en que trabaja.
        programaciones = [programacion for programacion in programaciones if auxiliar in programacion.cubren]
    elif alcance == 'sin_cobertura':
        programaciones = [programacion for programacion in programaciones if not programacion.cubierta]

    por_dia = defaultdict(list)
    for programacion in programaciones:
        programacion.bloque = programacion.get_jornada_display()
        por_dia[programacion.fecha_programada].append(programacion)

    html_string = render_to_string('partials/agenda/reporte_pdf.html', {
        'convocatoria': convocatoria,
        'alcance': alcance,
        'subtitulo': subtitulo,
        'auxiliar': auxiliar if alcance == 'auxiliar' else None,
        'dias': [{'fecha': fecha, 'programaciones': lista} for fecha, lista in sorted(por_dia.items())],
        'total': len(programaciones),
        'estados': resumen_estados(programaciones),
        # La hoja de ruta lleva columnas para llenar a mano en campo.
        'para_campo': alcance in ('auxiliar', 'dia'),
        'fecha_impresion': timezone.localtime(),
    })
    pdf = HTML(string=html_string, base_url=request.build_absolute_uri('/')).write_pdf()

    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="programacion-{alcance}.pdf"'
    return response


@permiso_requerido('programacion.change_programacion')
def programacion_estado(request, pk):
    """Cambio rápido de estado desde el modal del calendario."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    programacion = get_object_or_404(Programacion, pk=pk)
    form = ProgramacionEstadoForm(request.POST, instance=programacion)
    if programacion.ya_empezo and form.is_valid():
        form.save()
    respuesta = HttpResponse('<div id="programacion-modal-wrapper"></div>')
    respuesta['HX-Trigger'] = EVENTO_AGENDA
    return respuesta


@permiso_requerido('programacion.view_programacion')
def buscar_programaciones(request):
    _, programaciones = _programaciones_filtradas(request)
    return render(request, 'partials/programacion/tabla.html', {
        'programaciones': programaciones,
    })


@permiso_requerido('programacion.add_programacion', 'programacion.change_programacion', cualquiera=True)
def programacion_cobertura(request):
    """Qué auxiliares asignados a ese día cubren la jornada elegida en el formulario."""
    return render(request, 'partials/programacion/_cobertura.html', _contexto_cobertura(
        _por_id(Convocatoria, request.GET.get('convocatoria')),
        _fecha(request.GET.get('fecha_programada')),
        _jornada(request.GET.get('jornada')),
    ))


def _contexto_cobertura(convocatoria, fecha, jornada):
    contexto = {'convocatoria': convocatoria, 'fecha_y_jornada_elegidas': bool(convocatoria and fecha and jornada)}
    if contexto['fecha_y_jornada_elegidas']:
        contexto['cubren'], contexto['cubierta'] = cubren_en_jornada(convocatoria, fecha, jornada)
    return contexto


def _jornada(valor):
    return valor if valor in Jornada.values else None


def _inicial_programacion(request):
    """Valores con que se abre el formulario desde un turno de la agenda."""
    inicial = {}
    fecha = _fecha(request.GET.get('fecha'))
    jornada = _jornada(request.GET.get('jornada'))
    if fecha:
        inicial['fecha_programada'] = fecha
    if jornada:
        inicial['jornada'] = jornada
    return inicial, fecha, jornada


@permiso_formulario('programacion.programacion')
def programacion_form(request, pk=None):
    instance = get_object_or_404(Programacion, pk=pk) if pk else None
    # Desde la agenda de una convocatoria, la visita queda fija a esa convocatoria.
    convocatoria_fija = None
    if _origen(request) == 'convocatoria':
        convocatoria_fija = instance.convocatoria if instance else _por_id(Convocatoria, request.GET.get('convocatoria'))

    convocatoria_actual = instance.convocatoria if instance else convocatoria_fija
    fecha_bloque = instance.fecha_programada if instance else None
    jornada_bloque = instance.jornada if instance else None

    if request.method == 'POST':
        form = ProgramacionForm(request.POST, instance=instance, convocatoria_fija=convocatoria_fija)
        convocatoria_actual = _por_id(Convocatoria, request.POST.get('convocatoria')) or convocatoria_actual
        if form.is_valid():
            form.save()
            programaciones = None if _desde_calendario(request) else _programaciones_filtradas(request)[1]
            return _respuesta_guardado(request, 'partials/programacion/modal_form_success.html', {
                'programaciones': programaciones,
            })
        fecha_bloque = form.cleaned_data.get('fecha_programada')
        jornada_bloque = form.cleaned_data.get('jornada')
    elif instance:
        form = ProgramacionForm(instance=instance, convocatoria_fija=convocatoria_fija)
    else:
        inicial, fecha_bloque, jornada_bloque = _inicial_programacion(request)
        form = ProgramacionForm(initial=inicial, convocatoria_fija=convocatoria_fija)

    return render(request, 'partials/programacion/modal_form.html', {
        'form': form,
        'instance': instance,
        'convocatoria_fija': convocatoria_fija,
        'estados_programacion': Programacion._meta.get_field('estado').choices,
        'desde_calendario': _desde_calendario(request),
        'fecha_bloque': fecha_bloque,
        'etiqueta_bloque': etiqueta_jornada(jornada_bloque) if jornada_bloque else None,
        **_contexto_cobertura(convocatoria_actual, fecha_bloque, jornada_bloque),
    })


@permiso_requerido('programacion.delete_programacion')
def programacion_eliminar(request, pk):
    instance = get_object_or_404(Programacion, pk=pk)
    if request.method == 'POST':
        instance.delete()
        programaciones = None if _desde_calendario(request) else _programaciones_filtradas(request)[1]
        return _respuesta_guardado(request, 'partials/programacion/modal_form_success.html', {
            'programaciones': programaciones,
        })
    return render(request, 'partials/programacion/modal_delete.html', {
        'instance': instance,
    })


@permiso_requerido('programacion.view_programacion')
def programacion_imprimir(request):
    _, programaciones = _programaciones_filtradas(request, paginar=False)
    html_string = render_to_string('partials/programacion/reporte_pdf.html', {
        'programaciones': programaciones,
        'fecha_generacion': timezone.localdate(),
    })
    pdf = HTML(string=html_string, base_url=request.build_absolute_uri('/')).write_pdf()
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="programaciones.pdf"'
    return response


def _auxiliares_filtrados(request):
    search = request.GET.get("q", "").strip()
    auxiliares = Auxiliar.objects.prefetch_related(
        Prefetch(
            'horario_set',
            queryset=Horario.objects.order_by('dia', ORDEN_JORNADA, 'fecha_inicio'),
            to_attr='horarios',
        ),
        Prefetch(
            'ausencia_set',
            queryset=Ausencia.objects.order_by('-fecha'),
            to_attr='ausencias',
        ),
    ).order_by('apellido', 'nombre')
    if search:
        auxiliares = auxiliares.filter(
            nombre__icontains=search
        ) | auxiliares.filter(
            apellido__icontains=search
        ) | auxiliares.filter(
            email__icontains=search
        ) | auxiliares.filter(
            institucion__icontains=search
        )

    return search, auxiliares


def _filtrar_auxiliares(request):
    search, auxiliares_list = _auxiliares_filtrados(request)

    paginator = Paginator(auxiliares_list, 20)
    auxiliares = paginator.get_page(request.GET.get("page"))

    return search, auxiliares


@permiso_requerido('programacion.view_auxiliar')
def auxiliarHomeView(request):
    search, auxiliares = _filtrar_auxiliares(request)

    return render(
        request,
        "auxiliar/auxiliarHome.html",
        {
            "auxiliares": auxiliares,
            "search": search,
            "form_media": HorarioForm().media + AusenciaForm().media,
        },
    )


@permiso_requerido('programacion.view_auxiliar')
def buscar_auxiliares(request):
    _, auxiliares = _filtrar_auxiliares(request)

    return render(
        request,
        "partials/tabla.html",
        {"auxiliares": auxiliares},
    )


@permiso_formulario('programacion.auxiliar')
def auxiliar_form(request, pk=None):
    instance = get_object_or_404(Auxiliar, pk=pk) if pk else None

    if request.method == "POST":
        form = AuxiliarForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            _, auxiliares = _filtrar_auxiliares(request)
            return render(
                request,
                "partials/auxiliar/modal_form_success.html",
                {"auxiliares": auxiliares},
            )
    else:
        form = AuxiliarForm(instance=instance)

    return render(
        request,
        "partials/auxiliar/modal_form.html",
        {"form": form, "instance": instance},
    )


@permiso_requerido('programacion.delete_auxiliar')
def auxiliar_eliminar(request, pk):
    instance = get_object_or_404(Auxiliar, pk=pk)

    if request.method == "POST":
        instance.delete()
        _, auxiliares = _filtrar_auxiliares(request)
        return render(
            request,
            "partials/auxiliar/modal_form_success.html",
            {"auxiliares": auxiliares},
        )

    return render(
        request,
        "partials/auxiliar/modal_delete.html",
        {"instance": instance},
    )


@permiso_formulario('programacion.horario')
def horario_form(request, pk=None):
    instance = get_object_or_404(Horario, pk=pk) if pk else None
    if request.method == "POST":
        form = HorarioForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            _, auxiliares = _filtrar_auxiliares(request)
            return render(
                request,
                "partials/horario/modal_form_success.html",
                {"auxiliares": auxiliares},
            )
    elif instance:
        form = HorarioForm(instance=instance)
    else:
        auxiliar_id = request.GET.get('auxiliar')
        inicial = {'auxiliar': auxiliar_id}
        # Lo usual es agregar más días al mismo periodo de labores: se propone el del último horario.
        ultimo = Horario.objects.filter(auxiliar_id=auxiliar_id).order_by('-fecha_fin').first() if auxiliar_id else None
        if ultimo:
            inicial.update(fecha_inicio=ultimo.fecha_inicio, fecha_fin=ultimo.fecha_fin)
        form = HorarioForm(initial=inicial)

    return render(
        request,
        "partials/horario/modal_form.html",
        {"form": form, "instance": instance},
    )


@permiso_requerido('programacion.delete_horario')
def horario_eliminar(request, pk):
    instance = get_object_or_404(Horario, pk=pk)
    if request.method == "POST":
        instance.delete()
        _, auxiliares = _filtrar_auxiliares(request)
        return render(
            request,
            "partials/horario/modal_form_success.html",
            {"auxiliares": auxiliares},
        )

    return render(
        request,
        "partials/horario/modal_delete.html",
        {"instance": instance},
    )


@permiso_requerido('programacion.view_auxiliar')
def auxiliar_imprimir(request):
    _, auxiliares = _auxiliares_filtrados(request)
    html_string = render_to_string(
        "partials/auxiliar/reporte_pdf.html",
        {"auxiliares": auxiliares},
    )
    pdf = HTML(
        string=html_string,
        base_url=request.build_absolute_uri("/"),
    ).write_pdf()

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="auxiliares.pdf"'
    return response


def _ausencias_filtradas(request, paginar=True):
    search = request.GET.get("q", "").strip()
    fecha = request.GET.get("fecha", "").strip()
    ausencias = Ausencia.objects.select_related('auxiliar').order_by('-fecha', 'auxiliar__apellido', 'auxiliar__nombre')
    if search:
        ausencias = ausencias.filter(
            auxiliar__nombre__icontains=search
        ) | ausencias.filter(
            auxiliar__apellido__icontains=search
        ) | ausencias.filter(
            motivo__icontains=search
        )
    if fecha_date := parse_date(fecha):
        ausencias = ausencias.filter(fecha=fecha_date)

    if paginar:
        paginator = Paginator(ausencias, 20)
        ausencias = paginator.get_page(request.GET.get('page'))
    return search, fecha, ausencias


def _auxiliares_con_ausencias(request):
    search = request.GET.get("q", "").strip()
    fecha = request.GET.get("fecha", "").strip()
    ausencias = Ausencia.objects.order_by('-fecha')

    auxiliares = Auxiliar.objects.prefetch_related(
        Prefetch('horario_set', queryset=Horario.objects.order_by('dia', ORDEN_JORNADA, 'fecha_inicio'), to_attr='horarios'),
        Prefetch('ausencia_set', queryset=ausencias, to_attr='ausencias'),
    ).order_by('apellido', 'nombre')

    if search:
        auxiliares = auxiliares.filter(
            Q(nombre__icontains=search)
            | Q(apellido__icontains=search)
            | Q(ausencia__motivo__icontains=search)
        ).distinct()
    if fecha_date := parse_date(fecha):
        auxiliares = auxiliares.filter(ausencia__fecha=fecha_date).distinct()

    paginator = Paginator(auxiliares, 20)
    return paginator.get_page(request.GET.get('page'))


@permiso_requerido('programacion.view_ausencia')
def ausenciaHomeView(request):
    search = request.GET.get("q", "").strip()
    fecha = request.GET.get("fecha", "").strip()
    auxiliares = _auxiliares_con_ausencias(request)
    return render(request, "ausencia/ausenciaHome.html", {
        "auxiliares": auxiliares,
        "search": search,
        "fecha": fecha,
        "form_media": AusenciaForm().media,
    })


@permiso_requerido('programacion.view_ausencia')
def buscar_ausencias(request):
    auxiliares = _auxiliares_con_ausencias(request)
    return render(request, "partials/ausencia/tabla.html", {"auxiliares": auxiliares})


@permiso_formulario('programacion.ausencia')
def ausencia_form(request, pk=None):
    instance = get_object_or_404(Ausencia, pk=pk) if pk else None
    origen_auxiliares = request.GET.get('origen') == 'auxiliares'
    auxiliar_seleccionado = instance.auxiliar if instance else None
    if request.method == "POST":
        if not auxiliar_seleccionado and request.POST.get('auxiliar'):
            auxiliar_seleccionado = Auxiliar.objects.filter(pk=request.POST.get('auxiliar')).first()
        form = AusenciaForm(request.POST, instance=instance, auxiliar=auxiliar_seleccionado)
        if form.is_valid():
            form.save()
            contexto = {'origen_auxiliares': origen_auxiliares}
            if origen_auxiliares:
                _, auxiliares = _filtrar_auxiliares(request)
                contexto['auxiliares'] = auxiliares
            else:
                contexto['auxiliares'] = _auxiliares_con_ausencias(request)
            return render(request, "partials/ausencia/modal_form_success.html", contexto)
    else:
        auxiliar_id = request.GET.get('auxiliar') if not instance else None
        if auxiliar_id:
            auxiliar_seleccionado = Auxiliar.objects.filter(pk=auxiliar_id).first()
        form = AusenciaForm(
            instance=instance,
            initial={'auxiliar': auxiliar_id},
            auxiliar=auxiliar_seleccionado,
        )
    return render(request, "partials/ausencia/modal_form.html", {
        "form": form,
        "instance": instance,
        "auxiliar_seleccionado": auxiliar_seleccionado,
    })


@permiso_requerido('programacion.delete_ausencia')
def ausencia_eliminar(request, pk):
    instance = get_object_or_404(Ausencia, pk=pk)
    if request.method == "POST":
        instance.delete()
        origen_auxiliares = request.GET.get('origen') == 'auxiliares'
        contexto = {'origen_auxiliares': origen_auxiliares}
        if origen_auxiliares:
            _, auxiliares = _filtrar_auxiliares(request)
            contexto['auxiliares'] = auxiliares
        else:
            contexto['auxiliares'] = _auxiliares_con_ausencias(request)
        return render(request, "partials/ausencia/modal_form_success.html", contexto)
    return render(request, "partials/ausencia/modal_delete.html", {"instance": instance})


@permiso_requerido('programacion.view_ausencia')
def ausencia_imprimir(request):
    _, _, ausencias = _ausencias_filtradas(request, paginar=False)
    html_string = render_to_string("partials/ausencia/reporte_pdf.html", {"ausencias": ausencias})
    pdf = HTML(string=html_string, base_url=request.build_absolute_uri("/")).write_pdf()
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="ausencias.pdf"'
    return response


def _convocatorias_filtradas(request, paginar=True):
    search = request.GET.get("q", "").strip()
    fecha_inicio = request.GET.get("fecha_inicio", "").strip()
    fecha_fin = request.GET.get("fecha_fin", "").strip()
    convocatorias = Convocatoria.objects.all().order_by('fecha_inicio')
    if search:
        convocatorias = convocatorias.filter(
            nombre__icontains=search
        ) | convocatorias.filter(
            descripcion__icontains=search
        )
    if fecha_inicio_date := parse_date(fecha_inicio):
        convocatorias = convocatorias.filter(fecha_inicio__gte=fecha_inicio_date)
    if fecha_fin_date := parse_date(fecha_fin):
        convocatorias = convocatorias.filter(fecha_fin__lte=fecha_fin_date)

    if paginar:
        paginator = Paginator(convocatorias, 20)
        convocatorias = paginator.get_page(request.GET.get('page'))
    return search, fecha_inicio, fecha_fin, convocatorias

@permiso_requerido('programacion.view_convocatoria')
def convocatoriasHomeView(request):
    """Ruta anterior de convocatorias: ahora es una sección de Programación."""
    return HttpResponseRedirect(f"{reverse('home_programacion')}?seccion=convocatorias")


@permiso_requerido('programacion.view_convocatoria')
def buscar_convocatorias(request):
    _, _, _, convocatorias = _convocatorias_filtradas(request)
    return render(
        request,
        "partials/convocatorias/tabla.html",
        {"convocatorias": convocatorias},
    )


@permiso_formulario('programacion.convocatoria')
def convocatoria_form(request, pk=None):
    instance = get_object_or_404(Convocatoria, pk=pk) if pk else None

    if request.method == "POST":
        form = ConvocatoriaForm(request.POST, instance=instance)
        if form.is_valid():
            convocatoria = form.save()
            if instance is None and _desde_calendario(request):
                # Recién creada, lo siguiente es asignarle programaciones en su agenda.
                return _redirigir_htmx(f"{reverse('home_programacion')}?{urlencode({'convocatoria': convocatoria.pk})}")
            convocatorias = None if _desde_calendario(request) else _convocatorias_filtradas(request)[3]
            return _respuesta_guardado(request, "partials/convocatorias/modal_form_success.html", {
                "convocatorias": convocatorias,
            })
    else:
        fecha_inicio = _fecha(request.GET.get("fecha"))
        form = ConvocatoriaForm(
            instance=instance,
            initial={"fecha_inicio": fecha_inicio} if fecha_inicio and not instance else None,
        )

    return render(
        request,
        "partials/convocatorias/modal_form.html",
        {"form": form, "instance": instance},
    )


@permiso_requerido('programacion.add_convocatoriaauxiliar', 'programacion.delete_convocatoriaauxiliar')
def convocatoria_dia_auxiliares(request, pk):
    """Asignar auxiliares a un día de la convocatoria (solo los que tienen horario ese día)."""
    convocatoria = get_object_or_404(Convocatoria, pk=pk)
    fecha = _fecha(request.GET.get('fecha'))
    if not fecha or not convocatoria.fecha_inicio <= fecha <= convocatoria.fecha_fin:
        return HttpResponse('El día debe estar dentro de las fechas de la convocatoria.', status=400)

    if request.method == "POST":
        form = AsignarAuxiliaresDiaForm(request.POST, convocatoria=convocatoria, fecha=fecha)
        if form.is_valid():
            form.save()
            return _respuesta_guardado(request, "partials/convocatorias/modal_form_success.html", {"convocatorias": None})
    else:
        form = AsignarAuxiliaresDiaForm(convocatoria=convocatoria, fecha=fecha)
    return render(request, "partials/agenda/modal_asignar_auxiliares.html", {
        "form": form, "convocatoria": convocatoria, "fecha": fecha,
    })


@permiso_requerido('programacion.delete_convocatoria')
def convocatoria_eliminar(request, pk):
    instance = get_object_or_404(Convocatoria, pk=pk)

    if request.method == "POST":
        instance.delete()
        if _origen(request) == "convocatoria":
            # Se estaba dentro de su agenda, que ya no existe.
            return _redirigir_htmx(reverse("home_programacion"))
        convocatorias = None if _desde_calendario(request) else _convocatorias_filtradas(request)[3]
        return _respuesta_guardado(request, "partials/convocatorias/modal_form_success.html", {
            "convocatorias": convocatorias,
        })

    return render(
        request,
        "partials/convocatorias/modal_delete.html",
        {"instance": instance, "total_programaciones": instance.programacion_set.count()},
    )


@permiso_requerido('programacion.view_convocatoria')
def convocatoria_imprimir(request):
    _, _, _, convocatorias = _convocatorias_filtradas(request, paginar=False)
    html_string = render_to_string(
        "partials/convocatorias/reporte_pdf.html",
        {"convocatorias": convocatorias},
    )
    pdf = HTML(
        string=html_string,
        base_url=request.build_absolute_uri("/"),
    ).write_pdf()

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="convocatorias.pdf"'
    return response