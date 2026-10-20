import json
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from easyaudit.models import CRUDEvent, LoginEvent

from escuela.models import CDE, Distrito, Escuela
from liquidacion.models import Asignacion, Bono, Observacion, Recibo
from liquidacion.services import estado_liquidacion
from programacion.models import Convocatoria, Programacion
from . import notificaciones as notificaciones_service
from . import services
from .middleware import _leer_disparadores
from .notificaciones import notificaciones_de


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


class AvisosTests(TestCase):
    """Mensajes de guardado/eliminado: en htmx viajan en HX-Trigger (evento "aviso")."""

    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser(username='admin', password='clave-segura-123')
        self.client.force_login(self.usuario)
        self.distrito = Distrito.objects.create(nombre='Distrito avisos')
        self.escuela = Escuela.objects.create(codigo='AVI-1', nombre='Escuela avisos', nombre_corto='Avisos', distrito=self.distrito)

    def _disparadores(self, respuesta):
        return json.loads(respuesta['HX-Trigger'])

    def test_guardar_por_htmx_manda_el_aviso_en_el_header(self):
        respuesta = self.client.post(
            reverse('escuela_toggle', args=[self.escuela.pk]), HTTP_HX_REQUEST='true',
        )

        disparadores = self._disparadores(respuesta)
        self.assertEqual(disparadores['aviso'], {'avisos': [{'nivel': 'success', 'texto': 'Se desactivó la escuela Avisos.'}]})
        self.assertIn('notificaciones-actualizar', disparadores)
        # Ya se entregó: no vuelve a salir en la siguiente página.
        self.assertEqual(list(self.client.get(reverse('home')).context['messages']), [])

    def test_conserva_los_eventos_que_ya_mandaba_la_vista(self):
        convocatoria = Convocatoria.objects.create(
            nombre='Convocatoria avisos', descripcion='', fecha_inicio=date(2026, 5, 1), fecha_fin=date(2026, 5, 31),
        )
        respuesta = self.client.post(
            reverse('convocatoria_eliminar', args=[convocatoria.pk]), HTTP_HX_REQUEST='true',
        )

        disparadores = self._disparadores(respuesta)
        self.assertIn('agenda-actualizada', disparadores)
        self.assertEqual(disparadores['aviso']['avisos'][0]['texto'], 'Se eliminó la convocatoria Convocatoria avisos.')

    def test_si_la_respuesta_recarga_la_pagina_el_aviso_sale_en_la_pagina_nueva(self):
        respuesta = self.client.post(reverse('escuela_nueva'), {
            'escuela-codigo': 'AVI-2', 'escuela-nombre': 'Escuela nueva', 'escuela-nombre_corto': 'Nueva',
            'escuela-distrito': self.distrito.pk,
        }, HTTP_HX_REQUEST='true')

        self.assertIn('HX-Redirect', respuesta)
        self.assertNotIn('HX-Trigger', respuesta)
        pagina = self.client.get(respuesta['HX-Redirect'])
        self.assertContains(pagina, "mostrarAviso('success'")
        self.assertContains(pagina, 'Se registró la escuela Nueva')

    def test_sin_mensajes_no_toca_el_header(self):
        respuesta = self.client.get(reverse('escuela_buscar'), {'estado': '1'}, HTTP_HX_REQUEST='true')
        self.assertNotIn('HX-Trigger', respuesta)

    def test_formulario_con_errores_no_avisa(self):
        respuesta = self.client.post(reverse('escuela_nueva'), {'escuela-codigo': ''}, HTTP_HX_REQUEST='true')
        self.assertNotIn('HX-Trigger', respuesta)

    def test_leer_disparadores(self):
        self.assertEqual(_leer_disparadores(None), {})
        self.assertEqual(_leer_disparadores('uno, dos'), {'uno': None, 'dos': None})
        self.assertEqual(_leer_disparadores('{"uno": {"a": 1}}'), {'uno': {'a': 1}})


