from django.db import models

# Create your models here.
class Distrito(models.Model):
    nombre = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.nombre
    
    class Meta:
        verbose_name = "Distrito"
        verbose_name_plural = "Distritos"

class Escuela(models.Model):
    codigo = models.CharField(max_length=50, unique=True)
    nombre = models.CharField(max_length=255, unique=True)
    nombre_corto = models.CharField(max_length=100, unique=True)
    distrito = models.ForeignKey(Distrito, on_delete=models.CASCADE)
    estado = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.codigo} - {self.nombre} - {self.distrito.nombre}"
    
    class Meta:
        verbose_name = "Escuela"
        verbose_name_plural = "Escuelas"

class CDE(models.Model):
    FechaInicio = models.DateField()
    FechaFin = models.DateField()
    estado = models.BooleanField(default=True)
    escuela = models.ForeignKey(Escuela, on_delete=models.CASCADE)

    def __str__(self):
        return f"CDE: {self.escuela.nombre_corto} - del {self.FechaInicio} al {self.FechaFin}"
    
    class Meta:
        verbose_name = "CDE"
        verbose_name_plural = "CDEs"

class Encargado(models.Model):
    nombre = models.CharField(max_length=255)
    apellido = models.CharField(max_length=255)
    telefono = models.CharField(max_length=20)
    email = models.EmailField(unique=True)
    estado = models.BooleanField(default=True)
    escuela = models.ForeignKey(Escuela, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.nombre} {self.apellido} - {self.escuela.nombre_corto}"
    
    class Meta:
        verbose_name = "Encargado"
        verbose_name_plural = "Encargados"