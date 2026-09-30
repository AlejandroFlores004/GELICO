from django.db import models
from escuela.models import Escuela

ESTADO_LIQUIDACION_CHOICES = [
    ('liquidado', 'Liquidado'),
    ('liquidado_con_observaciones', 'Liquidado con observaciones'),
    ('pendiente_revision', 'Pendiente de revisión'),
]

# Create your models here.
class Bono(models.Model):
    nombre = models.CharField(max_length=255, unique=True)
    descripcion = models.TextField()
    id_sistema = models.IntegerField(null=True, blank=True, unique=True)

    def __str__(self):
        return self.nombre

    class Meta:
        verbose_name = "Bono"
        verbose_name_plural = "Bonos"


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

    @property
    def numero(self):
        """Número correlativo del recibo dentro de su asignación (1, 2, 3...)."""
        return Recibo.objects.filter(asignacion_id=self.asignacion_id, id__lte=self.id).count()

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
    fecha_creacion = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de creación")
    fecha_resolucion = models.DateTimeField(null=True, blank=True, editable=False, verbose_name="Fecha de resolución")

    def save(self, *args, **kwargs):
        # La fecha de resolución se marca al resolverla y se limpia si se reabre.
        if self.resuelta and self.fecha_resolucion is None:
            self.fecha_resolucion = timezone.now()
        elif not self.resuelta:
            self.fecha_resolucion = None
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Observación: {self.recibo.asignacion.bono.nombre} - {'Resuelta' if self.resuelta else 'Pendiente'}"

    class Meta:
        verbose_name = "Observación"
        verbose_name_plural = "Observaciones"
