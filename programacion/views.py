from datetime import timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.http import HttpResponse, HttpResponseNotAllowed, HttpResponseRedirect
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from main.pdf import datos_filtro, respuesta_pdf
from main.permisos import permiso_formulario, permiso_requerido
from . import services
from .agenda import (
    MODOS, agenda_de_convocatoria, personal_asignado, con_conteos, convocatoria_por_defecto, convocatorias_agrupadas,
    cubren_en_jornada, etiqueta_jornada, otras_convocatorias, rango_visible, tono_convocatoria, tonos_por_persona,
)

from .forms import (
    PersonalForm, PersonalDelDia, ConvocatoriaForm, FiltrarAsistenciaForm, FiltrarPersonalForm, HorarioForm, ProgramacionEstadoForm,
    ProgramacionFiltroForm, ProgramacionForm,
)
from .models import Asistencia, Personal, Convocatoria, Horario, Jornada, Programacion


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

def _url_agenda(convocatoria, modo, dia, persona=None):
    parametros = {'convocatoria': convocatoria.pk, 'modo': modo, 'fecha': dia.isoformat()}
    if persona:
        parametros['persona'] = persona.pk
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
    personas = list(personal_asignado(convocatoria))
    # Solo se filtra por personas asignadas a algún día de la convocatoria.
    persona = next((a for a in personas if str(a.pk) == request.GET.get('persona')), None)

    def url(modo_destino, dia_destino):
        return _url_agenda(convocatoria, modo_destino, dia_destino, persona)

    anterior, siguiente = services.fechas_vecinas(modo, dia)
    inicio_visible, fin_visible = rango_visible(modo, dia)

    tonos = tonos_por_persona(personas)
    mostrados = [persona] if persona else personas
    calendario = agenda_de_convocatoria(convocatoria, modo, dia, mostrados, tonos, solo_las_que_cubren=bool(persona))
    for columna in calendario.get('columnas', []):
        columna['url_dia'] = url('dia', columna['fecha'])
    for semana in calendario.get('semanas', []):
        for dia_mes in semana:
            dia_mes['url_dia'] = url('dia', dia_mes['fecha'])

    dias_asignados = services.dias_asignados_por_persona(convocatoria)

    return {
        'convocatoria': convocatoria,
        'convocatorias_agrupadas': convocatorias_agrupadas(hoy),
        'otras_convocatorias': [
            {'convocatoria': otra, 'tono': tono_convocatoria(otra), 'url': _url_agenda(otra, modo, dia, persona)}
            for otra in otras_convocatorias(inicio_visible, fin_visible, convocatoria)
        ],
        **services.resumen_convocatoria(convocatoria, personas, hoy),
        'modo': modo,
        'dia': dia,
        'hoy': hoy,
        'persona': persona,
        'personas': personas,
        'calendario': calendario,
        'titulo_periodo': services.titulo_periodo(modo, dia),
        'url_actual': url(modo, dia),
        # No se navega más allá del periodo de la convocatoria.
        'url_anterior': url(modo, anterior) if inicio_visible > convocatoria.fecha_inicio else None,
        'url_siguiente': url(modo, siguiente) if fin_visible < convocatoria.fecha_fin else None,
        'url_hoy': url(modo, hoy) if en_periodo else None,
        'url_primer_dia': url(modo, convocatoria.fecha_inicio),
        'dia_impresion': _dia_impresion(convocatoria),
        'modos': [(clave, etiqueta, url(clave, dia)) for clave, etiqueta in (('semana', 'Semana'), ('dia', 'Día'), ('mes', 'Mes'))],
        'leyenda': [
            {'persona': aux, 'tono': tonos[aux.pk], 'dias': dias_asignados.get(aux.pk, 0)} for aux in personas
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
# Impresión de la agenda: convocatoria completa, una semana o un día
# ---------------------------------------------------------------------------

def _dia_impresion(convocatoria):
    """Día con que se abre la impresión por semana o por día: hoy si la convocatoria está en curso; si no, su primer día."""
    hoy = timezone.localdate()
    return hoy if convocatoria.fecha_inicio <= hoy <= convocatoria.fecha_fin else convocatoria.fecha_inicio


@permiso_requerido('programacion.view_programacion')
def agenda_imprimir(request):
    convocatoria = get_object_or_404(Convocatoria, pk=request.GET.get('convocatoria') or 0)
    alcance = request.GET.get('alcance')
    alcance = alcance if alcance in services.ALCANCES_IMPRESION else 'convocatoria'
    dia = _fecha(request.GET.get('fecha')) or _dia_impresion(convocatoria)

    return respuesta_pdf(
        request, 'partials/agenda/reporte_pdf.html',
        services.reporte_agenda(convocatoria, alcance, dia),
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
    """Qué personas asignadas a ese día cubren la jornada elegida en el formulario."""
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


def _personas_filtrados(request):
    """Personal filtrados, sin paginar (los usa el listado y el "Imprimir")."""
    filtro_form = FiltrarPersonalForm(request.GET or None)
    return filtro_form, services.filtrar_personas(datos_filtro(filtro_form))


def _filtrar_personas(request):
    filtro_form, personas_list = _personas_filtrados(request)

    paginator = Paginator(personas_list, 20)
    personas = paginator.get_page(request.GET.get("page"))
    services.con_estado_horario(personas)

    return filtro_form, personas


@permiso_requerido('programacion.view_personal')
def personalHomeView(request):
    filtro_form, personas = _filtrar_personas(request)

    return render(
        request,
        "personal/personalHome.html",
        {
            "personas": personas,
            "filtro_form": filtro_form,
            "form_media": filtro_form.media,
            "breadcrumbs": [
                {"name": "Inicio", "url": reverse("home")},
                {"name": "Personal"},
            ],
        },
    )


@permiso_requerido('programacion.view_personal')
def buscar_personas(request):
    _, personas = _filtrar_personas(request)

    return render(
        request,
        "partials/personal/tabla.html",
        {"personas": personas},
    )


@permiso_formulario('programacion.personal')
def persona_form(request, pk=None):
    instance = get_object_or_404(Personal, pk=pk) if pk else None

    if request.method == "POST":
        form = PersonalForm(request.POST, instance=instance)
        if form.is_valid():
            persona = form.save()
            accion = 'registró' if instance is None else 'actualizó'
            messages.success(request, f'Se {accion} a la persona {persona.nombre} {persona.apellido}.')
            _, personas = _filtrar_personas(request)
            return render(
                request,
                "partials/personal/modal_form_success.html",
                {"personas": personas},
            )
    else:
        form = PersonalForm(instance=instance)

    return render(
        request,
        "partials/personal/modal_form.html",
        {"form": form, "instance": instance, "cargos": services.cargos_existentes()},
    )


@permiso_requerido('programacion.change_personal')
def persona_estado(request, pk):
    """Desactiva o vuelve a activar a una persona. Nunca se elimina: se perdería su historial."""
    instance = get_object_or_404(Personal, pk=pk)

    if request.method == "POST":
        if instance.activo:
            services.desactivar_persona(instance)
            messages.success(request, f'Se desactivó a {instance.nombre} {instance.apellido}.')
        else:
            services.activar_persona(instance)
            messages.success(request, f'Se activó de nuevo a {instance.nombre} {instance.apellido}.')
        _, personas = _filtrar_personas(request)
        return render(
            request,
            "partials/personal/modal_form_success.html",
            {"personas": personas},
        )

    return render(
        request,
        "partials/personal/modal_estado.html",
        {"instance": instance},
    )


def _practicante(persona_pk):
    # Al personal inactivo no se le cambia el horario: primero hay que activarlo.
    return get_object_or_404(Personal, pk=persona_pk, tipo=Personal.Tipo.PRACTICANTE, activo=True)


@permiso_requerido('programacion.add_horario', 'programacion.change_horario', 'programacion.delete_horario')
def horario_form(request, persona_pk):
    """Horario semanal del practicante: al guardar reemplaza el que tenía (tiene uno solo)."""
    persona = _practicante(persona_pk)
    tenia_horario = persona.horario_set.exists()
    if request.method == "POST":
        form = HorarioForm(persona, request.POST)
        if form.is_valid():
            form.save()
            accion = 'actualizó' if tenia_horario else 'asignó'
            messages.success(request, f'Se {accion} el horario de {persona.nombre} {persona.apellido}.')
            _, personas = _filtrar_personas(request)
            return render(
                request,
                "partials/horario/modal_form_success.html",
                {"personas": personas},
            )
    else:
        form = HorarioForm(persona, initial=services.horario_inicial(persona))

    return render(
        request,
        "partials/horario/modal_form.html",
        {"form": form, "persona": persona, "tenia_horario": tenia_horario},
    )


@permiso_requerido('programacion.delete_horario')
def horario_eliminar(request, persona_pk):
    persona = _practicante(persona_pk)
    if request.method == "POST":
        persona.horario_set.all().delete()
        messages.success(request, f'Se eliminó el horario de {persona.nombre} {persona.apellido}.')
        _, personas = _filtrar_personas(request)
        return render(
            request,
            "partials/horario/modal_form_success.html",
            {"personas": personas},
        )

    persona.horarios = list(persona.horario_set.all())
    services.con_estado_horario([persona])
    return render(
        request,
        "partials/horario/modal_delete.html",
        {"persona": persona},
    )


@permiso_requerido('programacion.view_personal')
def persona_imprimir(request):
    _, personas = _personas_filtrados(request)
    return respuesta_pdf(request, "partials/personal/reporte_pdf.html", {"personas": personas}, "personal.pdf")


# ---------------------------------------------------------------------------
# Asistencia de practicantes: pase de lista por día e historial
# ---------------------------------------------------------------------------

VISTAS_ASISTENCIA = ('dia', 'historial')


def _fecha_pase_de_lista(request):
    return _fecha(request.GET.get('fecha') or request.POST.get('fecha')) or timezone.localdate()


def _contexto_pase_de_lista(fecha):
    filas = services.pase_de_lista(fecha)
    hoy = timezone.localdate()
    return {
        'fecha': fecha,
        'hoy': hoy,
        'es_futuro': fecha > hoy,
        'filas': filas,
        'resumen': services.resumen_pase_de_lista(filas),
        'estados': Asistencia.Estado.choices,
        'anterior': fecha - timedelta(days=1),
        'siguiente': fecha + timedelta(days=1),
    }


def _asistencias_filtradas(request):
    """Formulario y asistencias filtradas, SIN paginar (lo reutiliza el imprimir)."""
    filtro_form = FiltrarAsistenciaForm(request.GET or None)
    return filtro_form, services.filtrar_asistencias(datos_filtro(filtro_form))


def _contexto_historial(request):
    filtro_form, asistencias = _asistencias_filtradas(request)
    return {
        'filtro_form': filtro_form,
        'asistencias': Paginator(asistencias, 25).get_page(request.GET.get('page')),
        'por_practicante': services.resumen_por_practicante(asistencias),
    }


@permiso_requerido('programacion.view_asistencia')
def asistenciaHomeView(request):
    vista = request.GET.get('vista')
    vista = vista if vista in VISTAS_ASISTENCIA else 'dia'
    contexto = {
        'vista': vista,
        'breadcrumbs': [
            {'name': 'Inicio', 'url': reverse('home')},
            {'name': 'Asistencia'},
        ],
        'form_media': FiltrarAsistenciaForm().media,
    }
    if vista == 'dia':
        contexto.update(_contexto_pase_de_lista(_fecha_pase_de_lista(request)))
    else:
        contexto.update(_contexto_historial(request))
    return render(request, 'asistencia/asistenciaHome.html', contexto)


@permiso_requerido('programacion.view_asistencia')
def asistencia_dia(request):
    """Pase de lista de otro día (navegación con htmx)."""
    return render(request, 'partials/asistencia/_pase_de_lista.html', _contexto_pase_de_lista(_fecha_pase_de_lista(request)))


@permiso_requerido('programacion.add_asistencia', 'programacion.change_asistencia')
@require_POST
def asistencia_registrar(request):
    """Guarda el estado de un practicante en un día y vuelve a pintar el pase de lista."""
    fecha = _fecha_pase_de_lista(request)
    persona = get_object_or_404(Personal, pk=request.POST.get('persona') or 0)
    estado = request.POST.get('estado')
    contexto = _contexto_pase_de_lista(fecha)
    if estado not in Asistencia.Estado.values:
        return render(request, 'partials/asistencia/_pase_de_lista.html', {**contexto, 'error': 'Elige un estado válido.'})
    try:
        asistencia = services.registrar_asistencia(persona.pk, fecha, estado, request.POST.get('observacion', ''))
    except ValidationError as error:
        mensaje = ' '.join(error.messages)
        return render(request, 'partials/asistencia/_pase_de_lista.html', {**contexto, 'error': f'{persona.nombre} {persona.apellido}: {mensaje}'})
    messages.success(request, f'{persona.nombre} {persona.apellido}: {asistencia.get_estado_display().lower()}.')
    return render(request, 'partials/asistencia/_pase_de_lista.html', _contexto_pase_de_lista(fecha))


@permiso_requerido('programacion.delete_asistencia')
@require_POST
def asistencia_quitar(request):
    """Deja a un practicante "sin registrar" ese día (para corregir un error)."""
    fecha = _fecha_pase_de_lista(request)
    persona = get_object_or_404(Personal, pk=request.POST.get('persona') or 0)
    services.quitar_asistencia(persona.pk, fecha)
    messages.info(request, f'Se quitó el registro de {persona.nombre} {persona.apellido}.')
    return render(request, 'partials/asistencia/_pase_de_lista.html', _contexto_pase_de_lista(fecha))


@permiso_requerido('programacion.add_asistencia')
@require_POST
def asistencia_todos_presentes(request):
    fecha = _fecha_pase_de_lista(request)
    if fecha > timezone.localdate():
        return render(request, 'partials/asistencia/_pase_de_lista.html', {
            **_contexto_pase_de_lista(fecha), 'error': 'No se puede marcar asistencia de un día que aún no llega.',
        })
    total = services.marcar_pendientes_presentes(fecha)
    if total:
        messages.success(request, f"Se marcaron {total} practicante{'s' if total != 1 else ''} como presente{'s' if total != 1 else ''}.")
    return render(request, 'partials/asistencia/_pase_de_lista.html', _contexto_pase_de_lista(fecha))


@permiso_requerido('programacion.view_asistencia')
def buscar_asistencias(request):
    return render(request, 'partials/asistencia/_historial_resultados.html', _contexto_historial(request))


@permiso_requerido('programacion.view_asistencia')
def asistencia_imprimir(request):
    filtro_form, asistencias = _asistencias_filtradas(request)
    filtros = datos_filtro(filtro_form)
    return respuesta_pdf(request, 'partials/asistencia/reporte_pdf.html', {
        'asistencias': asistencias,
        'por_practicante': services.resumen_por_practicante(asistencias),
        'filtros': filtros,
    }, 'asistencia.pdf')


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


# Acciones del modal de personas de un día y el permiso extra que pide cada una
# (agregar y quitar ya los exige el decorador de la vista).
ACCIONES_DIA = {
    'agregar': None,
    'quitar': None,
    'no_llego': 'programacion.add_asistencia',
    'si_llego': 'programacion.change_asistencia',
}
MENSAJES_DIA = {
    'agregar': 'Persona asignada al día.',
    'quitar': 'Persona quitada del día.',
    'no_llego': 'Se registró que el practicante no llegó.',
    'si_llego': 'El practicante quedó como presente.',
}


@permiso_requerido('programacion.add_convocatoriapersonal', 'programacion.delete_convocatoriapersonal')
def convocatoria_dia_personas(request, pk):
    """Agregar y quitar personas de un día de la convocatoria, y registrar si no llegaron. Cada acción
    se guarda al momento: se vuelve a pintar la lista del modal (que sigue abierto) y se avisa a la
    agenda para refrescarse."""
    convocatoria = get_object_or_404(Convocatoria, pk=pk)
    fecha = _fecha(request.GET.get('fecha'))
    if not fecha or not convocatoria.fecha_inicio <= fecha <= convocatoria.fecha_fin:
        return HttpResponse('El día debe estar dentro de las fechas de la convocatoria.', status=400)
    del_dia = PersonalDelDia(convocatoria, fecha)

    contexto = {"convocatoria": convocatoria, "fecha": fecha, "del_dia": del_dia}
    if request.method == "POST":
        error = None
        # Cada botón manda una sola acción con el id de la persona: {"agregar": id}, {"no_llego": id}...
        accion = next((nombre for nombre in ACCIONES_DIA if request.POST.get(nombre, '').isdigit()), None)
        persona_id = int(request.POST[accion]) if accion else None
        permiso = ACCIONES_DIA.get(accion)
        if permiso and not request.user.has_perm(permiso):
            raise PermissionDenied
        if accion == 'agregar':
            error = del_dia.agregar(persona_id)
        elif accion == 'quitar':
            del_dia.quitar(persona_id)
        elif accion == 'no_llego':
            error = del_dia.registrar_inasistencia(persona_id, request.POST.get('motivo', ''))
        elif accion == 'si_llego':
            del_dia.quitar_inasistencia(persona_id)
        contexto['asignados'], contexto['disponibles'] = del_dia.opciones()
        respuesta = render(request, "partials/agenda/_asignar_personal_lista.html", {**contexto, "error": error})
        if not error:
            if accion:
                messages.success(request, MENSAJES_DIA[accion])
            respuesta['HX-Trigger'] = EVENTO_AGENDA
        return respuesta

    contexto['asignados'], contexto['disponibles'] = del_dia.opciones()
    return render(request, "partials/agenda/modal_asignar_personal.html", contexto)


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