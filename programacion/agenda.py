"""Agenda por jornadas de una convocatoria.

Cada día del periodo de la convocatoria se divide en dos turnos (mañana y tarde); cada visita
a una escuela ocupa la jornada de la mañana, la de la tarde o todo el día (ambos turnos).

Las visitas no llevan persona: el personal se asigna a días de la convocatoria, y un turno
de un día queda "cubierto" por las personas asignadas a ese día que trabajan ese turno:
- los practicantes, si su horario semanal incluye ese turno (dentro de su periodo de labores)
  y no tienen registrado ese día como ausente o justificado;
- el personal de planta, siempre (no tiene horario fijo: asignado a un día, cubre el día completo).
"""
from calendar import Calendar
from collections import defaultdict
from datetime import datetime, timedelta

from django.db.models import Count, Q
from django.utils import timezone

from .models import (
    HORAS_TURNO, ORDEN_JORNADA, TURNOS, TURNOS_JORNADA, Asistencia, Personal, Convocatoria, Horario, Jornada,
    es_fin_de_semana,
)

MODOS = ('mes', 'semana', 'dia')

# Colores por persona. Se evitan success/warning/error porque esos indican el estado.
TONOS_PERSONA = [
    {'tarjeta': 'border-primary bg-primary/8', 'punto': 'bg-primary'},
    {'tarjeta': 'border-info bg-info/10', 'punto': 'bg-info'},
    {'tarjeta': 'border-accent bg-accent/10', 'punto': 'bg-accent'},
    {'tarjeta': 'border-secondary bg-secondary/12', 'punto': 'bg-secondary'},
    {'tarjeta': 'border-neutral/60 bg-neutral/8', 'punto': 'bg-neutral'},
]
# Visitas en una jornada que ninguna persona de la convocatoria cubre.
TONO_SIN_COBERTURA = {'tarjeta': 'border-dashed border-warning bg-warning/10', 'punto': 'bg-warning'}
# Colores de las convocatorias.
TONOS_CONVOCATORIA = [
    {'barra': 'bg-primary text-primary-content', 'punto': 'bg-primary'},
    {'barra': 'bg-info text-info-content', 'punto': 'bg-info'},
    {'barra': 'bg-accent text-accent-content', 'punto': 'bg-accent'},
    {'barra': 'bg-secondary text-secondary-content', 'punto': 'bg-secondary'},
    {'barra': 'bg-neutral text-neutral-content', 'punto': 'bg-neutral'},
]


def etiqueta_jornada(jornada):
    return Jornada(jornada).label


def tono_convocatoria(convocatoria):
    return TONOS_CONVOCATORIA[convocatoria.pk % len(TONOS_CONVOCATORIA)]


def inicio_semana(dia):
    """Domingo con que empieza la semana de una fecha."""
    return dia - timedelta(days=dia.isoweekday() % 7)


