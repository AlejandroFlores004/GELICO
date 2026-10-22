from datetime import datetime, time

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Case, F, IntegerField, Q, When
from django.utils import timezone
from django.utils.dateparse import parse_date
from escuela.models import Escuela


class Jornada(models.TextChoices):
    """Jornada de una visita o del horario de una persona."""
    MANANA = 'manana', 'Mañana'
    TARDE = 'tarde', 'Tarde'
    COMPLETA = 'completa', 'Todo el día'


# Turnos (mañana y tarde) que ocupa cada jornada: "todo el día" ocupa los dos.
TURNOS = (Jornada.MANANA, Jornada.TARDE)
TURNOS_JORNADA = {
    Jornada.MANANA: (Jornada.MANANA,),
    Jornada.TARDE: (Jornada.TARDE,),
    Jornada.COMPLETA: TURNOS,
}
# Horario de referencia de cada turno: sirve para saber si una visita ya empezó o ya terminó.
HORAS_TURNO = {
    Jornada.MANANA: (time(7), time(12)),
    Jornada.TARDE: (time(13), time(17)),
}
# Para ordenar por jornada: primero la mañana (y todo el día, que también empieza en la mañana), luego la tarde.
ORDEN_JORNADA = Case(When(jornada=Jornada.TARDE, then=1), default=0, output_field=IntegerField())


def turnos_de(jornada):
    return TURNOS_JORNADA[jornada]


def jornadas_que_se_cruzan(jornada):
    """Jornadas que comparten al menos un turno con la dada (p. ej. la mañana se cruza con "todo el día")."""
    return [otra for otra in Jornada.values if set(turnos_de(otra)) & set(turnos_de(jornada))]


class Convocatoria(models.Model):
    nombre = models.CharField(max_length=255, unique=True)
    descripcion = models.TextField()
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()

    def __str__(self):
        return self.nombre
    
    class Meta:
        verbose_name = "Convocatoria"
        verbose_name_plural = "Convocatorias"

class Personal(models.Model):
    """Persona que puede salir a las visitas de una convocatoria.

    - Planta: trabajadores de la institución (contadores, técnicos...). No tienen horario fijo
      (llegan cuando se les indica) y no se les toma asistencia; asignados a un día cubren la
      jornada completa.
    - Practicante: jóvenes en prácticas. Tienen horario semanal, cubren las jornadas de su
      horario y se les toma asistencia cada día que trabajan.
    """

    class Tipo(models.TextChoices):
        PLANTA = 'planta', 'Planta'
        PRACTICANTE = 'practicante', 'Practicante'

    tipo = models.CharField('tipo', max_length=20, choices=Tipo.choices, default=Tipo.PRACTICANTE)
    nombre = models.CharField(max_length=255)
    apellido = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    cargo = models.CharField('cargo', max_length=255, blank=True, help_text='Solo personal de planta. Ej. Contador.')
    institucion = models.CharField('institución', max_length=255, blank=True, help_text='Solo practicantes: de dónde vienen.')

    def __str__(self):
        return f"{self.nombre} {self.apellido} - {self.detalle}"

    @property
    def es_practicante(self):
        return self.tipo == self.Tipo.PRACTICANTE

    @property
    def detalle(self):
        """Cargo (planta) o institución (practicante)."""
        return (self.institucion if self.es_practicante else self.cargo) or self.get_tipo_display()

    def clean(self):
        if self.es_practicante and not self.institucion:
            raise ValidationError({'institucion': 'Indica la institución de donde viene el practicante.'})
        if not self.es_practicante and not self.cargo:
            raise ValidationError({'cargo': 'Indica el cargo de la persona (ej. Contador).'})

    class Meta:
        verbose_name = "Personal"
        verbose_name_plural = "Personal"


class ConvocatoriaPersonal(models.Model):
    """Persona asignada a un día de una convocatoria. El día debe caer dentro de la convocatoria.
    Un practicante solo se asigna si su horario semanal incluye ese día (y cubre las jornadas de su
    horario); el personal de planta no tiene horario fijo y cubre el día completo."""
    convocatoria = models.ForeignKey(Convocatoria, on_delete=models.CASCADE, related_name='asignaciones')
    persona = models.ForeignKey(Personal, on_delete=models.CASCADE, related_name='asignaciones')
    fecha = models.DateField('día')

    def __str__(self):
        return f"{self.persona.nombre} {self.persona.apellido} en {self.convocatoria.nombre} ({self.fecha:%d/%m/%Y})"

    def clean(self):
        if not (self.convocatoria_id and self.persona_id and self.fecha):
            return
        if not self.convocatoria.fecha_inicio <= self.fecha <= self.convocatoria.fecha_fin:
            raise ValidationError({'fecha': 'El día debe estar dentro de las fechas de la convocatoria.'})
        if self.persona.es_practicante and not Horario.objects.filter(persona_id=self.persona_id).del_dia(self.fecha).exists():
            raise ValidationError({'fecha': 'El practicante no tiene horario ese día.'})

    class Meta:
        verbose_name = "Personal asignado a un día"
        verbose_name_plural = "Personal asignado a días"
        ordering = ['convocatoria', 'fecha', 'persona']
        constraints = [
            models.UniqueConstraint(fields=['convocatoria', 'persona', 'fecha'], name='convocatoria_persona_dia_unico'),
        ]


