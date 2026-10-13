"""Agenda por jornadas de una convocatoria.

Cada día del periodo de la convocatoria se divide en dos turnos (mañana y tarde); cada visita
ocupa la jornada de la mañana, la de la tarde o todo el día (ambos turnos). Un auxiliar está
"disponible" para una jornada si su horario semanal cubre todos sus turnos ese día (y la fecha
cae en su periodo de labores), no está ausente ese día y no tiene otra visita en esos turnos.
"""
from calendar import Calendar
from collections import defaultdict
from datetime import datetime, timedelta

from django.db.models import Count, Q
from django.utils import timezone

from .models import HORAS_TURNO, ORDEN_JORNADA, TURNOS, Auxiliar, Ausencia, Convocatoria, Horario, Jornada, Programacion, turnos_de

MODOS = ('mes', 'semana', 'dia')
FIN_DE_SEMANA = (6, 7)  # isoweekday: sábado y domingo

# Colores por auxiliar. Se evitan success/warning/error porque esos indican el estado.
TONOS_AUXILIAR = [
    {'tarjeta': 'border-primary bg-primary/8', 'punto': 'bg-primary'},
    {'tarjeta': 'border-info bg-info/10', 'punto': 'bg-info'},
    {'tarjeta': 'border-accent bg-accent/10', 'punto': 'bg-accent'},
    {'tarjeta': 'border-secondary bg-secondary/12', 'punto': 'bg-secondary'},
    {'tarjeta': 'border-neutral/60 bg-neutral/8', 'punto': 'bg-neutral'},
]
# Visitas que aún no tienen auxiliar asignado.
TONO_SIN_AUXILIAR = {'tarjeta': 'border-dashed border-base-content/30 bg-base-200/70', 'punto': 'bg-base-300'}
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


def tonos_por_auxiliar(auxiliares):
    return {auxiliar.pk: TONOS_AUXILIAR[indice % len(TONOS_AUXILIAR)] for indice, auxiliar in enumerate(auxiliares)}


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
    """Reparte los horarios semanales en cada fecha del rango donde aplican: {(auxiliar_id, fecha): [horarios]}."""
    por_fecha = defaultdict(list)
    for horario in sorted(horarios, key=lambda horario: TURNOS.index(horario.turnos[0])):
        desde, hasta = max(inicio, horario.fecha_inicio), min(fin, horario.fecha_fin)
        # Primer día de la semana del horario a partir de "desde", y luego cada 7 días.
        fecha = desde + timedelta(days=(horario.dia - desde.isoweekday()) % 7)
        while fecha <= hasta:
            por_fecha[(horario.auxiliar_id, fecha)].append(horario)
            fecha += timedelta(days=7)
    return por_fecha


class Agenda:
    """Horarios, ausencias y programaciones de los auxiliares en un rango de fechas."""

    def __init__(self, auxiliares, inicio, fin, convocatoria, incluir_sin_auxiliar=False):
        ids = [auxiliar.pk for auxiliar in auxiliares]

        self.horarios = horarios_por_fecha(
            Horario.objects.filter(auxiliar__in=ids).vigentes_entre(inicio, fin), inicio, fin,
        )

        self.ausencias = {
            (ausencia.auxiliar_id, ausencia.fecha)
            for ausencia in Ausencia.objects.filter(auxiliar__in=ids, fecha__range=(inicio, fin))
        }

        de_quien = Q(auxiliar__in=ids) | Q(auxiliar__isnull=True) if incluir_sin_auxiliar else Q(auxiliar__in=ids)
        todas = Programacion.objects.filter(
            de_quien, fecha_programada__range=(inicio, fin),
        ).select_related('convocatoria', 'auxiliar', 'escuela').order_by('fecha_programada', ORDEN_JORNADA, 'escuela__nombre')

        # Un auxiliar ocupado en otra convocatoria tampoco está disponible en ese turno.
        self.ocupadas = set()
        self.programaciones = []
        for programacion in todas:
            if programacion.auxiliar_id:
                self.ocupar(programacion)
            if programacion.convocatoria_id == convocatoria.pk:
                self.programaciones.append(programacion)

    def _turnos_ocupados(self, programacion):
        return {(programacion.auxiliar_id, programacion.fecha_programada, turno) for turno in programacion.turnos}

    def ocupar(self, programacion):
        self.ocupadas |= self._turnos_ocupados(programacion)

    def liberar(self, programacion):
        self.ocupadas -= self._turnos_ocupados(programacion)

    def ausente(self, auxiliar_id, dia):
        return (auxiliar_id, dia) in self.ausencias

    def tiene_horario(self, auxiliar_id, dia):
        return bool(self.horarios[(auxiliar_id, dia)])

    def turnos_con_horario(self, auxiliar_id, dia):
        return {turno for horario in self.horarios[(auxiliar_id, dia)] for turno in horario.turnos}

    def disponible(self, auxiliar_id, dia, jornada):
        """Su horario cubre todos los turnos de la jornada, no está ausente y no tiene otra visita en ellos."""
        turnos = turnos_de(jornada)
        if self.ausente(auxiliar_id, dia) or any((auxiliar_id, dia, turno) in self.ocupadas for turno in turnos):
            return False
        return set(turnos) <= self.turnos_con_horario(auxiliar_id, dia)


