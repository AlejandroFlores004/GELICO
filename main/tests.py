from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from easyaudit.models import CRUDEvent, LoginEvent

from escuela.models import Distrito, Escuela
from liquidacion.models import Asignacion, Bono, Observacion, Recibo
from liquidacion.services import estado_liquidacion
from . import services


class AuditoriaTests(TestCase):
    def setUp(self):
        # easyaudit registra los cambios con transaction.on_commit, que TestCase no dispara solo.
        with self.captureOnCommitCallbacks(execute=True):
            self.usuario = get_user_model().objects.create_user(
                username='auditor', password='clave-segura-123', first_name='Ana', last_name='Pérez', is_staff=True,
            )
            self.client.login(username='auditor', password='clave-segura-123')
            self.distrito = Distrito.objects.create(nombre='Distrito auditado')
            self.escuela = Escuela.objects.create(
                codigo='AUD-1', nombre='Escuela auditada', nombre_corto='Auditada', distrito=self.distrito,
            )

    def test_requiere_iniciar_sesion(self):
        self.client.logout()
        respuesta = self.client.get(reverse('home_auditoria'))
        self.assertRedirects(respuesta, f"{reverse('login')}?next={reverse('home_auditoria')}")

    def test_las_tres_pestanas_cargan(self):
        for vista in ('cambios', 'accesos', 'solicitudes'):
            with self.subTest(vista=vista):
                respuesta = self.client.get(reverse('home_auditoria'), {'vista': vista})
                self.assertEqual(respuesta.status_code, 200)
                self.assertEqual(respuesta.context['vista'], vista)

    def test_filtra_cambios_por_modulo_y_texto(self):
        evento_escuela = CRUDEvent.objects.get(object_repr__icontains='Escuela auditada', event_type=CRUDEvent.CREATE)
        respuesta = self.client.get(reverse('buscar_auditoria'), {
            'vista': 'cambios',
            'modulo': evento_escuela.content_type_id,
            'q': 'auditada',
        })
        eventos = list(respuesta.context['eventos'])
        self.assertEqual([evento.pk for evento in eventos], [evento_escuela.pk])
        self.assertEqual(eventos[0].accion, 'Creación')

    def test_rango_de_fechas_invalido_muestra_aviso(self):
        respuesta = self.client.get(reverse('buscar_auditoria'), {
            'vista': 'cambios', 'desde': '2026-05-10', 'hasta': '2026-05-01',
        })
        self.assertContains(respuesta, 'No se aplicaron los filtros')

    def test_filtra_intentos_fallidos_sin_usuario_enlazado(self):
        LoginEvent.objects.create(login_type=LoginEvent.FAILED, username='auditor', remote_ip='10.0.0.5')

        respuesta = self.client.get(reverse('buscar_auditoria'), {
            'vista': 'accesos', 'tipo_acceso': LoginEvent.FAILED, 'usuario': self.usuario.pk,
        })
        eventos = list(respuesta.context['eventos'])
        self.assertEqual(len(eventos), 1)
        self.assertEqual(eventos[0].tipo, 'Intento fallido')

    def test_detalle_muestra_antes_y_despues(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.escuela.nombre = 'Escuela renombrada'
            self.escuela.save()
        evento = CRUDEvent.objects.filter(event_type=CRUDEvent.UPDATE, object_id=str(self.escuela.pk)).latest('datetime')

        respuesta = self.client.get(reverse('auditoria_detalle', args=[evento.pk]))
        self.assertEqual(respuesta.context['tipo_detalle'], 'cambios')
        self.assertContains(respuesta, 'Escuela auditada')
        self.assertContains(respuesta, 'Escuela renombrada')
        self.assertEqual(respuesta.context['total_historial'], 2)

    def test_detalle_de_creacion_resuelve_llaves_foraneas(self):
        evento = CRUDEvent.objects.get(event_type=CRUDEvent.CREATE, object_id=str(self.escuela.pk), object_repr__icontains='auditada')
        respuesta = self.client.get(reverse('auditoria_detalle', args=[evento.pk]))
        self.assertEqual(respuesta.context['tipo_detalle'], 'registro')
        self.assertContains(respuesta, str(self.distrito))

    def test_detalle_oculta_la_contrasena(self):
        evento = CRUDEvent.objects.filter(content_type__app_label='auth', object_id=str(self.usuario.pk)).first()
        respuesta = self.client.get(reverse('auditoria_detalle', args=[evento.pk]))
        self.assertNotContains(respuesta, 'pbkdf2')
        self.assertNotContains(respuesta, self.usuario.password)

    def test_imprimir_genera_pdf_de_cada_pestana(self):
        for vista in ('cambios', 'accesos', 'solicitudes'):
            with self.subTest(vista=vista):
                respuesta = self.client.get(reverse('auditoria_imprimir'), {'vista': vista})
                self.assertEqual(respuesta['Content-Type'], 'application/pdf')
                self.assertTrue(respuesta.content.startswith(b'%PDF'))


class SeguridadTests(TestCase):
    """Sesión obligatoria en todo el sitio y permisos por apartado."""

    CLAVE = 'clave-segura-123'

    def setUp(self):
        self.usuario = get_user_model().objects.create_user('operador', password=self.CLAVE)
        self.bono = Bono.objects.create(nombre='Bono 2026', descripcion='', anio=2026)

    def _dar_permisos(self, *codenames):
        self.usuario.user_permissions.add(*Permission.objects.filter(codename__in=codenames))

    def _entrar(self):
        self.client.login(username='operador', password=self.CLAVE)

    def test_sin_sesion_redirige_al_login(self):
        for nombre in ('home', 'home_bonos', 'home_escuelas', 'home_programacion', 'home_usuarios'):
            with self.subTest(vista=nombre):
                url = reverse(nombre)
                self.assertRedirects(self.client.get(url), f"{reverse('login')}?next={url}", fetch_redirect_response=False)

    def test_sin_sesion_en_htmx_redirige_la_pagina_completa(self):
        respuesta = self.client.get(
            reverse('bono_nuevo'), headers={'HX-Request': 'true', 'HX-Current-URL': 'http://testserver/liquidacion/bono/'},
        )
        self.assertEqual(respuesta['HX-Redirect'], f"{reverse('login')}?next=/liquidacion/bono/")

    def test_login_vuelve_a_la_pagina_pedida_solo_si_es_del_sitio(self):
        datos = {'username': 'operador', 'password': self.CLAVE}
        respuesta = self.client.post(f"{reverse('login')}?next={reverse('home_bonos')}", datos)
        self.assertRedirects(respuesta, reverse('home_bonos'), fetch_redirect_response=False)
        self.client.logout()
        respuesta = self.client.post(f"{reverse('login')}?next=https://sitio-malicioso.com/", datos)
        self.assertRedirects(respuesta, reverse('home'), fetch_redirect_response=False)

    def test_logout_solo_por_post(self):
        self._entrar()
        self.assertEqual(self.client.get(reverse('logout')).status_code, 405)
        self.assertRedirects(self.client.post(reverse('logout')), reverse('login'))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_sin_permiso_muestra_pagina_403(self):
        self._entrar()
        respuesta = self.client.get(reverse('home_bonos'))
        self.assertEqual(respuesta.status_code, 403)
        self.assertTemplateUsed(respuesta, '403.html')

    def test_permisos_por_accion(self):
        self._dar_permisos('view_bono')
        self._entrar()
        self.assertEqual(self.client.get(reverse('home_bonos')).status_code, 200)
        self.assertEqual(self.client.get(reverse('bono_nuevo')).status_code, 403)
        self.assertEqual(self.client.get(reverse('bono_editar', args=[self.bono.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse('bono_eliminar', args=[self.bono.pk])).status_code, 403)
        self.assertTrue(Bono.objects.filter(pk=self.bono.pk).exists())

        self._dar_permisos('add_bono')
        self.assertEqual(self.client.get(reverse('bono_nuevo')).status_code, 200)
        self.assertEqual(self.client.get(reverse('bono_editar', args=[self.bono.pk])).status_code, 403)

        self._dar_permisos('change_bono')
        self.assertEqual(self.client.get(reverse('bono_editar', args=[self.bono.pk])).status_code, 200)

    def test_auditoria_y_usuarios_solo_para_administradores(self):
        self._entrar()
        for nombre in ('home_auditoria', 'home_usuarios', 'home_grupos'):
            with self.subTest(vista=nombre):
                self.assertEqual(self.client.get(reverse(nombre)).status_code, 403)

    def test_sidebar_muestra_solo_apartados_permitidos(self):
        self._dar_permisos('view_bono')
        self._entrar()
        respuesta = self.client.get(reverse('home'))
        self.assertContains(respuesta, reverse('home_bonos'))
        self.assertNotContains(respuesta, reverse('home_asignaciones'))
        self.assertNotContains(respuesta, reverse('home_escuelas'))
        self.assertNotContains(respuesta, reverse('home_auditoria'))

    def test_pagina_404(self):
        respuesta = self.client.get('/no-existe/')
        self.assertEqual(respuesta.status_code, 404)
        self.assertTemplateUsed(respuesta, '404.html')


class PanelInicioServicesTests(TestCase):
    def setUp(self):
        distrito = Distrito.objects.create(nombre='Distrito panel')
        self.escuela = Escuela.objects.create(codigo='PAN-1', nombre='Escuela panel', nombre_corto='Panel', distrito=distrito)
        self.bono_2025 = Bono.objects.create(nombre='Bono 2025', descripcion='', anio=2025)
        self.bono_2026 = Bono.objects.create(nombre='Bono 2026', descripcion='', anio=2026)

    def test_elegir_anio(self):
        anios = services.anios_disponibles()
        self.assertEqual(anios, [2026, 2025])
        self.assertEqual(services.elegir_anio(None, anios), 2026)
        self.assertEqual(services.elegir_anio('2025', anios), 2025)
        self.assertEqual(services.elegir_anio('1999', anios), 2026)
        self.assertIsNone(services.elegir_anio('todos', anios))
        self.assertIsNone(services.elegir_anio(None, []))

    def test_porcentaje(self):
        self.assertEqual(services.porcentaje(1, 3), 33.3)
        self.assertEqual(services.porcentaje(5, 0), 0)

    def test_resumen_liquidacion_usa_el_mismo_criterio_que_liquidacion(self):
        sin_recibos = Asignacion.objects.create(escuela=self.escuela, bono=self.bono_2025, valor=Decimal('100'))
        con_observacion = Asignacion.objects.create(escuela=self.escuela, bono=self.bono_2026, valor=Decimal('300'))
        recibo = Recibo.objects.create(asignacion=con_observacion, monto=Decimal('120'))
        Observacion.objects.create(recibo=recibo, descripcion='Falta firma')

        resumen = services.resumen_liquidacion(Asignacion.objects.all(), Recibo.objects.all())

        self.assertEqual(resumen['asignado'], Decimal('400'))
        self.assertEqual(resumen['recibido'], Decimal('120'))
        self.assertEqual(resumen['porcentaje_recibido'], 30.0)
        por_estado = {estado['clave']: estado['cantidad'] for estado in resumen['estados']}
        for asignacion in (sin_recibos, con_observacion):
            estado = estado_liquidacion(list(asignacion.recibo_set.all()))
            self.assertEqual(por_estado[estado], 1, estado)

    def test_panel_filtra_por_anio(self):
        Asignacion.objects.create(escuela=self.escuela, bono=self.bono_2025, valor=Decimal('100'))
        asignacion = Asignacion.objects.create(escuela=self.escuela, bono=self.bono_2026, valor=Decimal('300'))
        Recibo.objects.create(asignacion=asignacion, monto=Decimal('350'))  # sobrepagada

        panel = services.panel_inicio(2026, timezone.localdate())

        self.assertEqual(panel['resumen']['asignado'], Decimal('300'))
        self.assertEqual(panel['atencion']['total_sobrepagadas'], 1)
        self.assertEqual(panel['con_saldo'], 0)
        self.assertEqual(services.panel_inicio(None, timezone.localdate())['con_saldo'], 1)

    def test_home_carga_con_cada_anio(self):
        usuario = get_user_model().objects.create_user(username='panel', password='clave-segura-123')
        self.client.force_login(usuario)
        for anio in ('', '2025', 'todos'):
            with self.subTest(anio=anio):
                respuesta = self.client.get(reverse('home'), {'anio': anio})
                self.assertEqual(respuesta.status_code, 200)
