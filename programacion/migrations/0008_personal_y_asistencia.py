"""Los auxiliares pasan a ser "Personal" (de planta o practicantes) y las ausencias se
reemplazan por la asistencia de los practicantes.

Se renombran tablas y columnas (no se borran), así que los datos se conservan:
- Los auxiliares existentes quedan como practicantes.
- Cada ausencia pasa a ser una asistencia "ausente" con su motivo como observación.
- Los grupos conservan sus permisos: los de auxiliar pasan a personal y quien tenía
  permisos sobre ausencias los recibe sobre asistencias.
"""
import django.db.models.deletion
from django.db import migrations, models

ACCIONES = ('add', 'change', 'delete', 'view')
RENOMBRES_PERMISOS = {
    'auxiliar': ('personal', 'Personal'),
    'convocatoriaauxiliar': ('convocatoriapersonal', 'Personal asignado a un día'),
}


def renombrar_permisos(apps, schema_editor):
    Permission = apps.get_model('auth', 'Permission')
    for modelo_viejo, (modelo_nuevo, nombre) in RENOMBRES_PERMISOS.items():
        for accion in ACCIONES:
            viejo = Permission.objects.filter(content_type__app_label='programacion', codename=f'{accion}_{modelo_viejo}').first()
            if viejo is None:
                continue
            nuevo = Permission.objects.filter(content_type=viejo.content_type, codename=f'{accion}_{modelo_nuevo}').first()
            if nuevo is None:
                viejo.codename = f'{accion}_{modelo_nuevo}'
                viejo.name = f'Can {accion} {nombre}'
                viejo.save()
            else:
                # Ya existía (p. ej. se migró antes en otra base): se pasan los grupos y usuarios.
                for grupo in viejo.group_set.all():
                    grupo.permissions.add(nuevo)
                for usuario in viejo.user_set.all():
                    usuario.user_permissions.add(nuevo)
                viejo.delete()


def ausencias_a_asistencias(apps, schema_editor):
    Ausencia = apps.get_model('programacion', 'Ausencia')
    Asistencia = apps.get_model('programacion', 'Asistencia')
    for ausencia in Ausencia.objects.all():
        Asistencia.objects.update_or_create(
            persona_id=ausencia.persona_id, fecha=ausencia.fecha,
            defaults={'estado': 'ausente', 'observacion': ausencia.motivo},
        )

    # Los permisos de asistencia aún no existen (Django los crea al terminar de migrar).
    ContentType = apps.get_model('contenttypes', 'ContentType')
    Permission = apps.get_model('auth', 'Permission')
    tipo_asistencia, _ = ContentType.objects.get_or_create(app_label='programacion', model='asistencia')
    for accion in ACCIONES:
        nuevo, _ = Permission.objects.get_or_create(
            content_type=tipo_asistencia, codename=f'{accion}_asistencia', defaults={'name': f'Can {accion} Asistencia'},
        )
        viejo = Permission.objects.filter(content_type__app_label='programacion', codename=f'{accion}_ausencia').first()
        if viejo:
            for grupo in viejo.group_set.all():
                grupo.permissions.add(nuevo)
            for usuario in viejo.user_set.all():
                usuario.user_permissions.add(nuevo)


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('contenttypes', '0002_remove_content_type_name'),
        ('programacion', '0007_asignacion_por_dia'),
    ]

    operations = [
        # Auxiliar -> Personal
        migrations.RenameModel('Auxiliar', 'Personal'),
        migrations.RenameModel('ConvocatoriaAuxiliar', 'ConvocatoriaPersonal'),
        migrations.RemoveConstraint(model_name='convocatoriapersonal', name='convocatoria_auxiliar_dia_unico'),
        migrations.RenameField(model_name='convocatoriapersonal', old_name='auxiliar', new_name='persona'),
        migrations.RenameField(model_name='horario', old_name='auxiliar', new_name='persona'),
        migrations.RenameField(model_name='ausencia', old_name='auxiliar', new_name='persona'),
        migrations.AddConstraint(
            model_name='convocatoriapersonal',
            constraint=models.UniqueConstraint(fields=('convocatoria', 'persona', 'fecha'), name='convocatoria_persona_dia_unico'),
        ),
        migrations.AlterModelOptions(
            name='personal',
            options={'verbose_name': 'Personal', 'verbose_name_plural': 'Personal'},
        ),
        migrations.AlterModelOptions(
            name='convocatoriapersonal',
            options={'ordering': ['convocatoria', 'fecha', 'persona'], 'verbose_name': 'Personal asignado a un día', 'verbose_name_plural': 'Personal asignado a días'},
        ),
        migrations.AlterModelOptions(
            name='horario',
            options={'ordering': ['persona', 'dia'], 'verbose_name': 'Horario', 'verbose_name_plural': 'Horarios'},
        ),

        # Planta o practicante
        migrations.AddField(
            model_name='personal',
            name='tipo',
            field=models.CharField(choices=[('planta', 'Planta'), ('practicante', 'Practicante')], default='practicante', max_length=20, verbose_name='tipo'),
        ),
        migrations.AddField(
            model_name='personal',
            name='cargo',
            field=models.CharField(blank=True, default='', help_text='Solo personal de planta. Ej. Contador.', max_length=255, verbose_name='cargo'),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='personal',
            name='institucion',
            field=models.CharField(blank=True, help_text='Solo practicantes: de dónde vienen.', max_length=255, verbose_name='institución'),
        ),
        migrations.RunPython(renombrar_permisos, migrations.RunPython.noop),

        # Ausencia -> Asistencia
        migrations.CreateModel(
            name='Asistencia',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha', models.DateField()),
                ('estado', models.CharField(choices=[('presente', 'Presente'), ('tarde', 'Llegó tarde'), ('ausente', 'Ausente'), ('justificado', 'Justificado')], max_length=20)),
                ('observacion', models.TextField(blank=True, help_text='Motivo de la ausencia o del permiso, o cualquier nota.', verbose_name='observación')),
                ('persona', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='asistencias', to='programacion.personal')),
            ],
            options={
                'verbose_name': 'Asistencia',
                'verbose_name_plural': 'Asistencias',
                'ordering': ['-fecha', 'persona__apellido', 'persona__nombre'],
                'constraints': [models.UniqueConstraint(fields=('persona', 'fecha'), name='asistencia_persona_dia_unica')],
            },
        ),
        migrations.RunPython(ausencias_a_asistencias, migrations.RunPython.noop),
        migrations.DeleteModel(name='Ausencia'),
    ]
