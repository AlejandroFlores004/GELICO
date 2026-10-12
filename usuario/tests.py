from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

User = get_user_model()
CLAVE = 'Clave-Segura-2026'


class GestionUsuariosBase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('admin', password=CLAVE, is_staff=True)
        self.client.login(username='admin', password=CLAVE)

    def _datos_usuario(self, **extra):
        datos = {
            'username': 'nuevo',
            'first_name': 'Nuevo',
            'last_name': 'Usuario',
            'email': 'nuevo@example.com',
            'password1': 'Otra-Clave-2026',
            'password2': 'Otra-Clave-2026',
            'is_active': 'on',
        }
        datos.update(extra)
        return datos


class AccesoTests(GestionUsuariosBase):
    def test_anonimo_va_al_login(self):
        self.client.logout()
        respuesta = self.client.get(reverse('home_usuarios'))
        self.assertRedirects(respuesta, f"{reverse('login')}?next={reverse('home_usuarios')}")

    def test_usuario_sin_rol_administrador_no_entra(self):
        User.objects.create_user('comun', password=CLAVE)
        self.client.login(username='comun', password=CLAVE)
        self.assertEqual(self.client.get(reverse('home_usuarios')).status_code, 403)
        self.assertEqual(self.client.get(reverse('home_grupos')).status_code, 403)

    def test_administrador_no_puede_tocar_un_superusuario(self):
        jefe = User.objects.create_superuser('jefe', password=CLAVE)
        for nombre in ('usuario_editar', 'usuario_contrasena', 'usuario_toggle', 'usuario_eliminar'):
            with self.subTest(vista=nombre):
                self.assertEqual(self.client.get(reverse(nombre, args=[jefe.pk])).status_code, 403)

    def test_administrador_no_ve_la_opcion_de_superusuario(self):
        respuesta = self.client.get(reverse('usuario_nuevo'))
        self.assertNotIn('is_superuser', respuesta.context['form'].fields)


class UsuarioTests(GestionUsuariosBase):
    def test_crea_usuario_con_contrasena_y_grupos(self):
        grupo = Group.objects.create(name='Técnicos')
        respuesta = self.client.post(reverse('usuario_nuevo'), self._datos_usuario(groups=[grupo.pk]))
        self.assertTemplateUsed(respuesta, 'partials/usuario/modal_form_success.html')

        usuario = User.objects.get(username='nuevo')
        self.assertTrue(usuario.check_password('Otra-Clave-2026'))
        self.assertEqual(list(usuario.groups.all()), [grupo])

    def test_rechaza_contrasenas_distintas_y_debiles(self):
        respuesta = self.client.post(reverse('usuario_nuevo'), self._datos_usuario(password2='diferente'))
        self.assertIn('password2', respuesta.context['form'].errors)

        respuesta = self.client.post(reverse('usuario_nuevo'), self._datos_usuario(password1='12345678', password2='12345678'))
        self.assertIn('password1', respuesta.context['form'].errors)
        self.assertFalse(User.objects.filter(username='nuevo').exists())

    def test_rechaza_correo_repetido(self):
        User.objects.create_user('otro', email='Nuevo@Example.com', password=CLAVE)
        respuesta = self.client.post(reverse('usuario_nuevo'), self._datos_usuario())
        self.assertIn('email', respuesta.context['form'].errors)

    def test_no_puede_quitarse_acceso_a_si_mismo(self):
        respuesta = self.client.post(reverse('usuario_editar', args=[self.admin.pk]), {'username': 'admin'})
        errores = respuesta.context['form'].errors
        self.assertIn('is_active', errores)
        self.assertIn('is_staff', errores)

    def test_no_puede_desactivarse_ni_eliminarse_a_si_mismo(self):
        self.client.post(reverse('usuario_toggle', args=[self.admin.pk]))
        self.client.post(reverse('usuario_eliminar', args=[self.admin.pk]))
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_activa_y_desactiva_otro_usuario(self):
        otro = User.objects.create_user('otro', password=CLAVE)
        self.client.post(reverse('usuario_toggle', args=[otro.pk]))
        otro.refresh_from_db()
        self.assertFalse(otro.is_active)

    def test_cambiar_contrasena_propia_mantiene_la_sesion(self):
        self.client.post(reverse('usuario_contrasena', args=[self.admin.pk]), {
            'new_password1': 'Nueva-Clave-2026', 'new_password2': 'Nueva-Clave-2026',
        })
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password('Nueva-Clave-2026'))
        self.assertEqual(self.client.get(reverse('home_usuarios')).status_code, 200)

    def test_filtra_por_grupo_y_rol(self):
        grupo = Group.objects.create(name='Revisores')
        revisor = User.objects.create_user('revisor', password=CLAVE)
        revisor.groups.add(grupo)

        respuesta = self.client.get(reverse('buscar_usuarios'), {'grupo': grupo.pk, 'rol': 'usuario'})
        self.assertEqual(list(respuesta.context['usuarios']), [revisor])

    def test_imprimir_genera_pdf(self):
        respuesta = self.client.get(reverse('usuario_imprimir'))
        self.assertEqual(respuesta['Content-Type'], 'application/pdf')


class GrupoTests(GestionUsuariosBase):
    def test_crea_grupo_con_permisos_y_usuarios(self):
        ver_escuela = Permission.objects.get(codename='view_escuela')
        miembro = User.objects.create_user('miembro', password=CLAVE)

        respuesta = self.client.post(reverse('grupo_nuevo'), {
            'name': 'Consulta', 'permissions': [ver_escuela.pk], 'usuarios': [miembro.pk],
        })
        self.assertTemplateUsed(respuesta, 'partials/grupo/modal_form_success.html')

        grupo = Group.objects.get(name='Consulta')
        self.assertEqual(list(grupo.permissions.all()), [ver_escuela])
        self.assertEqual(list(grupo.user_set.all()), [miembro])
        self.assertTrue(miembro.has_perm('escuela.view_escuela'))

    def test_conserva_permisos_que_la_pantalla_no_muestra(self):
        externo = Permission.objects.get(codename='view_session')
        grupo = Group.objects.create(name='Mixto')
        grupo.permissions.add(externo)

        self.client.post(reverse('grupo_editar', args=[grupo.pk]), {'name': 'Mixto'})
        self.assertIn(externo, grupo.permissions.all())

    def test_matriz_agrupa_por_modulo_y_accion(self):
        respuesta = self.client.get(reverse('grupo_nuevo'))
        matriz = respuesta.context['form'].matriz_permisos()
        apps = [app['app'] for app in matriz]
        self.assertIn('Escuelas', apps)
        self.assertNotIn('Sessions', apps)

        fila = next(fila for app in matriz for fila in app['filas'])
        self.assertEqual([celda['accion'] for celda in fila['celdas'] if celda], ['view', 'add', 'change', 'delete'])

    def test_eliminar_grupo_no_elimina_usuarios(self):
        grupo = Group.objects.create(name='Temporal')
        miembro = User.objects.create_user('miembro', password=CLAVE)
        miembro.groups.add(grupo)

        self.client.post(reverse('grupo_eliminar', args=[grupo.pk]))
        self.assertFalse(Group.objects.filter(pk=grupo.pk).exists())
        self.assertTrue(User.objects.filter(pk=miembro.pk).exists())

    def test_imprimir_genera_pdf(self):
        grupo = Group.objects.create(name='Consulta')
        grupo.permissions.add(Permission.objects.get(codename='view_escuela'))
        respuesta = self.client.get(reverse('grupo_imprimir'))
        self.assertEqual(respuesta['Content-Type'], 'application/pdf')