def sumar_meses(dia, meses):
    total = dia.year * 12 + (dia.month - 1) + meses
    return dia.replace(year=total // 12, month=total % 12 + 1, day=1)


def _semanas_del_mes(dia):
    return Calendar(firstweekday=6).monthdatescalendar(dia.year, dia.month)


def rango_visible(modo, dia):
    """Primer y último día que se ven en pantalla."""
    if modo == 'mes':
        semanas = _semanas_del_mes(dia)
        return semanas[0][0], semanas[-1][-1]
    if modo == 'semana':
        inicio = inicio_semana(dia)
        return inicio, inicio + timedelta(days=6)
    return dia, dia


def tonos_por_persona(personas):
    return {persona.pk: TONOS_PERSONA[indice % len(TONOS_PERSONA)] for indice, persona in enumerate(personas)}


def turno_paso(dia, turno):
    """Un turno ya pasó cuando terminó (hasta entonces aún se puede programar)."""
    fin = datetime.combine(dia, HORAS_TURNO[turno][1])
    return fin <= timezone.localtime().replace(tzinfo=None)


def estado_convocatoria(convocatoria, hoy=None):
    hoy = hoy or timezone.localdate()
    if convocatoria.fecha_fin < hoy:
        return 'finalizada'
    if convocatoria.fecha_inicio > hoy:
        return 'proxima'
    return 'en_curso'


# ---------------------------------------------------------------------------
# Convocatorias
# ---------------------------------------------------------------------------

def con_conteos(convocatorias):
    return convocatorias.annotate(
        total_programaciones=Count('programacion'),
        completadas=Count('programacion', filter=Q(programacion__estado='completado')),
    )


def convocatoria_por_defecto(hoy=None):
    """La que está en curso (la que termina primero); si no hay, la próxima; si no, la última que terminó."""
    hoy = hoy or timezone.localdate()
    return (
        Convocatoria.objects.filter(fecha_inicio__lte=hoy, fecha_fin__gte=hoy).order_by('fecha_fin', 'pk').first()
        or Convocatoria.objects.filter(fecha_inicio__gt=hoy).order_by('fecha_inicio', 'pk').first()
        or Convocatoria.objects.order_by('-fecha_fin', '-pk').first()
    )


def convocatorias_agrupadas(hoy=None):
    """Opciones del selector: en curso, próximas y finalizadas."""
    hoy = hoy or timezone.localdate()
    grupos = {'en_curso': [], 'proxima': [], 'finalizada': []}
    for convocatoria in Convocatoria.objects.order_by('fecha_inicio', 'pk'):
        grupos[estado_convocatoria(convocatoria, hoy)].append(convocatoria)
    grupos['finalizada'].reverse()  # las más recientes primero
    return [
        ('En curso', grupos['en_curso']),
        ('Próximas', grupos['proxima']),
        ('Finalizadas', grupos['finalizada']),
    ]


def otras_convocatorias(inicio, fin, convocatoria):
    """Otras convocatorias que también caen en el periodo visible, para cambiar a ellas."""
    return Convocatoria.objects.filter(fecha_inicio__lte=fin, fecha_fin__gte=inicio).exclude(
        pk=convocatoria.pk,
    ).order_by('fecha_inicio')


# ---------------------------------------------------------------------------
# Agenda de una convocatoria: turnos de mañana y tarde
# ---------------------------------------------------------------------------

def horarios_por_fecha(horarios, inicio, fin):
    """Reparte los horarios semanales en cada fecha del rango donde aplican: {(persona_id, fecha): [horarios]}."""
    por_fecha = defaultdict(list)
    for horario in sorted(horarios, key=lambda horario: TURNOS.index(horario.turnos[0])):
        desde, hasta = max(inicio, horario.fecha_inicio), min(fin, horario.fecha_fin)
        # Primer día de la semana del horario a partir de "desde", y luego cada 7 días.
        fecha = desde + timedelta(days=(horario.dia - desde.isoweekday()) % 7)
        while fecha <= hasta:
            por_fecha[(horario.persona_id, fecha)].append(horario)
            fecha += timedelta(days=7)
    return por_fecha


def personal_asignado(convocatoria):
    """Personas con al menos un día asignado en la convocatoria."""
    return Personal.objects.filter(asignaciones__convocatoria=convocatoria).distinct().order_by('apellido', 'nombre')


class Agenda:
    """Asignaciones, horarios y ausencias del personal de una convocatoria, y sus visitas, en un rango de fechas."""

    def __init__(self, convocatoria, inicio, fin, personas=None, con_visitas=True):
        self.personas = list(personas if personas is not None else personal_asignado(convocatoria))
        ids = [persona.pk for persona in self.personas]
        self.planta = {persona.pk for persona in self.personas if not persona.es_practicante}

        self.asignados = set(
            convocatoria.asignaciones.filter(persona__in=ids, fecha__range=(inicio, fin)).values_list('persona_id', 'fecha')
        )
        self.horarios = horarios_por_fecha(
            Horario.objects.filter(persona__in=ids).vigentes_entre(inicio, fin), inicio, fin,
        )
        self.ausencias = set(
            Asistencia.objects.filter(
                persona__in=ids, fecha__range=(inicio, fin), estado__in=Asistencia.NO_TRABAJO,
            ).values_list('persona_id', 'fecha')
        )
        self.programaciones = list(
            convocatoria.programacion_set.filter(fecha_programada__range=(inicio, fin))
            .select_related('escuela').order_by('fecha_programada', ORDEN_JORNADA, 'escuela__nombre')
        ) if con_visitas else []
        for programacion in self.programaciones:
            programacion.cubren = self.cubren_visita(programacion)
            programacion.cubierta = self.visita_cubierta(programacion)

    def asignado(self, persona_id, dia):
        return (persona_id, dia) in self.asignados

    def asignados_el(self, dia):
        return [persona for persona in self.personas if self.asignado(persona.pk, dia)]

    def ausente(self, persona_id, dia):
        return (persona_id, dia) in self.ausencias

    def turnos_que_trabaja(self, persona_id, dia):
        """Planta: el día completo. Practicante: los turnos de su horario de ese día."""
        if persona_id in self.planta:
            return set(TURNOS)
        return {turno for horario in self.horarios[(persona_id, dia)] for turno in horario.turnos}

    def cubre(self, persona_id, dia, turno):
        """Está asignado a ese día, trabaja ese turno y no está ausente."""
        return (
            self.asignado(persona_id, dia)
            and not self.ausente(persona_id, dia)
            and turno in self.turnos_que_trabaja(persona_id, dia)
        )

    def cubren(self, dia, turno):
        return [persona for persona in self.personas if self.cubre(persona.pk, dia, turno)]

    def cubren_visita(self, programacion):
        """Personas que cubren al menos un turno de la visita."""
        return [
            persona for persona in self.personas
            if any(self.cubre(persona.pk, programacion.fecha_programada, turno) for turno in programacion.turnos)
        ]

    def visita_cubierta(self, programacion):
        """Cada turno de la visita tiene al menos una persona (para todo el día puede ser uno en la mañana y otro en la tarde)."""
        return all(self.cubren(programacion.fecha_programada, turno) for turno in programacion.turnos)


def _en_periodo(dia, convocatoria):
    return convocatoria.fecha_inicio <= dia <= convocatoria.fecha_fin


def _puede_asignar(dia, asignados, convocatoria):
    """El fin de semana no se asigna personal; el botón solo queda si hay asignados de antes, para quitarlos."""
    return _en_periodo(dia, convocatoria) and (not es_fin_de_semana(dia) or bool(asignados))


def _columnas(modo, dia, agenda):
    """Semana: un día por columna (sábado y domingo no se trabaja: solo aparecen si quedó personal
    asignado o visitas de antes). Día: una columna."""
    if modo == 'dia':
        return [{'fecha': dia}]
    columnas = []
    for desplazamiento in range(7):
        fecha = inicio_semana(dia) + timedelta(days=desplazamiento)
        if es_fin_de_semana(fecha):
            hay_asignados = bool(agenda.asignados_el(fecha))
            hay_visitas = any(programacion.fecha_programada == fecha for programacion in agenda.programaciones)
            if not (hay_asignados or hay_visitas):
                continue
        columnas.append({'fecha': fecha})
    return columnas


def _celda(fecha, turno, agenda, convocatoria):
    celda = {
        'fecha': fecha,
        'turno': turno,
        # Una visita de todo el día aparece en los dos turnos.
        'programaciones': [
            programacion for programacion in agenda.programaciones
            if programacion.fecha_programada == fecha and turno in programacion.turnos
        ],
        'cubren': agenda.cubren(fecha, turno),
        'fuera_periodo': not _en_periodo(fecha, convocatoria),
        'paso': turno_paso(fecha, turno),
    }
    celda['puede_programar'] = not celda['fuera_periodo'] and not celda['paso'] and not es_fin_de_semana(fecha)
    return celda


def _con_tono(personas, tonos):
    return [{'persona': persona, 'tono': tonos.get(persona.pk, TONOS_PERSONA[0])} for persona in personas]


def agenda_de_convocatoria(convocatoria, modo, dia, personas, tonos, solo_las_que_cubren=False):
    """Agenda de la convocatoria con la cobertura de las personas dadas. Al filtrar por un
    persona (solo_las_que_cubren=True) solo se ven las visitas de las jornadas en que él trabaja."""
    inicio, fin = rango_visible(modo, dia)
    agenda = Agenda(convocatoria, inicio, fin, personas)
    if solo_las_que_cubren:
        agenda.programaciones = [programacion for programacion in agenda.programaciones if programacion.cubren]
    for programacion in agenda.programaciones:
        programacion.tono = TONOS_PERSONA[0] if programacion.cubierta else TONO_SIN_COBERTURA
        programacion.cubren_con_tono = _con_tono(programacion.cubren, tonos)

    hoy = timezone.localdate()
    if modo == 'mes':
        semanas = [
            [
                {
                    'fecha': fecha,
                    'en_mes': fecha.month == dia.month,
                    'programaciones': [p for p in agenda.programaciones if p.fecha_programada == fecha],
                    'asignados': _con_tono(agenda.asignados_el(fecha), tonos),
                    'ausentes': [persona for persona in agenda.asignados_el(fecha) if agenda.ausente(persona.pk, fecha)],
                    'fuera_periodo': not _en_periodo(fecha, convocatoria),
                    'puede_programar': fecha >= hoy and _en_periodo(fecha, convocatoria) and not es_fin_de_semana(fecha),
                    'puede_asignar': _puede_asignar(fecha, agenda.asignados_el(fecha), convocatoria),
                }
                for fecha in semana
            ]
            for semana in _semanas_del_mes(dia)
        ]
        return {
            'semanas': semanas,
            'total': len(agenda.programaciones),
            'programaciones': agenda.programaciones,
            'hay_sin_cobertura': any(not programacion.cubierta for programacion in agenda.programaciones),
        }

    columnas = _columnas(modo, dia, agenda)
    for columna in columnas:
        columna['ausentes'] = [persona for persona in agenda.asignados_el(columna['fecha']) if agenda.ausente(persona.pk, columna['fecha'])]
        columna['asignados'] = _con_tono(agenda.asignados_el(columna['fecha']), tonos)
        columna['fuera_periodo'] = not _en_periodo(columna['fecha'], convocatoria)
        columna['puede_asignar'] = _puede_asignar(columna['fecha'], columna['asignados'], convocatoria)

    # Franja con el nombre de la convocatoria sobre los días de su periodo: cada tramo
    # empieza donde la columna anterior queda fuera (o al inicio) y termina donde la siguiente sale.
    for indice, columna in enumerate(columnas):
        anterior = columnas[indice - 1] if indice else None
        siguiente = columnas[indice + 1] if indice + 1 < len(columnas) else None
        dentro = not columna['fuera_periodo']
        columna['inicia_tramo'] = dentro and (anterior is None or anterior['fuera_periodo'])
        columna['cierra_tramo'] = dentro and (siguiente is None or siguiente['fuera_periodo'])

    filas = [
        {
            'turno': turno,
            'etiqueta': etiqueta_jornada(turno),
            'inicio': HORAS_TURNO[turno][0],
            'fin': HORAS_TURNO[turno][1],
            'celdas': [_celda(columna['fecha'], turno, agenda, convocatoria) for columna in columnas],
        }
        for turno in TURNOS
    ]
    for fila in filas:
        for celda in fila['celdas']:
            celda['cubren_con_tono'] = _con_tono(celda['cubren'], tonos)
    return {
        'columnas': columnas,
        'filas': filas,
        'total': len(agenda.programaciones),
        'programaciones': agenda.programaciones,
        'hay_sin_cobertura': any(not programacion.cubierta for programacion in agenda.programaciones),
    }


def cubren_en_jornada(convocatoria, fecha, jornada):
    """Personal asignados a ese día que trabajan en algún turno de esa jornada, para el formulario.
    Devuelve (los que cubren, si cada turno de la jornada queda cubierto)."""
    agenda = Agenda(convocatoria, fecha, fecha, con_visitas=False)
    turnos = TURNOS_JORNADA[jornada]
    cubren = [persona for persona in agenda.personas if any(agenda.cubre(persona.pk, fecha, turno) for turno in turnos)]
    return cubren, all(agenda.cubren(fecha, turno) for turno in turnos)


def resumen_estados(programaciones):
    """Conteo por estado, con claves sin espacios para usarlas en los templates."""
    conteo = {'pendiente': 0, 'completado': 0, 'no_asistio': 0}
    for programacion in programaciones:
        conteo[programacion.estado.replace(' ', '_')] += 1
    return conteo
