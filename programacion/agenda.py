"""Calendario interactivo de programaciones: arma las vistas de mes, semana y día.

Las filas de semana y día son horas; una hora está "disponible" para un auxiliar si tiene
un Horario que la cubre, no está ausente ese día y no tiene otra programación en esa hora.
"""
from calendar import Calendar
from collections import defaultdict
from datetime import datetime, time, timedelta

from django.utils import timezone

from .models import Ausencia, Convocatoria, Horario, Programacion

MODOS = ('mes', 'semana', 'dia')
HORAS_POR_DEFECTO = range(7, 17)
FIN_DE_SEMANA = (6, 7)  # isoweekday: sábado y domingo

# Colores por auxiliar. Se evitan success/warning/error porque esos indican el estado.
TONOS_AUXILIAR = [
    {'tarjeta': 'border-primary bg-primary/8', 'punto': 'bg-primary'},
    {'tarjeta': 'border-info bg-info/10', 'punto': 'bg-info'},
    {'tarjeta': 'border-accent bg-accent/10', 'punto': 'bg-accent'},
    {'tarjeta': 'border-secondary bg-secondary/12', 'punto': 'bg-secondary'},
    {'tarjeta': 'border-neutral/60 bg-neutral/8', 'punto': 'bg-neutral'},
]


def inicio_semana(dia):
    """Domingo con que empieza la semana de una fecha (igual que el calendario anterior)."""
    return dia - timedelta(days=dia.isoweekday() % 7)


