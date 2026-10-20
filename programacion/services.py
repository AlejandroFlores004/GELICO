"""Lógica de negocio de programación: visitas, auxiliares, horarios, ausencias y convocatorias.

El cálculo de la agenda por jornadas (cobertura, turnos, colores) vive en agenda.py;
este módulo lo usa para armar resúmenes y reportes. Las funciones no reciben el
request: trabajan con datos ya validados y con modelos.
"""
from collections import defaultdict
from datetime import timedelta

from django.db.models import Count, Exists, OuterRef, Prefetch, Q
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.text import capfirst

from .agenda import Agenda, estado_convocatoria, rango_visible, resumen_estados, sumar_meses
from .models import ORDEN_JORNADA, Auxiliar, Ausencia, Convocatoria, ConvocatoriaAuxiliar, Horario, Jornada, Programacion

FORMATO_DIA = 'l j \\d\\e F \\d\\e Y'
FORMATO_FECHA = 'j \\d\\e F Y'
ALCANCES_IMPRESION = ('convocatoria', 'semana', 'dia', 'auxiliar', 'sin_cobertura', 'pendientes')


def titulo_periodo(modo, dia):
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


def fechas_vecinas(modo, dia):
    """Día que se muestra al ir al periodo anterior y al siguiente."""
    if modo == 'mes':
        return sumar_meses(dia, -1), sumar_meses(dia, 1)
    paso = timedelta(weeks=1) if modo == 'semana' else timedelta(days=1)
    return dia - paso, dia + paso


# ---------------------------------------------------------------------------
# Programaciones (visitas)
# ---------------------------------------------------------------------------

def filtrar_programaciones(filtros):
    programaciones = Programacion.objects.select_related(
        'convocatoria', 'escuela'
    ).order_by('-fecha_programada', ORDEN_JORNADA.desc())

    search = (filtros.get('q') or '').strip()
    convocatoria = filtros.get('convocatoria')
    escuela = filtros.get('escuela')

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
    return programaciones


def cobertura_de_visita(programacion):
    """(auxiliares que cubren la visita, si queda cubierta)."""
    cobertura = Agenda(programacion.convocatoria, programacion.fecha_programada, programacion.fecha_programada, con_visitas=False)
    return cobertura.cubren_visita(programacion), cobertura.visita_cubierta(programacion)


def resumen_convocatoria(convocatoria, auxiliares, hoy):
    """Indicadores de la convocatoria que acompañan a su agenda."""
    programaciones = convocatoria.programacion_set.all()
    # Cobertura de todo el periodo, para el contador de visitas que ningún auxiliar cubre.
    periodo = Agenda(convocatoria, convocatoria.fecha_inicio, convocatoria.fecha_fin, auxiliares)
    return {
        'estado_convocatoria': estado_convocatoria(convocatoria, hoy),
        'duracion': (convocatoria.fecha_fin - convocatoria.fecha_inicio).days + 1,
        'dias_restantes': (convocatoria.fecha_fin - hoy).days,
        'estados': resumen_estados(programaciones),
        'sin_cobertura': sum(not programacion.cubierta for programacion in periodo.programaciones),
        'escuelas_visitadas': programaciones.values('escuela').distinct().count(),
    }


def dias_asignados_por_auxiliar(convocatoria):
    """{auxiliar_id: cantidad de días asignados} en la convocatoria."""
    return dict(
        convocatoria.asignaciones.values('auxiliar').annotate(dias=Count('fecha')).values_list('auxiliar', 'dias')
    )


def reporte_agenda(convocatoria, alcance, dia, auxiliar=None):
    """Datos del PDF de la agenda según el alcance: toda la convocatoria, una semana, un día,
    la hoja de ruta de un auxiliar, las visitas sin cobertura o las pendientes."""
    programaciones = convocatoria.programacion_set.select_related(
        'escuela__distrito',
    ).order_by('fecha_programada', ORDEN_JORNADA, 'escuela__nombre')
    inicio, fin = convocatoria.fecha_inicio, convocatoria.fecha_fin
    subtitulo = f"Del {date_format(inicio, FORMATO_FECHA)} al {date_format(fin, FORMATO_FECHA)}"

    if alcance == 'semana':
        semana_inicio, semana_fin = rango_visible('semana', dia)
        # La semana se recorta al periodo de la convocatoria.
        inicio, fin = max(semana_inicio, inicio), min(semana_fin, fin)
        subtitulo = f"Semana: {titulo_periodo('semana', dia)}"
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

    return {
        'convocatoria': convocatoria,
        'alcance': alcance,
        'subtitulo': subtitulo,
        'auxiliar': auxiliar if alcance == 'auxiliar' else None,
        'dias': [{'fecha': fecha, 'programaciones': lista} for fecha, lista in sorted(por_dia.items())],
        'total': len(programaciones),
        'estados': resumen_estados(programaciones),
        # La hoja de ruta lleva columnas para llenar a mano en campo.
        'para_campo': alcance in ('auxiliar', 'dia'),
    }


# ---------------------------------------------------------------------------
# Auxiliares y horarios
# ---------------------------------------------------------------------------