def _en_periodo(dia, convocatoria):
    return convocatoria.fecha_inicio <= dia <= convocatoria.fecha_fin


def _columnas_semana(dia, auxiliares, agenda):
    columnas = []
    for desplazamiento in range(7):
        fecha = inicio_semana(dia) + timedelta(days=desplazamiento)
        # Sábado y domingo solo aparecen si alguien tiene horario o hay visitas ese día.
        if fecha.isoweekday() in FIN_DE_SEMANA:
            hay_horario = any(agenda.tiene_horario(auxiliar.pk, fecha) for auxiliar in auxiliares)
            hay_visitas = any(programacion.fecha_programada == fecha for programacion in agenda.programaciones)
            if not (hay_horario or hay_visitas):
                continue
        columnas.append({'fecha': fecha, 'auxiliar': None, 'auxiliares': auxiliares, 'sin_auxiliar': True})
    return columnas


def _columnas_dia(dia, auxiliares, agenda, incluir_sin_auxiliar):
    if len(auxiliares) == 1 and not incluir_sin_auxiliar:
        return [{'fecha': dia, 'auxiliar': auxiliares[0], 'auxiliares': auxiliares}]

    con_visitas = {programacion.auxiliar_id for programacion in agenda.programaciones}
    columnas = [
        {'fecha': dia, 'auxiliar': auxiliar, 'auxiliares': [auxiliar]}
        for auxiliar in auxiliares
        if agenda.tiene_horario(auxiliar.pk, dia) or agenda.ausente(auxiliar.pk, dia) or auxiliar.pk in con_visitas
    ]
    if not columnas:
        return [{'fecha': dia, 'auxiliar': None, 'auxiliares': auxiliares, 'sin_auxiliar': incluir_sin_auxiliar}]
    if None in con_visitas:
        # Las visitas sin auxiliar van en su propia columna al final.
        columnas.append({'fecha': dia, 'auxiliar': None, 'auxiliares': [], 'sin_auxiliar': True, 'solo_sin_auxiliar': True})
    return columnas


def _celda(columna, turno, agenda, convocatoria):
    fecha = columna['fecha']
    ids = {auxiliar.pk for auxiliar in columna['auxiliares']}
    disponibles = [auxiliar for auxiliar in columna['auxiliares'] if agenda.disponible(auxiliar.pk, fecha, turno)]
    celda = {
        'fecha': fecha,
        'turno': turno,
        # Una visita de todo el día aparece en los dos turnos.
        'programaciones': [
            programacion for programacion in agenda.programaciones
            if programacion.fecha_programada == fecha
            and (programacion.auxiliar_id in ids or (programacion.auxiliar_id is None and columna.get('sin_auxiliar')))
            and turno in programacion.turnos
        ],
        'disponibles': disponibles,
        'de_un_auxiliar': columna['auxiliar'] is not None,
        'solo_sin_auxiliar': columna.get('solo_sin_auxiliar', False),
        'fuera_periodo': not _en_periodo(fecha, convocatoria),
        'paso': turno_paso(fecha, turno),
    }
    celda['puede_programar'] = not celda['fuera_periodo'] and not celda['paso']
    # El formulario se abre con el auxiliar elegido si la columna es suya o es el único disponible.
    if columna['auxiliar']:
        celda['auxiliar_sugerido'] = columna['auxiliar'].pk
    elif len(disponibles) == 1:
        celda['auxiliar_sugerido'] = disponibles[0].pk
    return celda


