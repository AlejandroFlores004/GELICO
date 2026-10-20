from urllib.parse import urlencode

from django.contrib import messages
from django.http import HttpResponse, HttpResponseNotAllowed, HttpResponseRedirect
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date

from main.pdf import datos_filtro, respuesta_pdf
from main.permisos import permiso_formulario, permiso_requerido
from . import services
from .agenda import (
    MODOS, agenda_de_convocatoria, auxiliares_asignados, con_conteos, convocatoria_por_defecto, convocatorias_agrupadas,
    cubren_en_jornada, etiqueta_jornada, otras_convocatorias, rango_visible, tono_convocatoria, tonos_por_auxiliar,
)

from .forms import (
    AuxiliarForm, AuxiliaresDelDia, AusenciaForm, ConvocatoriaForm, FiltrarAuxiliaresForm, HorarioForm, ProgramacionEstadoForm,
    ProgramacionFiltroForm, ProgramacionForm,
)
from .models import Auxiliar, Ausencia, Convocatoria, Horario, Jornada, Programacion


def _programaciones_filtradas(request, paginar=True):
    filtro_form = ProgramacionFiltroForm(request.GET or None)
    programaciones = services.filtrar_programaciones(datos_filtro(filtro_form))

    if paginar:
        paginator = Paginator(programaciones, 20)
        programaciones = paginator.get_page(request.GET.get('page'))
    return filtro_form, programaciones


