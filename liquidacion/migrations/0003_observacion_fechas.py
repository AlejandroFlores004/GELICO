import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('liquidacion', '0002_bono_anio'),
    ]

    operations = [
        migrations.AddField(
            model_name='observacion',
            name='fecha_creacion',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now, verbose_name='Fecha de creación'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='observacion',
            name='fecha_resolucion',
            field=models.DateTimeField(blank=True, editable=False, null=True, verbose_name='Fecha de resolución'),
        ),
    ]
