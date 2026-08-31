from decimal import Decimal
from django.db import models
from catalogo.models import Bono
from escuela.models import Escuela

# Create your models here.
class Asignacion(models.Model):
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    escuela = models.ForeignKey(Escuela, on_delete=models.CASCADE)
    bono = models.ForeignKey(Bono, on_delete=models.CASCADE)
    fecha = models.DateField()

    def __str__(self):
        return f"Asignación: {self.escuela.nombre_corto} - {self.bono.nombre} - {self.fecha}"

    @property
    def total_transferido(self):
        total = self.transferencia_set.aggregate(total=models.Sum('monto'))['total']
        return total or Decimal('0')

    @property
    def saldo_disponible(self):
        return self.valor - self.total_transferido

    class Meta:
        verbose_name = "Asignación"
        verbose_name_plural = "Asignaciones"


class Transferencia(models.Model):
    fecha = models.DateField()
    asignacion = models.ForeignKey(Asignacion, on_delete=models.CASCADE)
    monto = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"Transferencia: {self.asignacion.escuela.nombre_corto} - {self.asignacion.bono.nombre} - {self.fecha}"
    
    class Meta:
        verbose_name = "Transferencia"
        verbose_name_plural = "Transferencias"


class Recibo(models.Model):
    fecha = models.DateField()
    transferencia = models.ForeignKey(Transferencia, on_delete=models.CASCADE)
    monto = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"Recibo: {self.transferencia.asignacion.escuela.nombre_corto} - {self.transferencia.asignacion.bono.nombre} - {self.fecha}"
    
    class Meta:
        verbose_name = "Recibo"
        verbose_name_plural = "Recibos"

class Observacion(models.Model):
    fecha = models.DateField()
    recibo = models.ForeignKey(Recibo, on_delete=models.CASCADE)
    comentario = models.TextField()
    resuelto = models.BooleanField(default=False)

    def __str__(self):
        return f"Observación: {self.recibo.transferencia.asignacion.escuela.nombre_corto} - {self.recibo.transferencia.asignacion.bono.nombre} - {self.fecha} - {'Resuelto' if self.resuelto else 'Pendiente'}"
    
    class Meta:
        verbose_name = "Observación"
        verbose_name_plural = "Observaciones"