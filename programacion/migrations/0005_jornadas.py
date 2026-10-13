from datetime import time

from django.db import migrations, models

JORNADAS = [('manana', 'Mañana'), ('tarde', 'Tarde'), ('completa', 'Todo el día')]
MEDIODIA, INICIO_TARDE = time(12), time(13)


def horas_a_jornadas(apps, schema_editor):
    Programacion = apps.get_model('programacion', 'Programacion')
    for programacion in Programacion.objects.all():
        programacion.jornada = 'manana' if programacion.hora_programada < MEDIODIA else 'tarde'
        programacion.save(update_fields=['jornada'])

    Horario = apps.get_model('programacion', 'Horario')
    for horario in Horario.objects.all():
        if horario.hora_inicio < MEDIODIA and horario.hora_fin > INICIO_TARDE:
            horario.jornada = 'completa'
        elif horario.hora_inicio < MEDIODIA:
            horario.jornada = 'manana'
        else:
            horario.jornada = 'tarde'
        horario.save(update_fields=['jornada'])


def jornadas_a_horas(apps, schema_editor):
    inicio = {'manana': time(7), 'tarde': time(13), 'completa': time(7)}
    fin = {'manana': time(12), 'tarde': time(17), 'completa': time(17)}
    Programacion = apps.get_model('programacion', 'Programacion')
    for programacion in Programacion.objects.all():
        programacion.hora_programada = inicio[programacion.jornada]
        programacion.save(update_fields=['hora_programada'])
    Horario = apps.get_model('programacion', 'Horario')
    for horario in Horario.objects.all():
        horario.hora_inicio, horario.hora_fin = inicio[horario.jornada], fin[horario.jornada]
        horario.save(update_fields=['hora_inicio', 'hora_fin'])


class Migration(migrations.Migration):

    dependencies = [
        ('programacion', '0004_horario_semanal'),
    ]

    operations = [
        migrations.AddField(
            model_name='programacion',
            name='jornada',
            field=models.CharField(choices=JORNADAS, max_length=10, null=True),
        ),
        migrations.AddField(
            model_name='horario',
            name='jornada',
            field=models.CharField(choices=JORNADAS, max_length=10, null=True, verbose_name='jornada'),
        ),
        migrations.AlterField(
            model_name='programacion',
            name='hora_programada',
            field=models.TimeField(null=True),
        ),
        migrations.AlterField(
            model_name='horario',
            name='hora_inicio',
            field=models.TimeField(null=True, verbose_name='hora de inicio'),
        ),
        migrations.AlterField(
            model_name='horario',
            name='hora_fin',
            field=models.TimeField(null=True, verbose_name='hora de fin'),
        ),
        migrations.RemoveConstraint(
            model_name='horario',
            name='horario_fin_despues_de_inicio',
        ),
        migrations.RunPython(horas_a_jornadas, jornadas_a_horas),
        migrations.RemoveField(
            model_name='programacion',
            name='hora_programada',
        ),
        migrations.RemoveField(
            model_name='horario',
            name='hora_inicio',
        ),
        migrations.RemoveField(
            model_name='horario',
            name='hora_fin',
        ),
        migrations.AlterField(
            model_name='programacion',
            name='jornada',
            field=models.CharField(choices=JORNADAS, max_length=10),
        ),
        migrations.AlterField(
            model_name='horario',
            name='jornada',
            field=models.CharField(choices=JORNADAS, max_length=10, verbose_name='jornada'),
        ),
        migrations.AlterModelOptions(
            name='horario',
            options={'ordering': ['auxiliar', 'dia'], 'verbose_name': 'Horario', 'verbose_name_plural': 'Horarios'},
        ),
    ]
