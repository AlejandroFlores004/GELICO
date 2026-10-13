from datetime import datetime, time

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Case, F, IntegerField, Q, When
from django.utils import timezone
from django.utils.dateparse import parse_date
from escuela.models import Escuela


class Jornada(models.TextChoices):
    """Jornada de una visita o del horario de un auxiliar."""
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

class Auxiliar(models.Model):
    nombre = models.CharField(max_length=255)
    apellido = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    institucion = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.nombre} {self.apellido} - {self.institucion}"
    
    class Meta:
        verbose_name = "Auxiliar"
        verbose_name_plural = "Auxiliares"


class ConvocatoriaAuxiliar(models.Model):
    """Auxiliar asignado a un día de una convocatoria. Solo se puede asignar si ese día cae dentro de
    la convocatoria y su horario semanal incluye ese día; la jornada en que cubre sale de su horario."""
    convocatoria = models.ForeignKey(Convocatoria, on_delete=models.CASCADE, related_name='asignaciones')
    auxiliar = models.ForeignKey(Auxiliar, on_delete=models.CASCADE, related_name='asignaciones')
    fecha = models.DateField('día')

    def __str__(self):
        return f"{self.auxiliar.nombre} {self.auxiliar.apellido} en {self.convocatoria.nombre} ({self.fecha:%d/%m/%Y})"

    def clean(self):
        if not (self.convocatoria_id and self.auxiliar_id and self.fecha):
            return
        if not self.convocatoria.fecha_inicio <= self.fecha <= self.convocatoria.fecha_fin:
            raise ValidationError({'fecha': 'El día debe estar dentro de las fechas de la convocatoria.'})
        if not Horario.objects.filter(auxiliar_id=self.auxiliar_id).del_dia(self.fecha).exists():
            raise ValidationError({'fecha': 'El auxiliar no tiene horario ese día.'})

    class Meta:
        verbose_name = "Auxiliar asignado a un día"
        verbose_name_plural = "Auxiliares asignados a días"
        ordering = ['convocatoria', 'fecha', 'auxiliar']
        constraints = [
            models.UniqueConstraint(fields=['convocatoria', 'auxiliar', 'fecha'], name='convocatoria_auxiliar_dia_unico'),
        ]


class Programacion(models.Model):
    """Visita a una escuela en una jornada. No lleva auxiliar: la cubren los auxiliares de la
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
    """Horario semanal de un auxiliar: se repite cada semana, el mismo día, mientras dure su periodo de labores."""

    class Dia(models.IntegerChoices):
        # Mismos valores que date.isoweekday()
        LUNES = 1, 'Lunes'
        MARTES = 2, 'Martes'
        MIERCOLES = 3, 'Miércoles'
        JUEVES = 4, 'Jueves'
        VIERNES = 5, 'Viernes'
        SABADO = 6, 'Sábado'
        DOMINGO = 7, 'Domingo'

    auxiliar = models.ForeignKey(Auxiliar, on_delete=models.CASCADE)
    dia = models.PositiveSmallIntegerField('día', choices=Dia.choices)
    jornada = models.CharField('jornada', max_length=10, choices=Jornada.choices)
    fecha_inicio = models.DateField('inicio de labores')
    fecha_fin = models.DateField('fin de labores')

    objects = HorarioQuerySet.as_manager()

    def __str__(self):
        return (
            f"Horario: {self.auxiliar.nombre} {self.auxiliar.apellido} - {self.get_dia_display()} "
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
        ordering = ['auxiliar', 'dia']
        constraints = [
            models.CheckConstraint(
                condition=Q(fecha_fin__gte=F('fecha_inicio')),
                name='horario_periodo_valido',
                violation_error_message='El fin de labores debe ser igual o posterior al inicio de labores.',
            ),
        ]

class Ausencia(models.Model):
    auxiliar = models.ForeignKey(Auxiliar, on_delete=models.CASCADE)
    fecha = models.DateField()
    motivo = models.TextField()

    def __str__(self):
        return f"Ausencia: {self.auxiliar.nombre} {self.auxiliar.apellido} - {self.fecha}"
    
    class Meta:
        verbose_name = "Ausencia"
        verbose_name_plural = "Ausencias"