from django.db import migrations, models


def fecha_a_semanal(apps, schema_editor):
    """Un horario de una fecha concreta pasa a ser ese día de la semana, solo durante esa fecha."""
    Horario = apps.get_model('programacion', 'Horario')
    for horario in Horario.objects.all():
        horario.dia = horario.fecha.isoweekday()
        horario.fecha_inicio = horario.fecha
        horario.fecha_fin = horario.fecha
        horario.save(update_fields=['dia', 'fecha_inicio', 'fecha_fin'])


def semanal_a_fecha(apps, schema_editor):
    Horario = apps.get_model('programacion', 'Horario')
    for horario in Horario.objects.all():
        horario.fecha = horario.fecha_inicio
        horario.save(update_fields=['fecha'])


class Migration(migrations.Migration):

    dependencies = [
        ('programacion', '0003_programacion_auxiliar_opcional'),
    ]

    operations = [
        migrations.AddField(
            model_name='horario',
            name='dia',
            field=models.PositiveSmallIntegerField(choices=[(1, 'Lunes'), (2, 'Martes'), (3, 'Miércoles'), (4, 'Jueves'), (5, 'Viernes'), (6, 'Sábado'), (7, 'Domingo')], null=True, verbose_name='día'),
        ),
        migrations.AddField(
            model_name='horario',
            name='fecha_inicio',
            field=models.DateField(null=True, verbose_name='inicio de labores'),
        ),
        migrations.AddField(
            model_name='horario',
            name='fecha_fin',
            field=models.DateField(null=True, verbose_name='fin de labores'),
        ),
        migrations.AlterField(
            model_name='horario',
            name='fecha',
            field=models.DateField(null=True),
        ),
        migrations.RunPython(fecha_a_semanal, semanal_a_fecha),
        migrations.RemoveField(
            model_name='horario',
            name='fecha',
        ),
        migrations.AlterField(
            model_name='horario',
            name='dia',
            field=models.PositiveSmallIntegerField(choices=[(1, 'Lunes'), (2, 'Martes'), (3, 'Miércoles'), (4, 'Jueves'), (5, 'Viernes'), (6, 'Sábado'), (7, 'Domingo')], verbose_name='día'),
        ),
        migrations.AlterField(
            model_name='horario',
            name='fecha_inicio',
            field=models.DateField(verbose_name='inicio de labores'),
        ),
        migrations.AlterField(
            model_name='horario',
            name='fecha_fin',
            field=models.DateField(verbose_name='fin de labores'),
        ),
        migrations.AlterField(
            model_name='horario',
            name='hora_inicio',
            field=models.TimeField(verbose_name='hora de inicio'),
        ),
        migrations.AlterField(
            model_name='horario',
            name='hora_fin',
            field=models.TimeField(verbose_name='hora de fin'),
        ),
        migrations.AlterModelOptions(
            name='horario',
            options={'ordering': ['auxiliar', 'dia', 'hora_inicio'], 'verbose_name': 'Horario', 'verbose_name_plural': 'Horarios'},
        ),
        migrations.AddConstraint(
            model_name='horario',
            constraint=models.CheckConstraint(condition=models.Q(('hora_fin__gt', models.F('hora_inicio'))), name='horario_fin_despues_de_inicio', violation_error_message='La hora de fin debe ser posterior a la hora de inicio.'),
        ),
        migrations.AddConstraint(
            model_name='horario',
            constraint=models.CheckConstraint(condition=models.Q(('fecha_fin__gte', models.F('fecha_inicio'))), name='horario_periodo_valido', violation_error_message='El fin de labores debe ser igual o posterior al inicio de labores.'),
        ),
    ]
