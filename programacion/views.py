from calendar import Calendar
from collections import defaultdict
from datetime import timedelta
from urllib.parse import urlencode

from django.http import HttpResponse, HttpResponseNotAllowed, HttpResponseRedirect
from django.core.paginator import Paginator
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_time
from django.utils.formats import date_format
from django.utils.text import capfirst
from weasyprint import HTML

from .agenda import (
    MODOS, agenda_de_convocatoria, con_conteos, convocatoria_por_defecto, convocatorias_agrupadas,
    disponibles_en_bloque, estado_convocatoria, etiqueta_bloque, otras_convocatorias, rango_visible,
    resumen_estados, sumar_meses, tono_convocatoria, tonos_por_auxiliar,
)

from .forms import AuxiliarForm, AusenciaForm, ConvocatoriaForm, HorarioForm, ProgramacionEstadoForm, ProgramacionFiltroForm, ProgramacionForm
from .models import Auxiliar, Ausencia, Convocatoria, Horario, Programacion


def _programaciones_filtradas(request, paginar=True):
    filtro_form = ProgramacionFiltroForm(request.GET or None)
    programaciones = Programacion.objects.select_related(
        'convocatoria', 'auxiliar', 'escuela'
    ).order_by('-fecha_programada', '-hora_programada')

    if filtro_form.is_valid():
        search = filtro_form.cleaned_data.get('q', '').strip()
        convocatoria = filtro_form.cleaned_data.get('convocatoria')
        escuela = filtro_form.cleaned_data.get('escuela')
        auxiliar = filtro_form.cleaned_data.get('auxiliar')

        if convocatoria:
            programaciones = programaciones.filter(convocatoria=convocatoria)
        if escuela:
            programaciones = programaciones.filter(escuela=escuela)
        if auxiliar:
            programaciones = programaciones.filter(auxiliar=auxiliar)
        if search:
            programaciones = programaciones.filter(
                Q(convocatoria__nombre__icontains=search)
                | Q(auxiliar__nombre__icontains=search)
                | Q(auxiliar__apellido__icontains=search)
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
# Calendario: agenda semanal por bloques de la convocatoria elegida
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
    auxiliar = _por_id(Auxiliar, request.GET.get('auxiliar'))

    def url(modo_destino, dia_destino):
        return _url_agenda(convocatoria, modo_destino, dia_destino, auxiliar)

    if modo == 'mes':
        anterior, siguiente = sumar_meses(dia, -1), sumar_meses(dia, 1)
    else:
        paso = timedelta(weeks=1) if modo == 'semana' else timedelta(days=1)
        anterior, siguiente = dia - paso, dia + paso
    inicio_visible, fin_visible = rango_visible(modo, dia)

    auxiliares = list(Auxiliar.objects.order_by('apellido', 'nombre'))
    tonos = tonos_por_auxiliar(auxiliares)
    mostrados = [auxiliar] if auxiliar else auxiliares
    calendario = agenda_de_convocatoria(convocatoria, modo, dia, mostrados, tonos, incluir_sin_auxiliar=not auxiliar)
    for columna in calendario.get('columnas', []):
        columna['url_dia'] = url('dia', columna['fecha'])
    for semana in calendario.get('semanas', []):
        for dia_mes in semana:
            dia_mes['url_dia'] = url('dia', dia_mes['fecha'])

    programaciones = convocatoria.programacion_set.all()
    columnas_por_auxiliar = modo == 'dia' and any(c['auxiliar'] for c in calendario.get('columnas', []))

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
        'auxiliares_asignados': programaciones.exclude(auxiliar=None).values('auxiliar').distinct().count(),
        'sin_auxiliar': programaciones.filter(auxiliar=None).count(),
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
        'leyenda': [{'auxiliar': aux, 'tono': tonos[aux.pk]} for aux in mostrados],
        'mostrar_auxiliar': len(mostrados) > 1 and not columnas_por_auxiliar,
    }


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


def calendario_programaciones(request):
    """Ruta anterior del calendario: ahora es la sección principal de Programación."""
    return HttpResponseRedirect(reverse('home_programacion'))


def convocatoria_agenda(request, pk):
    """Enlace directo a una convocatoria: abre el calendario con ella elegida."""
    convocatoria = get_object_or_404(Convocatoria, pk=pk)
    return HttpResponseRedirect(f"{reverse('home_programacion')}?{urlencode({'convocatoria': convocatoria.pk})}")


# ---------------------------------------------------------------------------
# Impresión de la agenda: convocatoria, semana, día, hoja de ruta por auxiliar...
# ---------------------------------------------------------------------------

