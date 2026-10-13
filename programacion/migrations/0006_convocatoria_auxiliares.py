import django.db.models.deletion
from django.db import migrations, models


def auxiliares_de_visitas_a_convocatoria(apps, schema_editor):
    """Cada auxiliar que tenía visitas asignadas pasa a participar en la convocatoria de esas visitas."""
    Programacion = apps.get_model('programacion', 'Programacion')
    ConvocatoriaAuxiliar = apps.get_model('programacion', 'ConvocatoriaAuxiliar')
    parejas = Programacion.objects.exclude(auxiliar=None).values_list('convocatoria_id', 'auxiliar_id').distinct()
    ConvocatoriaAuxiliar.objects.bulk_create(
        [ConvocatoriaAuxiliar(convocatoria_id=convocatoria, auxiliar_id=auxiliar) for convocatoria, auxiliar in parejas],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('programacion', '0005_jornadas'),
    ]

    operations = [
        migrations.CreateModel(
            name='ConvocatoriaAuxiliar',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('auxiliar', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='programacion.auxiliar')),
                ('convocatoria', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='programacion.convocatoria')),
            ],
            options={
                'verbose_name': 'Auxiliar de convocatoria',
                'verbose_name_plural': 'Auxiliares de convocatoria',
            },
        ),
        migrations.AddField(
            model_name='convocatoria',
            name='auxiliares',
            field=models.ManyToManyField(blank=True, related_name='convocatorias', through='programacion.ConvocatoriaAuxiliar', to='programacion.auxiliar'),
        ),
        migrations.AddConstraint(
            model_name='convocatoriaauxiliar',
            constraint=models.UniqueConstraint(fields=('convocatoria', 'auxiliar'), name='convocatoria_auxiliar_unico'),
        ),
        migrations.RunPython(auxiliares_de_visitas_a_convocatoria, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='programacion',
            name='auxiliar',
        ),
    ]
