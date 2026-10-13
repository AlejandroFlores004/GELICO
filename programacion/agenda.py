"""Agenda por bloques de hora de una convocatoria.

Cada día del periodo de la convocatoria se divide en bloques de una hora; en cada bloque se
asignan programaciones. Un auxiliar está "disponible" en un bloque si su horario semanal lo
cubre ese día (y la fecha cae en su periodo de labores), no está ausente ese día y no tiene
otra programación en esa hora.
"""
from calendar import Calendar
from collections import defaultdict
from datetime import datetime, time, timedelta

from django.db.models import Count, Q
from django.utils import timezone

from .models import Auxiliar, Ausencia, Convocatoria, Horario, Programacion

MODOS = ('mes', 'semana', 'dia')
# Bloques de la agenda: de 7:00 a 17:00, una hora cada uno.
PRIMERA_HORA, ULTIMA_HORA = 7, 17
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


def bloques():
    """Horas de inicio de cada bloque de la agenda."""
    return [time(hora) for hora in range(PRIMERA_HORA, ULTIMA_HORA)]


def fin_de_bloque(hora):
    return time(hora.hour + 1, hora.minute) if hora.hour < 23 else time.max


def etiqueta_bloque(hora):
    return f'{hora:%H:%M} – {fin_de_bloque(hora):%H:%M}'


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


def _minutos(hora):
    return hora.hour * 60 + hora.minute


def bloque_paso(dia, hora):
    """Un bloque ya pasó cuando terminó (hasta entonces aún se puede programar)."""
    fin = datetime.combine(dia, time(hora.hour)) + timedelta(hours=1)
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
# Agenda de una convocatoria: bloques de hora
# ---------------------------------------------------------------------------

def horarios_por_fecha(horarios, inicio, fin):
    """Reparte los horarios semanales en cada fecha del rango donde aplican: {(auxiliar_id, fecha): [horarios]}."""
    por_fecha = defaultdict(list)
    for horario in sorted(horarios, key=lambda horario: horario.hora_inicio):
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
        ).select_related('convocatoria', 'auxiliar', 'escuela').order_by('fecha_programada', 'hora_programada')

        # Un auxiliar ocupado en otra convocatoria tampoco está disponible en ese bloque.
        self.ocupadas = set()
        self.programaciones = []
        for programacion in todas:
            if programacion.auxiliar_id:
                self.ocupadas.add((programacion.auxiliar_id, programacion.fecha_programada, programacion.hora_programada.hour))
            if programacion.convocatoria_id == convocatoria.pk:
                self.programaciones.append(programacion)

    def ausente(self, auxiliar_id, dia):
        return (auxiliar_id, dia) in self.ausencias

    def tiene_horario(self, auxiliar_id, dia):
        return bool(self.horarios[(auxiliar_id, dia)])

    def disponible(self, auxiliar_id, dia, hora):
        """Tiene un horario que cubre el bloque, no está ausente y no tiene otra visita a esa hora."""
        if self.ausente(auxiliar_id, dia) or (auxiliar_id, dia, hora.hour) in self.ocupadas:
            return False
        inicio, fin = _minutos(hora), _minutos(hora) + 60
        return any(
            _minutos(horario.hora_inicio) < fin and _minutos(horario.hora_fin) > inicio
            for horario in self.horarios[(auxiliar_id, dia)]
        )


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


def _horas_visibles(agenda):
    horas = {bloque.hour for bloque in bloques()}
    # Si alguna visita quedó fuera de los bloques (p. ej. a las 18:00), se agrega su hora.
    horas |= {programacion.hora_programada.hour for programacion in agenda.programaciones}
    return sorted(horas)


def _celda(columna, hora, agenda, convocatoria):
    fecha = columna['fecha']
    ids = {auxiliar.pk for auxiliar in columna['auxiliares']}
    disponibles = [auxiliar for auxiliar in columna['auxiliares'] if agenda.disponible(auxiliar.pk, fecha, hora)]
    celda = {
        'fecha': fecha,
        'hora': hora,
        'programaciones': [
            programacion for programacion in agenda.programaciones
            if programacion.fecha_programada == fecha
            and (programacion.auxiliar_id in ids or (programacion.auxiliar_id is None and columna.get('sin_auxiliar')))
            and programacion.hora_programada.hour == hora.hour
        ],
        'disponibles': disponibles,
        'de_un_auxiliar': columna['auxiliar'] is not None,
        'solo_sin_auxiliar': columna.get('solo_sin_auxiliar', False),
        'fuera_periodo': not _en_periodo(fecha, convocatoria),
        'paso': bloque_paso(fecha, hora),
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
        {'hora': time(hora), 'celdas': [_celda(columna, time(hora), agenda, convocatoria) for columna in columnas]}
        for hora in _horas_visibles(agenda)
    ]
    return {
        'columnas': columnas,
        'filas': filas,
        'total': len(agenda.programaciones),
        'programaciones': agenda.programaciones,
        'hay_sin_auxiliar': any(programacion.auxiliar_id is None for programacion in agenda.programaciones),
    }


def disponibles_en_bloque(fecha, hora, excluir=None):
    """Auxiliares que pueden tomar un bloque, para sugerirlos en el formulario."""
    auxiliares = list(Auxiliar.objects.order_by('apellido', 'nombre'))
    agenda = Agenda(auxiliares, fecha, fecha, Convocatoria(pk=0))
    if excluir is not None and excluir.auxiliar_id:
        # Al editar, la propia visita no cuenta como ocupación.
        agenda.ocupadas.discard((excluir.auxiliar_id, excluir.fecha_programada, excluir.hora_programada.hour))
    return [auxiliar for auxiliar in auxiliares if agenda.disponible(auxiliar.pk, fecha, hora)]


def resumen_estados(programaciones):
    """Conteo por estado, con claves sin espacios para usarlas en los templates."""
    conteo = {'pendiente': 0, 'completado': 0, 'no_asistio': 0}
    for programacion in programaciones:
        conteo[programacion.estado.replace(' ', '_')] += 1
    return conteo
