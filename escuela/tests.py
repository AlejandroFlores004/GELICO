from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import services
from .forms import EncargadoForm, TelefonoFormSet
from .models import CDE, Distrito, Encargado, Escuela, Telefono


def datos_encargado(escuela, email='nuevo@clases.edu.sv', numero='7123-4567'):
    """POST del modal de encargado: el form (prefijo 'encargado') y un teléfono."""
    return {
        'encargado-nombre': 'María',
        'encargado-apellido': 'López',
        'encargado-email': email,
        'encargado-escuela': escuela.pk,
        'telefonos-TOTAL_FORMS': '1',
        'telefonos-INITIAL_FORMS': '0',
        'telefonos-MIN_NUM_FORMS': '0',
        'telefonos-MAX_NUM_FORMS': '1000',
        'telefonos-0-numero': numero,
        'telefonos-0-etiqueta': 'personal',
    }


class EscuelaBase(TestCase):
    def setUp(self):
        self.hoy = timezone.localdate()
        self.distrito = Distrito.objects.create(nombre='Distrito Centro')
        self.otro_distrito = Distrito.objects.create(nombre='Distrito Norte')
        self.escuela = Escuela.objects.create(
            codigo='10001', nombre='Centro Escolar Uno', nombre_corto='CE Uno', distrito=self.distrito,
        )
        self.otra_escuela = Escuela.objects.create(
            codigo='10002', nombre='Centro Escolar Dos', nombre_corto='CE Dos', distrito=self.otro_distrito,
        )
        self.activo = Encargado.objects.create(
            nombre='Juan', apellido='Pérez', email='juan@clases.edu.sv', escuela=self.escuela,
        )
        Telefono.objects.create(encargado=self.activo, numero='2222-3333')

    def crear_cde(self, escuela, inicio_dias, fin_dias):
        """CDE con fechas relativas a hoy (en días)."""
        return CDE.objects.create(
            escuela=escuela,
            FechaInicio=self.hoy + timedelta(days=inicio_dias),
            FechaFin=self.hoy + timedelta(days=fin_dias),
        )


# ===================== Services =====================

class EncargadoServicesTests(EscuelaBase):
    def test_filtrar_encargados_por_texto_y_estado(self):
        Encargado.objects.create(
            nombre='Ana', apellido='Gómez', email='ana@clases.edu.sv', escuela=self.otra_escuela, estado=False,
        )

        self.assertEqual(list(services.filtrar_encargados({'texto': 'juan'})), [self.activo])
        self.assertEqual(
            [e.nombre for e in services.filtrar_encargados({'estado': '0'})], ['Ana'],
        )
        self.assertEqual(
            list(services.filtrar_encargados({'distrito': self.distrito})), [self.activo],
        )
        self.assertEqual(services.filtrar_encargados({}).count(), 2)

    def test_guardar_encargado_nuevo_desactiva_al_anterior(self):
        form = EncargadoForm(datos_encargado(self.escuela), prefix='encargado')
        formset = TelefonoFormSet(datos_encargado(self.escuela), prefix='telefonos')
        self.assertTrue(form.is_valid() and formset.is_valid(), (form.errors, formset.errors))

        nuevo = services.guardar_encargado(form, formset)

        self.activo.refresh_from_db()
        self.assertTrue(nuevo.estado)
        self.assertFalse(self.activo.estado)
        self.assertEqual(list(nuevo.telefonos.values_list('numero', flat=True)), ['7123-4567'])

    def test_guardar_encargado_existente_no_toca_a_los_demas(self):
        otro = Encargado.objects.create(
            nombre='Luis', apellido='Ramos', email='luis@clases.edu.sv', escuela=self.escuela,
        )
        datos = datos_encargado(self.escuela, email='luis@clases.edu.sv')
        form = EncargadoForm(datos, instance=otro, prefix='encargado')
        formset = TelefonoFormSet(datos, instance=otro, prefix='telefonos')
        self.assertTrue(form.is_valid() and formset.is_valid(), (form.errors, formset.errors))

        services.guardar_encargado(form, formset)

        self.activo.refresh_from_db()
        self.assertTrue(self.activo.estado)

    def test_cambiar_encargado(self):
        datos = datos_encargado(self.escuela)
        nuevo_instance = Encargado(escuela=self.escuela)
        form = EncargadoForm(datos, instance=nuevo_instance, prefix='encargado')
        formset = TelefonoFormSet(datos, instance=nuevo_instance, prefix='telefonos')
        self.assertTrue(form.is_valid() and formset.is_valid(), (form.errors, formset.errors))

        nuevo = services.cambiar_encargado(self.activo, form, formset)

        self.activo.refresh_from_db()
        self.assertFalse(self.activo.estado)
        self.assertTrue(nuevo.estado)
        self.assertEqual(nuevo.escuela, self.escuela)

    def test_alternar_estado_activa_y_deja_un_solo_activo(self):
        inactivo = Encargado.objects.create(
            nombre='Luis', apellido='Ramos', email='luis@clases.edu.sv', escuela=self.escuela, estado=False,
        )

        services.alternar_estado_encargado(inactivo)

        self.activo.refresh_from_db()
        self.assertTrue(inactivo.estado)
        self.assertFalse(self.activo.estado)

        services.alternar_estado_encargado(inactivo)
        self.assertFalse(inactivo.estado)

    def test_encargados_de_escuelas_con_y_sin_anteriores(self):
        Encargado.objects.create(
            nombre='Luis', apellido='Ramos', email='luis@clases.edu.sv', escuela=self.escuela, estado=False,
        )
        escuelas = Escuela.objects.filter(pk=self.escuela.pk)

        self.assertEqual(services.encargados_de_escuelas(escuelas).count(), 1)
        self.assertEqual(services.encargados_de_escuelas(escuelas, con_anteriores=True).count(), 2)


