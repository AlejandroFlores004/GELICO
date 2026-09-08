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
    email = models.EmailField(unique=True)
    estado = models.BooleanField(default=True)
    escuela = models.ForeignKey(Escuela, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.nombre} {self.apellido} - {self.escuela.nombre_corto}"
    
    class Meta:
        verbose_name = "Encargado"
        verbose_name_plural = "Encargados"

class Telefono(models.Model):
    class Tipo(models.TextChoices):
        FIJO = 'fijo', 'Fijo'
        CELULAR = 'celular', 'Celular'

    class Etiqueta(models.TextChoices):
        PERSONAL = 'personal', 'Personal'
        INSTITUCIONAL = 'institucional', 'Institucional'

    encargado = models.ForeignKey(Encargado, on_delete=models.CASCADE, related_name='telefonos')
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    etiqueta = models.CharField(max_length=20, choices=Etiqueta.choices, default=Etiqueta.PERSONAL)
    numero = models.CharField(max_length=20)

    def __str__(self):
        return f"{self.get_tipo_display()}: {self.numero}"

    class Meta:
        verbose_name = "Teléfono"
        verbose_name_plural = "Teléfonos"
        unique_together = ('encargado', 'tipo')