class Programacion(models.Model):
    """Visita a una escuela en una jornada. No lleva persona: la cubren las personas de la
    convocatoria cuyo horario incluye esa jornada ese día."""
    convocatoria = models.ForeignKey(Convocatoria, on_delete=models.CASCADE)
    fecha_programada = models.DateField()
    jornada = models.CharField(max_length=10, choices=Jornada.choices)
    escuela = models.ForeignKey(Escuela, on_delete=models.CASCADE)
    estado = models.CharField(max_length=50, choices=[('pendiente', 'Pendiente'), ('completado', 'Completado'), ('no asistio', 'No Asistió')], default='pendiente')

    def __str__(self):
        return f"Programación: {self.convocatoria.nombre} - {self.fecha_programada} {self.get_jornada_display()} - {self.escuela.nombre} - {self.estado}"

    @property
    def turnos(self):
        return turnos_de(self.jornada)

    @property
    def ya_empezo(self):
        """El estado solo se puede marcar cuando empezó la jornada de la visita o ya pasó."""
        fecha = self.fecha_programada
        # Recién creada sin recargar, puede traer la fecha como texto.
        fecha = parse_date(fecha) if isinstance(fecha, str) else fecha
        inicio_jornada = HORAS_TURNO[self.turnos[0]][0]
        return timezone.now() >= timezone.make_aware(datetime.combine(fecha, inicio_jornada))
    
    class Meta:
        verbose_name = "Programación"
        verbose_name_plural = "Programaciones"


class HorarioQuerySet(models.QuerySet):
    def vigentes_entre(self, inicio, fin):
        """Horarios cuyo periodo de labores se cruza con el rango [inicio, fin]."""
        return self.filter(fecha_inicio__lte=fin, fecha_fin__gte=inicio)

    def del_dia(self, fecha):
        """Horarios que aplican en una fecha: su día de la semana y dentro del periodo de labores."""
        return self.vigentes_entre(fecha, fecha).filter(dia=fecha.isoweekday())


class Horario(models.Model):
    """Horario semanal de una persona: se repite cada semana, el mismo día, mientras dure su periodo de labores."""

    class Dia(models.IntegerChoices):
        # Mismos valores que date.isoweekday()
        LUNES = 1, 'Lunes'
        MARTES = 2, 'Martes'
        MIERCOLES = 3, 'Miércoles'
        JUEVES = 4, 'Jueves'
        VIERNES = 5, 'Viernes'
        SABADO = 6, 'Sábado'
        DOMINGO = 7, 'Domingo'

    persona = models.ForeignKey(Personal, on_delete=models.CASCADE)
    dia = models.PositiveSmallIntegerField('día', choices=Dia.choices)
    jornada = models.CharField('jornada', max_length=10, choices=Jornada.choices)
    fecha_inicio = models.DateField('inicio de labores')
    fecha_fin = models.DateField('fin de labores')

    objects = HorarioQuerySet.as_manager()

    def __str__(self):
        return (
            f"Horario: {self.persona.nombre} {self.persona.apellido} - {self.get_dia_display()} "
            f"{self.get_jornada_display()} ({self.fecha_inicio:%d/%m/%Y} al {self.fecha_fin:%d/%m/%Y})"
        )

    @property
    def turnos(self):
        return turnos_de(self.jornada)

    def aplica_en(self, fecha):
        return self.dia == fecha.isoweekday() and self.fecha_inicio <= fecha <= self.fecha_fin

    class Meta:
        verbose_name = "Horario"
        verbose_name_plural = "Horarios"
        ordering = ['persona', 'dia']
        constraints = [
            models.CheckConstraint(
                condition=Q(fecha_fin__gte=F('fecha_inicio')),
                name='horario_periodo_valido',
                violation_error_message='El fin de labores debe ser igual o posterior al inicio de labores.',
            ),
        ]

class Asistencia(models.Model):
    """Asistencia de un practicante en un día que trabaja según su horario (una por día).

    Ausente y justificado significan que ese día no trabajó: no cubre visitas ni se le puede
    asignar. "Justificado" se puede registrar por adelantado (un permiso); los demás estados
    solo desde ese día.
    """

    class Estado(models.TextChoices):
        PRESENTE = 'presente', 'Presente'
        TARDE = 'tarde', 'Llegó tarde'
        AUSENTE = 'ausente', 'Ausente'
        JUSTIFICADO = 'justificado', 'Justificado'

    # Estados en que la persona no trabajó ese día.
    NO_TRABAJO = (Estado.AUSENTE, Estado.JUSTIFICADO)

    persona = models.ForeignKey(Personal, on_delete=models.CASCADE, related_name='asistencias')
    fecha = models.DateField()
    estado = models.CharField(max_length=20, choices=Estado.choices)
    observacion = models.TextField('observación', blank=True, help_text='Motivo de la ausencia o del permiso, o cualquier nota.')

    def __str__(self):
        return f"{self.persona.nombre} {self.persona.apellido} - {self.fecha:%d/%m/%Y}: {self.get_estado_display()}"

    @property
    def no_trabajo(self):
        return self.estado in self.NO_TRABAJO

    def clean(self):
        if not (self.persona_id and self.fecha and self.estado):
            return
        if not self.persona.es_practicante:
            raise ValidationError({'persona': 'La asistencia solo se toma a los practicantes.'})
        if not Horario.objects.filter(persona_id=self.persona_id).del_dia(self.fecha).exists():
            raise ValidationError({'fecha': 'El practicante no tiene horario ese día.'})
        if self.estado != self.Estado.JUSTIFICADO and self.fecha > timezone.localdate():
            raise ValidationError({'estado': 'Por adelantado solo se puede registrar una ausencia justificada.'})

    class Meta:
        verbose_name = "Asistencia"
        verbose_name_plural = "Asistencias"
        ordering = ['-fecha', 'persona__apellido', 'persona__nombre']
        constraints = [
            models.UniqueConstraint(fields=['persona', 'fecha'], name='asistencia_persona_dia_unica'),
        ]