class CDEServicesTests(EscuelaBase):
    def test_anotar_vigencia(self):
        vencido = self.crear_cde(self.escuela, -400, -1)
        por_vencer = self.crear_cde(self.escuela, -300, services.DIAS_POR_VENCER)
        vigente = self.crear_cde(self.escuela, -10, services.DIAS_POR_VENCER + 1)
        proximo = self.crear_cde(self.escuela, 5, 300)

        vigencias = dict(services.anotar_vigencia(CDE.objects.all()).values_list('pk', 'vigencia'))

        self.assertEqual(vigencias, {
            vencido.pk: 'vencido',
            por_vencer.pk: 'por_vencer',
            vigente.pk: 'vigente',
            proximo.pk: 'proximo',
        })

    def test_leer_orden_cdes(self):
        self.assertEqual(services.leer_orden_cdes('-fin'), ('fin', True))
        self.assertEqual(services.leer_orden_cdes('escuela'), ('escuela', False))
        self.assertEqual(services.leer_orden_cdes('inventado'), (services.ORDEN_CDE_DEFECTO, False))
        self.assertEqual(services.leer_orden_cdes(None), (services.ORDEN_CDE_DEFECTO, False))

    def test_filtrar_cdes_por_vigencia_y_orden(self):
        vencido = self.crear_cde(self.escuela, -400, -1)
        vigente = self.crear_cde(self.otra_escuela, -10, 200)

        sin_vigencia, cdes = services.filtrar_cdes({'vigencia': 'vencido'})
        self.assertEqual(list(cdes), [vencido])
        # El primero ignora el filtro de vigencia: lo usa el resumen.
        self.assertEqual(sin_vigencia.count(), 2)

        _, por_fin_desc = services.filtrar_cdes({}, 'fin', descendente=True)
        self.assertEqual(list(por_fin_desc), [vigente, vencido])

    def test_resumen_cdes_cuenta_y_lista_escuelas_sin_cde(self):
        self.crear_cde(self.escuela, -10, 200)
        self.crear_cde(self.otra_escuela, -400, -1)

        sin_vigencia, _ = services.filtrar_cdes({})
        resumen = services.resumen_cdes({}, sin_vigencia)

        self.assertEqual(resumen['vigente'], 1)
        self.assertEqual(resumen['vencido'], 1)
        self.assertEqual(resumen['escuelas_sin_cde'], [self.otra_escuela])

    def test_con_dias_calcula_avance(self):
        cde = self.crear_cde(self.escuela, -50, 50)

        services.con_dias([cde])

        self.assertEqual(cde.dias_para_fin, 50)
        self.assertEqual(cde.avance, 50)


class EscuelaServicesTests(EscuelaBase):
    def test_filtrar_escuelas(self):
        self.otra_escuela.estado = False
        self.otra_escuela.save()

        self.assertEqual(list(services.filtrar_escuelas({'estado': '1'})), [self.escuela])
        self.assertEqual(list(services.filtrar_escuelas({'distrito': self.otro_distrito})), [self.otra_escuela])
        self.assertEqual(services.filtrar_escuelas({}).count(), 2)

    def test_ficha_escuela(self):
        anterior = Encargado.objects.create(
            nombre='Luis', apellido='Ramos', email='luis@clases.edu.sv', escuela=self.escuela, estado=False,
        )
        viejo = self.crear_cde(self.escuela, -800, -400)
        actual = self.crear_cde(self.escuela, -10, 200)

        ficha = services.ficha_escuela(self.escuela)

        self.assertEqual(ficha['encargado_activo'], self.activo)
        self.assertEqual(ficha['encargados_anteriores'], [anterior])
        self.assertEqual(ficha['cdes'], [actual, viejo])
        self.assertEqual(ficha['cde_actual'], actual)

    def test_con_encargado_y_cde(self):
        actual = self.crear_cde(self.escuela, -10, 200)
        self.crear_cde(self.escuela, -800, -400)

        escuela = services.con_encargado_y_cde(Escuela.objects.filter(pk=self.escuela.pk)).get()

        self.assertEqual(escuela.encargados_activos, [self.activo])
        self.assertEqual(escuela.cdes_activos, [actual])

    def test_alternar_estado_escuela(self):
        services.alternar_estado_escuela(self.escuela)
        self.escuela.refresh_from_db()
        self.assertFalse(self.escuela.estado)


