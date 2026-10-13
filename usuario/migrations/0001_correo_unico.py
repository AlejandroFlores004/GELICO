from django.db import migrations

# El User de Django no exige correo único. Este índice lo garantiza en la base de datos, sin
# distinguir mayúsculas (LOWER) y sin contar los usuarios sin correo (los creados antes de que
# fuera obligatorio, o por createsuperuser si se deja vacío). SQLite y PostgreSQL lo soportan igual.
CREAR = "CREATE UNIQUE INDEX usuario_email_unico ON auth_user (LOWER(email)) WHERE email <> '';"
BORRAR = "DROP INDEX usuario_email_unico;"


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunSQL(CREAR, BORRAR),
    ]
