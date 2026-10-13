from datetime import timedelta

import django.db.models.deletion
from django.db import migrations, models


def a_dias_con_horario(apps, schema_editor):
    """Una asignación a toda la convocatoria pasa a ser una por cada día de la convocatoria
    en que el auxiliar tiene horario."""
    ConvocatoriaAuxiliar = apps.get_model('programacion', 'ConvocatoriaAuxiliar')
    Horario = apps.get_model('programacion', 'Horario')
    nuevas = []
    for asignacion in ConvocatoriaAuxiliar.objects.filter(fecha__isnull=True).select_related('convocatoria'):
        convocatoria = asignacion.convocatoria
        dias = set()
        for horario in Horario.objects.filter(
            auxiliar_id=asignacion.auxiliar_id,
            fecha_inicio__lte=convocatoria.fecha_fin,
            fecha_fin__gte=convocatoria.fecha_inicio,
        ):
            desde = max(convocatoria.fecha_inicio, horario.fecha_inicio)
            hasta = min(convocatoria.fecha_fin, horario.fecha_fin)
            fecha = desde + timedelta(days=(horario.dia - desde.isoweekday()) % 7)
            while fecha <= hasta:
                dias.add(fecha)
                fecha += timedelta(days=7)
        nuevas += [
            ConvocatoriaAuxiliar(convocatoria_id=convocatoria.pk, auxiliar_id=asignacion.auxiliar_id, fecha=fecha)
            for fecha in sorted(dias)
        ]
    ConvocatoriaAuxiliar.objects.filter(fecha__isnull=True).delete()
    ConvocatoriaAuxiliar.objects.bulk_create(nuevas)


class Migration(migrations.Migration):

    dependencies = [
        ('programacion', '0006_convocatoria_auxiliares'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='convocatoriaauxiliar',
            name='convocatoria_auxiliar_unico',
        ),
        migrations.AddField(
            model_name='convocatoriaauxiliar',
            name='fecha',
            field=models.DateField(null=True, verbose_name='día'),
        ),
        migrations.RunPython(a_dias_con_horario, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='convocatoriaauxiliar',
            name='fecha',
            field=models.DateField(verbose_name='día'),
        ),
        migrations.RemoveField(
            model_name='convocatoria',
            name='auxiliares',
        ),
        migrations.AlterField(
            model_name='convocatoriaauxiliar',
            name='convocatoria',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='asignaciones', to='programacion.convocatoria'),
        ),
        migrations.AlterField(
            model_name='convocatoriaauxiliar',
            name='auxiliar',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='asignaciones', to='programacion.auxiliar'),
        ),
        migrations.AlterModelOptions(
            name='convocatoriaauxiliar',
            options={'ordering': ['convocatoria', 'fecha', 'auxiliar'], 'verbose_name': 'Auxiliar asignado a un día', 'verbose_name_plural': 'Auxiliares asignados a días'},
        ),
        migrations.AddConstraint(
            model_name='convocatoriaauxiliar',
            constraint=models.UniqueConstraint(fields=('convocatoria', 'auxiliar', 'fecha'), name='convocatoria_auxiliar_dia_unico'),
        ),
    ]
