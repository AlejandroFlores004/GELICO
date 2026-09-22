from django.db import models
from catalogo.models import Bono
from escuela.models import Escuela

ESTADO_LIQUIDACION_CHOICES = [
    ('liquidado', 'Liquidado'),
    ('liquidado_sin_observaciones', 'Liquidado sin observaciones'),
    ('no_liquidado', 'No liquidado con observaciones'),
    ('sin_recibos', 'Sin recibos'),
]

# Create your models here.
class Asignacion(models.Model):
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    bono = models.ForeignKey(Bono, on_delete=models.CASCADE)
    escuela = models.ForeignKey(Escuela, on_delete=models.CASCADE)

    def __str__(self):
        return f"Asignación: {self.bono.nombre} - {self.escuela.nombre_corto} - {self.valor}"

    class Meta:
        verbose_name = "Asignación"
        verbose_name_plural = "Asignaciones"


class Recibo(models.Model):
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    asignacion = models.ForeignKey(Asignacion, on_delete=models.CASCADE)

    def __str__(self):
        return f"Recibo: {self.asignacion.bono.nombre} - {self.monto}"

    class Meta:
        verbose_name = "Recibo"
        verbose_name_plural = "Recibos"


class Abono(models.Model):
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    requerimiento = models.CharField(max_length=255)
    estado = models.IntegerField()
    recibo = models.ForeignKey(Recibo, on_delete=models.CASCADE)
    id_planilla_parcial = models.IntegerField()

    def __str__(self):
        return f"Abono: {self.recibo.asignacion.bono.nombre} - {self.monto}"

    class Meta:
        verbose_name = "Abono"
        verbose_name_plural = "Abonos"


class Observacion(models.Model):
    descripcion = models.TextField()
    resuelta = models.BooleanField(default=False)
    recibo = models.ForeignKey(Recibo, on_delete=models.CASCADE)

    def __str__(self):
        return f"Observación: {self.recibo.asignacion.bono.nombre} - {'Resuelta' if self.resuelta else 'Pendiente'}"

    class Meta:
        verbose_name = "Observación"
        verbose_name_plural = "Observaciones"
