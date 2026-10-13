from datetime import datetime

from django.db import models
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_time
from escuela.models import Escuela

# Create your models here.
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


class Programacion(models.Model):
    convocatoria = models.ForeignKey(Convocatoria, on_delete=models.CASCADE)
    # Opcional: una visita puede programarse y asignarle el auxiliar después.
    auxiliar = models.ForeignKey(Auxiliar, on_delete=models.CASCADE, null=True, blank=True)
    fecha_programada = models.DateField()
    hora_programada = models.TimeField()
    escuela = models.ForeignKey(Escuela, on_delete=models.CASCADE)
    estado = models.CharField(max_length=50, choices=[('pendiente', 'Pendiente'), ('completado', 'Completado'), ('no asistio', 'No Asistió')], default='pendiente')

    def __str__(self):
        auxiliar = f"{self.auxiliar.nombre} {self.auxiliar.apellido}" if self.auxiliar else "Sin auxiliar"
        return f"Programación: {self.convocatoria.nombre} - {auxiliar} - {self.fecha_programada} {self.hora_programada} - {self.escuela.nombre} - {self.estado}"

    @property
    def ya_empezo(self):
        """El estado solo se puede marcar cuando llegó la hora de la visita o ya pasó."""
        fecha, hora = self.fecha_programada, self.hora_programada
        # Recién creada sin recargar, puede traer los valores como texto.
        fecha = parse_date(fecha) if isinstance(fecha, str) else fecha
        hora = parse_time(hora) if isinstance(hora, str) else hora
        inicio = timezone.make_aware(datetime.combine(fecha, hora))
        return timezone.now() >= inicio
    
    class Meta:
        verbose_name = "Programación"
        verbose_name_plural = "Programaciones"


class Horario(models.Model):
    auxiliar = models.ForeignKey(Auxiliar, on_delete=models.CASCADE)
    fecha = models.DateField()
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()

    def __str__(self):
        return f"Horario: {self.auxiliar.nombre} {self.auxiliar.apellido} - {self.fecha} {self.hora_inicio} - {self.hora_fin}"
    
    class Meta:
        verbose_name = "Horario"
        verbose_name_plural = "Horarios"

class Ausencia(models.Model):
    auxiliar = models.ForeignKey(Auxiliar, on_delete=models.CASCADE)
    fecha = models.DateField()
    motivo = models.TextField()

    def __str__(self):
        return f"Ausencia: {self.auxiliar.nombre} {self.auxiliar.apellido} - {self.fecha}"
    
    class Meta:
        verbose_name = "Ausencia"
        verbose_name_plural = "Ausencias"