from django.db import models

# Create your models here.
class Bono(models.Model):
    nombre = models.CharField(max_length=255, unique=True)
    descripcion = models.TextField()
    id_sistema = models.IntegerField(null=True, blank=True, unique=True)

    def __str__(self):
        return self.nombre

    def meta(self):
        verbose_name = "Bono"
        verbose_name_plural = "Bonos"