SECCIONES = ('calendario', 'convocatorias', 'programaciones')
# Evento htmx que los calendarios escuchan para volver a pintarse tras guardar algo en un modal.
EVENTO_AGENDA = 'agenda-actualizada'


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

    anterior, siguiente = services.fechas_vecinas(modo, dia)
    inicio_visible, fin_visible = rango_visible(modo, dia)

    tonos = tonos_por_auxiliar(auxiliares)
    mostrados = [auxiliar] if auxiliar else auxiliares
    calendario = agenda_de_convocatoria(convocatoria, modo, dia, mostrados, tonos, solo_las_que_cubren=bool(auxiliar))
    for columna in calendario.get('columnas', []):
        columna['url_dia'] = url('dia', columna['fecha'])
    for semana in calendario.get('semanas', []):
        for dia_mes in semana:
            dia_mes['url_dia'] = url('dia', dia_mes['fecha'])

    dias_asignados = services.dias_asignados_por_auxiliar(convocatoria)

    return {
        'convocatoria': convocatoria,
        'convocatorias_agrupadas': convocatorias_agrupadas(hoy),
        'otras_convocatorias': [
            {'convocatoria': otra, 'tono': tono_convocatoria(otra), 'url': _url_agenda(otra, modo, dia, auxiliar)}
            for otra in otras_convocatorias(inicio_visible, fin_visible, convocatoria)
        ],
        **services.resumen_convocatoria(convocatoria, auxiliares, hoy),
        'modo': modo,
        'dia': dia,
        'hoy': hoy,
        'auxiliar': auxiliar,
        'auxiliares': auxiliares,
        'calendario': calendario,
        'titulo_periodo': services.titulo_periodo(modo, dia),
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

@permiso_requerido('programacion.view_programacion')
def agenda_imprimir(request):
    convocatoria = get_object_or_404(Convocatoria, pk=request.GET.get('convocatoria') or 0)
    alcance = request.GET.get('alcance')
    alcance = alcance if alcance in services.ALCANCES_IMPRESION else 'convocatoria'
    dia = _fecha(request.GET.get('fecha')) or convocatoria.fecha_inicio
    auxiliar = _por_id(Auxiliar, request.GET.get('auxiliar'))

    return respuesta_pdf(
        request, 'partials/agenda/reporte_pdf.html',
        services.reporte_agenda(convocatoria, alcance, dia, auxiliar),
        f'programacion-{alcance}.pdf',
    )


@permiso_requerido('programacion.view_programacion')
def programacion_detalle(request, pk):
    """Detalle de una visita al hacer clic en su código en la agenda."""
    programacion = get_object_or_404(Programacion.objects.select_related('convocatoria', 'escuela__distrito'), pk=pk)
    cubren, cubierta = services.cobertura_de_visita(programacion)
    return render(request, 'partials/programacion/modal_detalle.html', {
        'programacion': programacion,
        'cubren': cubren,
        'cubierta': cubierta,
        'estados_programacion': Programacion._meta.get_field('estado').choices,
    })


@permiso_requerido('programacion.change_programacion')
def programacion_estado(request, pk):
    """Cambio rápido de estado desde el modal del calendario."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    programacion = get_object_or_404(Programacion, pk=pk)
    form = ProgramacionEstadoForm(request.POST, instance=programacion)
    if programacion.ya_empezo and form.is_valid():
        form.save()
        messages.success(request, f'Visita a {programacion.escuela.nombre_corto} marcada como «{programacion.get_estado_display()}».')
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
            programacion = form.save()
            accion = 'programó' if instance is None else 'actualizó'
            messages.success(request, f'Se {accion} la visita a {programacion.escuela.nombre_corto}.')
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
        messages.success(request, f'Se eliminó la visita a {instance.escuela.nombre_corto}.')
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
    return respuesta_pdf(
        request, 'partials/programacion/reporte_pdf.html',
        {'programaciones': programaciones}, 'programaciones.pdf',
    )


def _auxiliares_filtrados(request):
    """Auxiliares filtrados, sin paginar (los usa el listado y el "Imprimir")."""
    filtro_form = FiltrarAuxiliaresForm(request.GET or None)
    return filtro_form, services.filtrar_auxiliares(datos_filtro(filtro_form))


def _filtrar_auxiliares(request):
    filtro_form, auxiliares_list = _auxiliares_filtrados(request)

    paginator = Paginator(auxiliares_list, 20)
    auxiliares = paginator.get_page(request.GET.get("page"))
    services.con_estado_horario(auxiliares)

    return filtro_form, auxiliares


@permiso_requerido('programacion.view_auxiliar')
def auxiliarHomeView(request):
    filtro_form, auxiliares = _filtrar_auxiliares(request)

    return render(
        request,
        "auxiliar/auxiliarHome.html",
        {
            "auxiliares": auxiliares,
            "filtro_form": filtro_form,
            "form_media": HorarioForm().media + filtro_form.media,
            "breadcrumbs": [
                {"name": "Inicio", "url": reverse("home")},
                {"name": "Auxiliares"},
            ],
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
            auxiliar = form.save()
            accion = 'registró' if instance is None else 'actualizó'
            messages.success(request, f'Se {accion} al auxiliar {auxiliar.nombre} {auxiliar.apellido}.')
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
        messages.success(request, f'Se eliminó al auxiliar {instance.nombre} {instance.apellido}.')
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
            # Al crear se guarda un horario por cada día elegido (save devuelve la lista).
            guardados = form.save()
            auxiliar = form.cleaned_data['auxiliar']
            if instance is None:
                dias = len(guardados)
                messages.success(request, f"Se agregó el horario de {auxiliar.nombre} {auxiliar.apellido} ({dias} día{'s' if dias != 1 else ''}).")
            else:
                messages.success(request, f'Se actualizó el horario de {auxiliar.nombre} {auxiliar.apellido}.')
            _, auxiliares = _filtrar_auxiliares(request)
            return render(
                request,
                "partials/horario/modal_form_success.html",
                {"auxiliares": auxiliares},
            )
    elif instance:
        form = HorarioForm(instance=instance)
    else:
        form = HorarioForm(initial=services.horario_inicial(request.GET.get('auxiliar')))

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
        messages.success(request, f'Se eliminó el horario de {instance.auxiliar.nombre} {instance.auxiliar.apellido}.')
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
    return respuesta_pdf(request, "partials/auxiliar/reporte_pdf.html", {"auxiliares": auxiliares}, "auxiliares.pdf")


def _ausencias_filtradas(request):
    """Ausencias filtradas, sin paginar (las usa el "Imprimir")."""
    search = request.GET.get("q", "").strip()
    return services.filtrar_ausencias(search, _fecha(request.GET.get("fecha", "").strip()))


def _auxiliares_con_ausencias(request):
    search = request.GET.get("q", "").strip()
    auxiliares = services.auxiliares_con_ausencias(search, _fecha(request.GET.get("fecha", "").strip()))
    return Paginator(auxiliares, 20).get_page(request.GET.get('page'))


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
        "breadcrumbs": [
            {"name": "Inicio", "url": reverse("home")},
            {"name": "Ausencias"},
        ],
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
            ausencia = form.save()
            accion = 'registró' if instance is None else 'actualizó'
            messages.success(request, f'Se {accion} la ausencia de {ausencia.auxiliar.nombre} {ausencia.auxiliar.apellido}.')
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
        messages.success(request, f'Se eliminó la ausencia de {instance.auxiliar.nombre} {instance.auxiliar.apellido}.')
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
    return respuesta_pdf(
        request, "partials/ausencia/reporte_pdf.html", {"ausencias": _ausencias_filtradas(request)}, "ausencias.pdf",
    )


def _convocatorias_filtradas(request, paginar=True):
    search = request.GET.get("q", "").strip()
    fecha_inicio = request.GET.get("fecha_inicio", "").strip()
    fecha_fin = request.GET.get("fecha_fin", "").strip()
    convocatorias = services.filtrar_convocatorias(search, _fecha(fecha_inicio), _fecha(fecha_fin))

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
            accion = 'creó' if instance is None else 'actualizó'
            messages.success(request, f'Se {accion} la convocatoria {convocatoria.nombre}.')
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


# Acciones del modal de auxiliares de un día y el permiso extra que pide cada una
# (agregar y quitar ya los exige el decorador de la vista).
ACCIONES_DIA = {
    'agregar': None,
    'quitar': None,
    'no_llego': 'programacion.add_ausencia',
    'si_llego': 'programacion.delete_ausencia',
}
MENSAJES_DIA = {
    'agregar': 'Auxiliar asignado al día.',
    'quitar': 'Auxiliar quitado del día.',
    'no_llego': 'Se registró que el auxiliar no llegó.',
    'si_llego': 'Se quitó la inasistencia del auxiliar.',
}


@permiso_requerido('programacion.add_convocatoriaauxiliar', 'programacion.delete_convocatoriaauxiliar')
def convocatoria_dia_auxiliares(request, pk):
    """Agregar y quitar auxiliares de un día de la convocatoria, y registrar si no llegaron. Cada acción
    se guarda al momento: se vuelve a pintar la lista del modal (que sigue abierto) y se avisa a la
    agenda para refrescarse."""
    convocatoria = get_object_or_404(Convocatoria, pk=pk)
    fecha = _fecha(request.GET.get('fecha'))
    if not fecha or not convocatoria.fecha_inicio <= fecha <= convocatoria.fecha_fin:
        return HttpResponse('El día debe estar dentro de las fechas de la convocatoria.', status=400)
    del_dia = AuxiliaresDelDia(convocatoria, fecha)

    contexto = {"convocatoria": convocatoria, "fecha": fecha, "del_dia": del_dia}
    if request.method == "POST":
        error = None
        # Cada botón manda una sola acción con el id del auxiliar: {"agregar": id}, {"no_llego": id}...
        accion = next((nombre for nombre in ACCIONES_DIA if request.POST.get(nombre, '').isdigit()), None)
        auxiliar_id = int(request.POST[accion]) if accion else None
        permiso = ACCIONES_DIA.get(accion)
        if permiso and not request.user.has_perm(permiso):
            raise PermissionDenied
        if accion == 'agregar':
            error = del_dia.agregar(auxiliar_id)
        elif accion == 'quitar':
            del_dia.quitar(auxiliar_id)
        elif accion == 'no_llego':
            error = del_dia.registrar_inasistencia(auxiliar_id, request.POST.get('motivo', ''))
        elif accion == 'si_llego':
            del_dia.quitar_inasistencia(auxiliar_id)
        contexto['asignados'], contexto['disponibles'] = del_dia.opciones()
        respuesta = render(request, "partials/agenda/_asignar_auxiliares_lista.html", {**contexto, "error": error})
        if not error:
            if accion:
                messages.success(request, MENSAJES_DIA[accion])
            respuesta['HX-Trigger'] = EVENTO_AGENDA
        return respuesta

    contexto['asignados'], contexto['disponibles'] = del_dia.opciones()
    return render(request, "partials/agenda/modal_asignar_auxiliares.html", contexto)


@permiso_requerido('programacion.delete_convocatoria')
def convocatoria_eliminar(request, pk):
    instance = get_object_or_404(Convocatoria, pk=pk)

    if request.method == "POST":
        instance.delete()
        messages.success(request, f'Se eliminó la convocatoria {instance.nombre}.')
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
    return respuesta_pdf(
        request, "partials/convocatorias/reporte_pdf.html", {"convocatorias": convocatorias}, "convocatorias.pdf",
    )