ALCANCES_IMPRESION = ('convocatoria', 'semana', 'dia', 'auxiliar', 'sin_auxiliar', 'pendientes')


def agenda_imprimir(request):
    convocatoria = get_object_or_404(Convocatoria, pk=request.GET.get('convocatoria') or 0)
    alcance = request.GET.get('alcance')
    alcance = alcance if alcance in ALCANCES_IMPRESION else 'convocatoria'
    dia = _fecha(request.GET.get('fecha')) or convocatoria.fecha_inicio
    auxiliar = _por_id(Auxiliar, request.GET.get('auxiliar'))

    programaciones = convocatoria.programacion_set.select_related(
        'auxiliar', 'escuela__distrito',
    ).order_by('fecha_programada', 'hora_programada', 'escuela__nombre')
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
        programaciones = programaciones.filter(auxiliar=auxiliar)
        subtitulo = f"Hoja de ruta de {auxiliar.nombre} {auxiliar.apellido}"
    elif alcance == 'sin_auxiliar':
        programaciones = programaciones.filter(auxiliar=None)
        subtitulo = 'Visitas sin auxiliar asignado'
    elif alcance == 'pendientes':
        programaciones = programaciones.filter(estado='pendiente')
        subtitulo = 'Visitas pendientes'
    programaciones = list(programaciones.filter(fecha_programada__range=(inicio, fin)))

    por_dia = defaultdict(list)
    for programacion in programaciones:
        programacion.bloque = etiqueta_bloque(programacion.hora_programada)
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


def buscar_programaciones(request):
    _, programaciones = _programaciones_filtradas(request)
    return render(request, 'partials/programacion/tabla.html', {
        'programaciones': programaciones,
    })


def _auxiliar_horarios_contexto(auxiliar, mes_parametro=None, convocatoria=None):
    mes_actual = parse_date(f'{mes_parametro}-01') if mes_parametro else None
    if mes_actual is None:
        mes_actual = timezone.localdate().replace(day=1)
    else:
        mes_actual = mes_actual.replace(day=1)

    if mes_actual.month == 1:
        mes_anterior = mes_actual.replace(year=mes_actual.year - 1, month=12)
    else:
        mes_anterior = mes_actual.replace(month=mes_actual.month - 1)
    if mes_actual.month == 12:
        mes_siguiente = mes_actual.replace(year=mes_actual.year + 1, month=1)
    else:
        mes_siguiente = mes_actual.replace(month=mes_actual.month + 1)

    horarios = Horario.objects.filter(
        auxiliar=auxiliar,
        fecha__gte=mes_actual,
        fecha__lt=mes_siguiente,
    ).order_by('fecha', 'hora_inicio') if auxiliar else Horario.objects.none()
    horarios_por_fecha = defaultdict(list)
    for horario in horarios:
        horarios_por_fecha[horario.fecha].append(horario)

    calendario_horarios = [
        [
            {
                'fecha': fecha,
                'en_mes': fecha.month == mes_actual.month,
                'horarios': horarios_por_fecha[fecha],
                'en_periodo_convocatoria': bool(
                    convocatoria
                    and convocatoria.fecha_inicio <= fecha <= convocatoria.fecha_fin
                ),
                'inicio_convocatoria': bool(
                    convocatoria and fecha == convocatoria.fecha_inicio
                ),
                'fin_convocatoria': bool(
                    convocatoria and fecha == convocatoria.fecha_fin
                ),
            }
            for fecha in semana
        ]
        for semana in Calendar(firstweekday=6).monthdatescalendar(
            mes_actual.year, mes_actual.month
        )
    ]
    nombres_meses = (
        'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
        'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
    )
    return {
        'auxiliar': auxiliar,
        'convocatoria': convocatoria,
        'calendario_horarios': calendario_horarios,
        'mes_actual': mes_actual.strftime('%Y-%m'),
        'mes_anterior': mes_anterior.strftime('%Y-%m'),
        'mes_siguiente': mes_siguiente.strftime('%Y-%m'),
        'mes_titulo': f'{nombres_meses[mes_actual.month - 1].capitalize()} {mes_actual.year}',
    }


def programacion_auxiliar_horario(request):
    auxiliar_id = request.GET.get('auxiliar')
    convocatoria_id = request.GET.get('convocatoria')
    auxiliar = Auxiliar.objects.filter(pk=auxiliar_id).first() if auxiliar_id else None
    convocatoria = Convocatoria.objects.filter(pk=convocatoria_id).first() if convocatoria_id else None
    return render(request, 'partials/programacion/auxiliar_horarios.html', _auxiliar_horarios_contexto(
        auxiliar,
        request.GET.get('mes'),
        convocatoria,
    ))


