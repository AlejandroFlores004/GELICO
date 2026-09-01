from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('liquidacion', '0003_rename_fecha_asignacion_asignacion_fecha'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='observacion',
            options={'ordering': ['-fecha'], 'verbose_name': 'Observación', 'verbose_name_plural': 'Observaciones'},
        ),
        migrations.AlterModelOptions(
            name='recibo',
            options={'ordering': ['-fecha'], 'verbose_name': 'Recibo', 'verbose_name_plural': 'Recibos'},
        ),
    ]