def filtrar_auxiliares(filtros):
    """Auxiliares filtrados por texto, institución, horario y convocatoria. SIN paginar."""
    auxiliares = Auxiliar.objects.prefetch_related(
        Prefetch(
            'horario_set',
            queryset=Horario.objects.order_by('dia', ORDEN_JORNADA, 'fecha_inicio'),
            to_attr='horarios',
        ),
    ).order_by('apellido', 'nombre')
    if not filtros:
        return auxiliares

    hoy = timezone.localdate()
    fecha, dia, jornada = filtros.get('fecha'), filtros.get('dia'), filtros.get('jornada')

    texto = (filtros.get('q') or '').strip()
    if texto:
        auxiliares = auxiliares.filter(
            Q(nombre__icontains=texto) | Q(apellido__icontains=texto) | Q(email__icontains=texto)
            | Q(telefono__icontains=texto) | Q(institucion__icontains=texto)
        )
    if filtros.get('institucion'):
        auxiliares = auxiliares.filter(institucion=filtros['institucion'])

    # Horarios del auxiliar que cumplen la fecha, el día y la jornada pedidos.
    horarios = Horario.objects.filter(auxiliar=OuterRef('pk'))
    if fecha:
        horarios = horarios.del_dia(fecha)
    if dia:
        horarios = horarios.filter(dia=dia)
    if jornada:
        # Quien trabaja todo el día también trabaja en la mañana y en la tarde.
        horarios = horarios.filter(jornada__in=[jornada] if jornada == Jornada.COMPLETA else [jornada, Jornada.COMPLETA])
    # Elegir fecha, día o jornada sin decir nada del horario se entiende como "trabaja entonces".
    estado = filtros.get('horario') or ('con' if fecha or dia or jornada else '')
    if estado == 'con':
        auxiliares = auxiliares.filter(Exists(horarios))
    elif estado == 'sin':
        auxiliares = auxiliares.filter(~Exists(horarios))
    elif estado == 'vigente':
        auxiliares = auxiliares.filter(Exists(horarios.filter(fecha_inicio__lte=hoy, fecha_fin__gte=hoy)))
    elif estado == 'vencido':
        auxiliares = auxiliares.filter(Exists(horarios)).exclude(Exists(horarios.filter(fecha_fin__gte=hoy)))

    # Con fecha, las asignaciones se miran solo ese día.
    if filtros.get('convocatoria'):
        asignaciones = ConvocatoriaAuxiliar.objects.filter(auxiliar=OuterRef('pk'), convocatoria=filtros['convocatoria'])
        if fecha:
            asignaciones = asignaciones.filter(fecha=fecha)
        auxiliares = auxiliares.filter(Exists(asignaciones))

    return auxiliares


def con_estado_horario(auxiliares):
    """Marca cada auxiliar según su horario: sin horario, vigente hoy, por empezar o vencido."""
    hoy = timezone.localdate()
    for auxiliar in auxiliares:
        if not auxiliar.horarios:
            auxiliar.estado_horario = 'sin'
        elif any(h.fecha_inicio <= hoy <= h.fecha_fin for h in auxiliar.horarios):
            auxiliar.estado_horario = 'vigente'
        elif any(h.fecha_inicio > hoy for h in auxiliar.horarios):
            auxiliar.estado_horario = 'futuro'
        else:
            auxiliar.estado_horario = 'vencido'
    return auxiliares


def horario_inicial(auxiliar_id):
    """Valores con que se abre un horario nuevo. Lo usual es agregar más días al mismo
    periodo de labores: se propone el del último horario del auxiliar."""
    inicial = {'auxiliar': auxiliar_id}
    ultimo = Horario.objects.filter(auxiliar_id=auxiliar_id).order_by('-fecha_fin').first() if auxiliar_id else None
    if ultimo:
        inicial.update(fecha_inicio=ultimo.fecha_inicio, fecha_fin=ultimo.fecha_fin)
    return inicial


# ---------------------------------------------------------------------------
# Ausencias
# ---------------------------------------------------------------------------

def filtrar_ausencias(search='', fecha=None):
    """Ausencias por nombre del auxiliar o motivo, y por fecha exacta. SIN paginar."""
    ausencias = Ausencia.objects.select_related('auxiliar').order_by('-fecha', 'auxiliar__apellido', 'auxiliar__nombre')
    if search:
        ausencias = ausencias.filter(
            Q(auxiliar__nombre__icontains=search)
            | Q(auxiliar__apellido__icontains=search)
            | Q(motivo__icontains=search)
        )
    if fecha:
        ausencias = ausencias.filter(fecha=fecha)
    return ausencias


def auxiliares_con_ausencias(search='', fecha=None):
    """Auxiliares con sus horarios y ausencias, filtrados por nombre/motivo y fecha. SIN paginar."""
    auxiliares = Auxiliar.objects.prefetch_related(
        Prefetch('horario_set', queryset=Horario.objects.order_by('dia', ORDEN_JORNADA, 'fecha_inicio'), to_attr='horarios'),
        Prefetch('ausencia_set', queryset=Ausencia.objects.order_by('-fecha'), to_attr='ausencias'),
    ).order_by('apellido', 'nombre')

    if search:
        auxiliares = auxiliares.filter(
            Q(nombre__icontains=search)
            | Q(apellido__icontains=search)
            | Q(ausencia__motivo__icontains=search)
        ).distinct()
    if fecha:
        auxiliares = auxiliares.filter(ausencia__fecha=fecha).distinct()
    return auxiliares


# ---------------------------------------------------------------------------
# Convocatorias
# ---------------------------------------------------------------------------

def filtrar_convocatorias(search='', fecha_inicio=None, fecha_fin=None):
    """Convocatorias por nombre/descripción y dentro del rango de fechas. SIN paginar."""
    convocatorias = Convocatoria.objects.all().order_by('fecha_inicio')
    if search:
        convocatorias = convocatorias.filter(Q(nombre__icontains=search) | Q(descripcion__icontains=search))
    if fecha_inicio:
        convocatorias = convocatorias.filter(fecha_inicio__gte=fecha_inicio)
    if fecha_fin:
        convocatorias = convocatorias.filter(fecha_fin__lte=fecha_fin)
    return convocatorias