def sumar_meses(dia, meses):
    total = dia.year * 12 + (dia.month - 1) + meses
    return dia.replace(year=total // 12, month=total % 12 + 1, day=1)


def rango_visible(modo, dia):
    """Primer y último día que se ven en pantalla."""
    if modo == 'mes':
        semanas = Calendar(firstweekday=6).monthdatescalendar(dia.year, dia.month)
        return semanas[0][0], semanas[-1][-1]
    if modo == 'semana':
        inicio = inicio_semana(dia)
        return inicio, inicio + timedelta(days=6)
    return dia, dia


def tonos_por_auxiliar(auxiliares):
    return {auxiliar.pk: TONOS_AUXILIAR[indice % len(TONOS_AUXILIAR)] for indice, auxiliar in enumerate(auxiliares)}


def _minutos(hora):
    return hora.hour * 60 + hora.minute


def _ya_paso(dia, hora):
    """Una hora del calendario ya pasó cuando terminó (hasta entonces aún se puede programar)."""
    fin = datetime.combine(dia, time(hora)) + timedelta(hours=1)
    return fin <= timezone.localtime().replace(tzinfo=None)


class Agenda:
    """Horarios, ausencias y programaciones de los auxiliares en un rango de fechas."""

    def __init__(self, auxiliares, inicio, fin, convocatoria=None):
        ids = [auxiliar.pk for auxiliar in auxiliares]

        self.horarios = defaultdict(list)
        for horario in Horario.objects.filter(auxiliar__in=ids, fecha__range=(inicio, fin)).order_by('hora_inicio'):
            self.horarios[(horario.auxiliar_id, horario.fecha)].append(horario)

        self.ausencias = {
            (ausencia.auxiliar_id, ausencia.fecha): ausencia
            for ausencia in Ausencia.objects.filter(auxiliar__in=ids, fecha__range=(inicio, fin))
        }

        todas = Programacion.objects.filter(
            auxiliar__in=ids, fecha_programada__range=(inicio, fin),
        ).select_related('convocatoria', 'auxiliar', 'escuela').order_by('fecha_programada', 'hora_programada')

        # La ocupación no depende del filtro: un auxiliar no puede estar en dos visitas a la vez.
        self.ocupadas = set()
        self.programaciones = []
        for programacion in todas:
            self.ocupadas.add((programacion.auxiliar_id, programacion.fecha_programada, programacion.hora_programada.hour))
            if convocatoria is None or programacion.convocatoria_id == convocatoria.pk:
                self.programaciones.append(programacion)

    def ausente(self, auxiliar_id, dia):
        return (auxiliar_id, dia) in self.ausencias

    def trabaja(self, auxiliar_id, dia):
        return bool(self.horarios[(auxiliar_id, dia)]) and not self.ausente(auxiliar_id, dia)

    def horas(self, auxiliar_id, dia):
        """Horas (enteras) que cubre algún horario del auxiliar ese día."""
        horas = set()
        for horario in self.horarios[(auxiliar_id, dia)]:
            inicio, fin = _minutos(horario.hora_inicio), _minutos(horario.hora_fin)
            horas.update(hora for hora in range(24) if inicio < (hora + 1) * 60 and fin > hora * 60)
        return horas

    def libre(self, auxiliar_id, dia, hora):
        """Primera hora exacta en que se le puede programar dentro de esa hora, o None."""
        if self.ausente(auxiliar_id, dia) or (auxiliar_id, dia, hora) in self.ocupadas or _ya_paso(dia, hora):
            return None
        for horario in self.horarios[(auxiliar_id, dia)]:
            inicio, fin = _minutos(horario.hora_inicio), _minutos(horario.hora_fin)
            if inicio < (hora + 1) * 60 and fin > hora * 60:
                return max(time(hora), horario.hora_inicio)
        return None


def _en_periodo(dia, convocatoria):
    return convocatoria is None or convocatoria.fecha_inicio <= dia <= convocatoria.fecha_fin


def _columnas_semana(dia, auxiliares, agenda):
    columnas = []
    for desplazamiento in range(7):
        fecha = inicio_semana(dia) + timedelta(days=desplazamiento)
        # Sábado y domingo solo aparecen si alguien trabaja o hay programaciones.
        if fecha.isoweekday() in FIN_DE_SEMANA:
            hay_trabajo = any(agenda.trabaja(auxiliar.pk, fecha) for auxiliar in auxiliares)
            hay_visitas = any(programacion.fecha_programada == fecha for programacion in agenda.programaciones)
            if not (hay_trabajo or hay_visitas):
                continue
        columnas.append({'fecha': fecha, 'auxiliar': None, 'auxiliares': auxiliares})
    return columnas


def _columnas_dia(dia, auxiliares, agenda):
    if len(auxiliares) == 1:
        return [{'fecha': dia, 'auxiliar': auxiliares[0], 'auxiliares': auxiliares}]

    con_visitas = {programacion.auxiliar_id for programacion in agenda.programaciones}
    columnas = [
        {'fecha': dia, 'auxiliar': auxiliar, 'auxiliares': [auxiliar]}
        for auxiliar in auxiliares
        if agenda.horarios[(auxiliar.pk, dia)] or agenda.ausente(auxiliar.pk, dia) or auxiliar.pk in con_visitas
    ]
    return columnas or [{'fecha': dia, 'auxiliar': None, 'auxiliares': auxiliares}]


def _horas_visibles(columnas, agenda):
    horas = {programacion.hora_programada.hour for programacion in agenda.programaciones}
    for columna in columnas:
        for auxiliar in columna['auxiliares']:
            horas.update(agenda.horas(auxiliar.pk, columna['fecha']))
    if not horas:
        return HORAS_POR_DEFECTO
    return range(min(min(horas), HORAS_POR_DEFECTO.start), max(max(horas), HORAS_POR_DEFECTO.stop - 1) + 1)


def _celda(columna, hora, agenda, convocatoria):
    fecha = columna['fecha']
    ids = {auxiliar.pk for auxiliar in columna['auxiliares']}
    celda = {
        'fecha': fecha,
        'hora': time(hora),
        'programaciones': [
            programacion for programacion in agenda.programaciones
            if programacion.fecha_programada == fecha
            and programacion.auxiliar_id in ids
            and programacion.hora_programada.hour == hora
        ],
        'trabaja': any(
            hora in agenda.horas(auxiliar.pk, fecha) and not agenda.ausente(auxiliar.pk, fecha)
            for auxiliar in columna['auxiliares']
        ),
        'fuera_periodo': not _en_periodo(fecha, convocatoria),
        'paso': _ya_paso(fecha, hora),
    }
    if celda['fuera_periodo']:
        return celda

    libres = {}
    for auxiliar in columna['auxiliares']:
        libre = agenda.libre(auxiliar.pk, fecha, hora)
        if libre:
            libres[auxiliar.pk] = libre
    if libres:
        celda['hora_libre'] = min(libres.values())
        # El formulario se abre con el auxiliar elegido si solo uno está libre.
        if columna['auxiliar']:
            celda['auxiliar_libre'] = columna['auxiliar'].pk
        elif len(libres) == 1:
            celda['auxiliar_libre'] = next(iter(libres))
        celda['total_libres'] = len(libres)
    return celda


def _ausentes(fecha, auxiliares, agenda):
    return [auxiliar for auxiliar in auxiliares if agenda.ausente(auxiliar.pk, fecha)]


def armar_calendario(modo, dia, auxiliares, tonos, convocatoria=None):
    inicio, fin = rango_visible(modo, dia)
    agenda = Agenda(auxiliares, inicio, fin, convocatoria)
    for programacion in agenda.programaciones:
        programacion.tono = tonos.get(programacion.auxiliar_id, TONOS_AUXILIAR[0])

    hoy = timezone.localdate()
    if modo == 'mes':
        semanas = []
        for semana in Calendar(firstweekday=6).monthdatescalendar(dia.year, dia.month):
            semanas.append([
                {
                    'fecha': fecha,
                    'en_mes': fecha.month == dia.month,
                    'programaciones': [p for p in agenda.programaciones if p.fecha_programada == fecha],
                    'disponibles': sum(agenda.trabaja(auxiliar.pk, fecha) for auxiliar in auxiliares),
                    'ausentes': _ausentes(fecha, auxiliares, agenda),
                    'fuera_periodo': not _en_periodo(fecha, convocatoria),
                    'puede_programar': fecha >= hoy and _en_periodo(fecha, convocatoria),
                }
                for fecha in semana
            ])
        return {'semanas': semanas, 'total': len(agenda.programaciones), 'programaciones': agenda.programaciones}

    if modo == 'semana':
        columnas = _columnas_semana(dia, auxiliares, agenda)
    else:
        columnas = _columnas_dia(dia, auxiliares, agenda)
    for columna in columnas:
        columna['ausentes'] = _ausentes(columna['fecha'], columna['auxiliares'], agenda)
        columna['fuera_periodo'] = not _en_periodo(columna['fecha'], convocatoria)
        if columna['auxiliar']:
            columna['tono'] = tonos.get(columna['auxiliar'].pk, TONOS_AUXILIAR[0])

    filas = [
        {'hora': time(hora), 'celdas': [_celda(columna, hora, agenda, convocatoria) for columna in columnas]}
        for hora in _horas_visibles(columnas, agenda)
    ]
    return {
        'columnas': columnas,
        'filas': filas,
        'total': len(agenda.programaciones),
        'programaciones': agenda.programaciones,
        'hay_horarios': any(celda['trabaja'] for fila in filas for celda in fila['celdas']),
    }


def convocatorias_en_rango(inicio, fin):
    return Convocatoria.objects.filter(fecha_inicio__lte=fin, fecha_fin__gte=inicio).order_by('fecha_inicio')


def resumen_estados(programaciones):
    """Conteo por estado, con claves sin espacios para usarlas en los templates."""
    conteo = {'pendiente': 0, 'completado': 0, 'no_asistio': 0}
    for programacion in programaciones:
        conteo[programacion.estado.replace(' ', '_')] += 1
    return conteo