def _inicial_programacion(request):
    """Valores con que se abre el formulario desde un bloque de la agenda."""
    inicial = {}
    fecha = _fecha(request.GET.get('fecha'))
    hora = parse_time(request.GET.get('hora') or '') if request.GET.get('hora') else None
    auxiliar = _por_id(Auxiliar, request.GET.get('auxiliar'))
    if fecha:
        inicial['fecha_programada'] = fecha
    if hora:
        inicial['hora_programada'] = hora
    if auxiliar:
        inicial['auxiliar'] = auxiliar.pk
    return inicial, auxiliar, fecha, hora


def programacion_form(request, pk=None):
    instance = get_object_or_404(Programacion, pk=pk) if pk else None
    # Desde la agenda de una convocatoria, la visita queda fija a esa convocatoria.
    convocatoria_fija = None
    if _origen(request) == 'convocatoria':
        convocatoria_fija = instance.convocatoria if instance else _por_id(Convocatoria, request.GET.get('convocatoria'))

    auxiliar_actual = instance.auxiliar if instance else None
    convocatoria_actual = instance.convocatoria if instance else convocatoria_fija
    mes_horarios = instance.fecha_programada.strftime('%Y-%m') if instance else None
    fecha_bloque = instance.fecha_programada if instance else None
    hora_bloque = instance.hora_programada if instance else None

    if request.method == 'POST':
        form = ProgramacionForm(request.POST, instance=instance, convocatoria_fija=convocatoria_fija)
        auxiliar_id = request.POST.get('auxiliar')
        convocatoria_id = request.POST.get('convocatoria')
        mes_horarios = request.POST.get('mes') or mes_horarios
        if auxiliar_id:
            auxiliar_actual = Auxiliar.objects.filter(pk=auxiliar_id).first()
        if convocatoria_id:
            convocatoria_actual = Convocatoria.objects.filter(pk=convocatoria_id).first()
        if form.is_valid():
            form.save()
            programaciones = None if _desde_calendario(request) else _programaciones_filtradas(request)[1]
            return _respuesta_guardado(request, 'partials/programacion/modal_form_success.html', {
                'programaciones': programaciones,
            })
        fecha_bloque = form.cleaned_data.get('fecha_programada')
        hora_bloque = form.cleaned_data.get('hora_programada')
    elif instance:
        form = ProgramacionForm(instance=instance, convocatoria_fija=convocatoria_fija)
    else:
        inicial, auxiliar_actual, fecha_bloque, hora_bloque = _inicial_programacion(request)
        form = ProgramacionForm(initial=inicial, convocatoria_fija=convocatoria_fija)
        if fecha_bloque:
            mes_horarios = fecha_bloque.strftime('%Y-%m')

    return render(request, 'partials/programacion/modal_form.html', {
        'form': form,
        'instance': instance,
        'convocatoria_fija': convocatoria_fija,
        'estados_programacion': Programacion._meta.get_field('estado').choices,
        'desde_calendario': _desde_calendario(request),
        'fecha_bloque': fecha_bloque,
        'etiqueta_bloque': etiqueta_bloque(hora_bloque) if hora_bloque else None,
        'disponibles_bloque': (
            disponibles_en_bloque(fecha_bloque, hora_bloque, excluir=instance)
            if fecha_bloque and hora_bloque else None
        ),
        **_auxiliar_horarios_contexto(auxiliar_actual, mes_horarios, convocatoria_actual),
    })


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
            queryset=Horario.objects.order_by('-fecha', 'hora_inicio'),
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


def buscar_auxiliares(request):
    _, auxiliares = _filtrar_auxiliares(request)

    return render(
        request,
        "partials/tabla.html",
        {"auxiliares": auxiliares},
    )


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
        form = HorarioForm(initial={'auxiliar': auxiliar_id})

    return render(
        request,
        "partials/horario/modal_form.html",
        {"form": form, "instance": instance},
    )


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
        Prefetch('horario_set', queryset=Horario.objects.order_by('-fecha', 'hora_inicio'), to_attr='horarios'),
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


def buscar_ausencias(request):
    auxiliares = _auxiliares_con_ausencias(request)
    return render(request, "partials/ausencia/tabla.html", {"auxiliares": auxiliares})


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

def convocatoriasHomeView(request):
    """Ruta anterior de convocatorias: ahora es una sección de Programación."""
    return HttpResponseRedirect(f"{reverse('home_programacion')}?seccion=convocatorias")


def buscar_convocatorias(request):
    _, _, _, convocatorias = _convocatorias_filtradas(request)
    return render(
        request,
        "partials/convocatorias/tabla.html",
        {"convocatorias": convocatorias},
    )


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