def agenda_de_convocatoria(convocatoria, modo, dia, auxiliares, tonos, incluir_sin_auxiliar=True):
    """Con incluir_sin_auxiliar=False (al filtrar por un auxiliar) se ocultan las visitas sin asignar."""
    inicio, fin = rango_visible(modo, dia)
    agenda = Agenda(auxiliares, inicio, fin, convocatoria, incluir_sin_auxiliar)
    for programacion in agenda.programaciones:
        programacion.tono = tonos.get(programacion.auxiliar_id, TONOS_AUXILIAR[0]) if programacion.auxiliar_id else TONO_SIN_AUXILIAR

    hoy = timezone.localdate()
    if modo == 'mes':
        semanas = [
            [
                {
                    'fecha': fecha,
                    'en_mes': fecha.month == dia.month,
                    'programaciones': [p for p in agenda.programaciones if p.fecha_programada == fecha],
                    'disponibles': sum(
                        agenda.tiene_horario(auxiliar.pk, fecha) and not agenda.ausente(auxiliar.pk, fecha)
                        for auxiliar in auxiliares
                    ),
                    'ausentes': [auxiliar for auxiliar in auxiliares if agenda.ausente(auxiliar.pk, fecha)],
                    'fuera_periodo': not _en_periodo(fecha, convocatoria),
                    'puede_programar': fecha >= hoy and _en_periodo(fecha, convocatoria),
                }
                for fecha in semana
            ]
            for semana in _semanas_del_mes(dia)
        ]
        return {'semanas': semanas, 'total': len(agenda.programaciones), 'programaciones': agenda.programaciones}

    if modo == 'semana':
        columnas = _columnas_semana(dia, auxiliares, agenda)
    else:
        columnas = _columnas_dia(dia, auxiliares, agenda, incluir_sin_auxiliar)
    for columna in columnas:
        columna['ausentes'] = [auxiliar for auxiliar in columna['auxiliares'] if agenda.ausente(auxiliar.pk, columna['fecha'])]
        columna['fuera_periodo'] = not _en_periodo(columna['fecha'], convocatoria)
        if columna['auxiliar']:
            columna['tono'] = tonos.get(columna['auxiliar'].pk, TONOS_AUXILIAR[0])

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
            'celdas': [_celda(columna, turno, agenda, convocatoria) for columna in columnas],
        }
        for turno in TURNOS
    ]
    return {
        'columnas': columnas,
        'filas': filas,
        'total': len(agenda.programaciones),
        'programaciones': agenda.programaciones,
        'hay_sin_auxiliar': any(programacion.auxiliar_id is None for programacion in agenda.programaciones),
    }


def disponibles_en_jornada(fecha, jornada, excluir=None):
    """Auxiliares que pueden tomar una jornada, para sugerirlos en el formulario."""
    auxiliares = list(Auxiliar.objects.order_by('apellido', 'nombre'))
    agenda = Agenda(auxiliares, fecha, fecha, Convocatoria(pk=0))
    if excluir is not None and excluir.auxiliar_id:
        # Al editar, la propia visita no cuenta como ocupación.
        agenda.liberar(excluir)
    return [auxiliar for auxiliar in auxiliares if agenda.disponible(auxiliar.pk, fecha, jornada)]


def resumen_estados(programaciones):
    """Conteo por estado, con claves sin espacios para usarlas en los templates."""
    conteo = {'pendiente': 0, 'completado': 0, 'no_asistio': 0}
    for programacion in programaciones:
        conteo[programacion.estado.replace(' ', '_')] += 1
    return conteo