# ===================== Vistas =====================

class EscuelaVistasTests(EscuelaBase):
    def setUp(self):
        super().setUp()
        self.usuario = get_user_model().objects.create_superuser(username='admin', password='clave-segura-123')
        self.client.force_login(self.usuario)

    def test_paginas_principales_cargan(self):
        for nombre in ('home_encargados', 'home_cde', 'home_escuelas'):
            with self.subTest(pagina=nombre):
                self.assertEqual(self.client.get(reverse(nombre)).status_code, 200)

    def test_listado_de_escuelas_vacio_sin_filtros(self):
        respuesta = self.client.get(reverse('escuela_buscar'))
        self.assertIsNone(respuesta.context['escuelas'])

        respuesta = self.client.get(reverse('escuela_buscar'), {'estado': '1'})
        self.assertEqual(len(respuesta.context['escuelas']), 2)

    def test_gestionar_escuela(self):
        self.crear_cde(self.escuela, -10, 200)
        respuesta = self.client.get(reverse('escuela_gestionar', args=[self.escuela.pk]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context['encargado_activo'], self.activo)
        self.assertIsNotNone(respuesta.context['cde_actual'])

    def test_reportes_pdf(self):
        self.crear_cde(self.escuela, -10, 200)
        urls = [
            reverse('encargado_imprimir'),
            reverse('cde_imprimir'),
            reverse('escuela_imprimir'),
            reverse('escuela_imprimir_encargados') + '?anteriores=1',
            reverse('escuela_imprimir_cde'),
            reverse('escuela_imprimir_general'),
            # Antes fallaba con NameError: la ficha usaba "cdes" sin definirlo.
            reverse('escuela_imprimir_ficha', args=[self.escuela.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                respuesta = self.client.get(url)
                self.assertEqual(respuesta.status_code, 200)
                self.assertEqual(respuesta['Content-Type'], 'application/pdf')

    def test_crear_encargado_desde_el_listado(self):
        respuesta = self.client.post(reverse('encargado_nuevo'), datos_encargado(self.escuela))

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, 'partials/encargado/_encargado_form_success.html')
        self.activo.refresh_from_db()
        self.assertFalse(self.activo.estado)
        self.assertTrue(Encargado.objects.get(email='nuevo@clases.edu.sv').estado)

    def test_crear_encargado_invalido_vuelve_a_mostrar_el_modal(self):
        datos = datos_encargado(self.escuela, numero='1234')
        respuesta = self.client.post(reverse('encargado_nuevo'), datos)

        self.assertTemplateUsed(respuesta, 'partials/encargado/_encargado_form_modal.html')
        self.assertFalse(Encargado.objects.filter(email='nuevo@clases.edu.sv').exists())

    def test_crear_encargado_desde_gestionar_recarga_la_pagina(self):
        url_gestion = 'http://testserver' + reverse('escuela_gestionar', args=[self.escuela.pk])
        respuesta = self.client.post(
            reverse('encargado_nuevo'),
            # La escuela va bloqueada: aunque se mande otra, se usa la de la página.
            datos_encargado(self.otra_escuela),
            HTTP_HX_REQUEST='true', HTTP_HX_CURRENT_URL=url_gestion,
        )

        self.assertEqual(respuesta['HX-Redirect'], reverse('escuela_gestionar', args=[self.escuela.pk]))
        self.assertEqual(Encargado.objects.get(email='nuevo@clases.edu.sv').escuela, self.escuela)

    def test_toggle_encargado_y_escuela(self):
        self.client.post(reverse('encargado_toggle', args=[self.activo.pk]))
        self.activo.refresh_from_db()
        self.assertFalse(self.activo.estado)

        self.client.post(reverse('escuela_toggle', args=[self.escuela.pk]))
        self.escuela.refresh_from_db()
        self.assertFalse(self.escuela.estado)

    def test_crear_y_eliminar_cde(self):
        respuesta = self.client.post(reverse('cde_nuevo'), {
            'FechaInicio': self.hoy.isoformat(),
            'FechaFin': (self.hoy + timedelta(days=365)).isoformat(),
            'escuela': self.escuela.pk,
        })
        self.assertTemplateUsed(respuesta, 'partials/cde/modal_form_success.html')
        cde = CDE.objects.get(escuela=self.escuela)

        self.client.post(reverse('cde_eliminar', args=[cde.pk]))
        self.assertFalse(CDE.objects.exists())

    def test_sin_permiso_no_entra(self):
        self.client.force_login(get_user_model().objects.create_user(username='sin_permisos', password='x'))
        self.assertEqual(self.client.get(reverse('home_escuelas')).status_code, 403)