class NotificacionesTests(TestCase):
    def setUp(self):
        self.hoy = timezone.localdate()
        self.distrito = Distrito.objects.create(nombre='Distrito notificaciones')

    def _escuela(self, codigo, **extra):
        return Escuela.objects.create(
            codigo=codigo, nombre=f'Escuela {codigo}', nombre_corto=f'E{codigo}', distrito=self.distrito, **extra,
        )

    def _cde(self, escuela, inicio_dias, fin_dias):
        return CDE.objects.create(
            escuela=escuela, FechaInicio=self.hoy + timedelta(days=inicio_dias), FechaFin=self.hoy + timedelta(days=fin_dias),
        )

    def _titulos(self, notificaciones):
        return [notificacion.titulo for notificacion in notificaciones]

    def test_cde_por_vencer_y_vencido(self):
        por_vencer = self._escuela('N1')
        self._cde(por_vencer, -300, 10)
        vencida = self._escuela('N2')
        self._cde(vencida, -800, -400)
        self._cde(vencida, -399, -5)  # el último periodo es el que cuenta
        al_dia = self._escuela('N3')
        self._cde(al_dia, -10, 300)

        notificaciones = notificaciones_service.cde_por_vencer_y_vencidos(self.hoy)

        self.assertEqual(self._titulos(notificaciones), [
            'El CDE de EN1 está por vencer',
            'El CDE de EN2 está vencido',
        ])
        self.assertEqual(notificaciones[0].detalle.split(',')[0], 'Vence en 10 días')
        self.assertIn('hace 5 días', notificaciones[1].detalle)
        self.assertEqual(notificaciones[1].url, reverse('escuela_gestionar', args=[vencida.pk]))

    def test_cde_renovado_o_escuela_inactiva_no_avisan(self):
        renovada = self._escuela('N1')
        self._cde(renovada, -300, 10)
        self._cde(renovada, 11, 400)   # ya tiene el siguiente periodo
        inactiva = self._escuela('N2', estado=False)
        self._cde(inactiva, -800, -5)

        self.assertEqual(notificaciones_service.cde_por_vencer_y_vencidos(self.hoy), [])

    def test_escuelas_sin_cde_y_sin_encargado_se_agrupan(self):
        self._escuela('N1')
        self._escuela('N2')
        self._escuela('N3', estado=False)

        self.assertEqual(self._titulos(notificaciones_service.escuelas_sin_cde(self.hoy)), [
            '2 escuelas activas no tienen CDE registrado',
        ])
        self.assertEqual(self._titulos(notificaciones_service.escuelas_sin_encargado(self.hoy)), [
            '2 escuelas activas no tienen encargado activo',
        ])

    def test_visitas_sin_resultado(self):
        escuela = self._escuela('N1')
        convocatoria = Convocatoria.objects.create(
            nombre='Ronda', descripcion='', fecha_inicio=self.hoy - timedelta(days=60), fecha_fin=self.hoy,
        )

        def visita(dias, estado='pendiente', jornada='manana'):
            return Programacion.objects.create(
                convocatoria=convocatoria, escuela=escuela, jornada=jornada, estado=estado,
                fecha_programada=self.hoy - timedelta(days=dias),
            )

        visita(2)
        visita(2, jornada='tarde')
        visita(3, estado='completado')
        visita(45)
        visita(0)  # hoy todavía no cuenta

        notificaciones = notificaciones_service.visitas_sin_resultado(self.hoy)

        self.assertEqual(len(notificaciones), 2)
        self.assertTrue(notificaciones[0].titulo.startswith('2 visitas sin resultado del '))
        self.assertIn('modo=dia', notificaciones[0].url)
        self.assertEqual(notificaciones[1].titulo, '1 visita antigua sigue pendiente')

    def test_orden_y_permisos(self):
        escuela = self._escuela('N1')
        self._cde(escuela, -800, -5)      # urgente (vencido)
        otra = self._escuela('N2')
        self._cde(otra, -300, 10)         # por atender

        superusuario = get_user_model().objects.create_superuser(username='root', password='x')
        niveles = [notificacion.nivel for notificacion in notificaciones_de(superusuario, self.hoy)]
        self.assertEqual(niveles, sorted(niveles, key=['error', 'warning', 'info'].index))
        self.assertEqual(niveles[0], 'error')

        sin_permisos = get_user_model().objects.create_user(username='nadie', password='x')
        self.assertEqual(notificaciones_de(sin_permisos, self.hoy), [])

        solo_escuelas = get_user_model().objects.create_user(username='escuelas', password='x')
        solo_escuelas.user_permissions.add(Permission.objects.get(codename='view_escuela'))
        categorias = {n.categoria for n in notificaciones_de(solo_escuelas, self.hoy)}
        self.assertEqual(categorias, {'Escuelas'})

    def test_campana_y_pagina(self):
        self._cde(self._escuela('N1'), -800, -5)
        usuario = get_user_model().objects.create_superuser(username='root', password='x')
        self.client.force_login(usuario)

        campana = self.client.get(reverse('notificaciones_campana'), HTTP_HX_REQUEST='true')
        self.assertEqual(campana.context['urgentes'], 1)
        self.assertContains(campana, 'El CDE de EN1 está vencido')

        pagina = self.client.get(reverse('home_notificaciones'))
        self.assertEqual(pagina.status_code, 200)
        self.assertEqual(pagina.context['por_nivel']['error'], 1)
        self.assertIn('CDE', dict(pagina.context['grupos']))

    def test_sin_pendientes_muestra_todo_al_dia(self):
        usuario = get_user_model().objects.create_user(username='nadie', password='x')
        self.client.force_login(usuario)
        self.assertContains(self.client.get(reverse('notificaciones_campana')), 'Todo al día')
        self.assertContains(self.client.get(reverse('home_notificaciones')), 'Todo al día')
