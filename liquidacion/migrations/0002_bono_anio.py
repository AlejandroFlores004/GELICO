from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('liquidacion', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='bono',
            name='anio',
            field=models.PositiveSmallIntegerField(default=2026, verbose_name='Año'),
            preserve_default=False,
        ),
    ]
