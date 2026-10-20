from decimal import Decimal
from io import BytesIO

import openpyxl
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from escuela.models import Distrito, Encargado, Escuela
from . import services
from .models import Abono, Asignacion, Bono, Observacion, Recibo

COLUMNAS_RECIBOS = [
    'codigo_entidad', 'id_bono', 'monto_asignado', 'monto', 'no_requerimiento',
    'estado_trans', 'id_planilla_parcial', 'monto',
]


def archivo_excel(filas, nombre='archivo.xlsx'):
    """Arma un .xlsx en memoria (la primera fila son los encabezados)."""
    libro = openpyxl.Workbook()
    for fila in filas:
        libro.active.append(fila)
    contenido = BytesIO()
    libro.save(contenido)
    return SimpleUploadedFile(nombre, contenido.getvalue())


class LiquidacionBase(TestCase):
    def setUp(self):
        self.distrito = Distrito.objects.create(nombre='Distrito Centro')
        self.escuela = Escuela.objects.create(
            codigo='10001', nombre='Centro Escolar Uno', nombre_corto='CE Uno', distrito=self.distrito,
        )
        self.otra_escuela = Escuela.objects.create(
            codigo='10002', nombre='Centro Escolar Dos', nombre_corto='CE Dos', distrito=self.distrito,
        )
        Encargado.objects.create(nombre='Juan', apellido='Pérez', email='juan@clases.edu.sv', escuela=self.escuela)
        self.bono = Bono.objects.create(nombre='BONO ESCOLAR 2025', descripcion='', anio=2025, id_sistema=501)
        self.bono_2026 = Bono.objects.create(nombre='BONO ESCOLAR 2026', descripcion='Útiles', anio=2026, id_sistema=601)
        self.asignacion = Asignacion.objects.create(escuela=self.escuela, bono=self.bono, valor=Decimal('1000.00'))


# ===================== Services =====================

class EstadoLiquidacionTests(LiquidacionBase):
    def test_estado_segun_observaciones(self):
        recibo = Recibo.objects.create(asignacion=self.asignacion, monto=Decimal('600.00'))
        self.assertEqual(services.estado_liquidacion([recibo]), 'pendiente_revision')

        observacion = Observacion.objects.create(recibo=recibo, descripcion='Falta firma')
        self.assertEqual(services.estado_liquidacion([recibo]), 'liquidado_con_observaciones')

        services.alternar_observacion(observacion)
        self.assertEqual(services.estado_liquidacion([recibo]), 'liquidado')
        self.assertIsNotNone(observacion.fecha_resolucion)

    def test_estado_de_varios_recibos(self):
        uno = Recibo.objects.create(asignacion=self.asignacion, monto=Decimal('500.00'))
        dos = Recibo.objects.create(asignacion=self.asignacion, monto=Decimal('500.00'))
        Observacion.objects.create(recibo=uno, descripcion='Ok', resuelta=True)
        Observacion.objects.create(recibo=dos, descripcion='Pendiente')

        self.assertEqual(services.estado_liquidacion([uno, dos]), 'liquidado_con_observaciones')


class AsignacionServicesTests(LiquidacionBase):
    def setUp(self):
        super().setUp()
        self.recibo = Recibo.objects.create(asignacion=self.asignacion, monto=Decimal('600.00'))
        Abono.objects.create(recibo=self.recibo, monto=Decimal('400.00'), requerimiento='R1', estado=1, id_planilla_parcial=1)
        Abono.objects.create(recibo=self.recibo, monto=Decimal('100.00'), requerimiento='R2', estado=1, id_planilla_parcial=2)
        self.otra = Asignacion.objects.create(escuela=self.otra_escuela, bono=self.bono_2026, valor=Decimal('50.00'))

    def test_filtrar_asignaciones_calcula_total_y_diferencia(self):
        asignacion = services.filtrar_asignaciones({'escuela': self.escuela}).get()
        self.assertEqual(asignacion.total_recibido, Decimal('600.00'))
        self.assertEqual(asignacion.diferencia, Decimal('400.00'))

    def test_filtrar_asignaciones_por_anio_y_estado(self):
        self.assertEqual(list(services.filtrar_asignaciones({'anio': 2026})), [self.otra])

        Observacion.objects.create(recibo=self.recibo, descripcion='Falta firma')
        con_observaciones = services.filtrar_asignaciones({'estado': 'liquidado_con_observaciones'})
        self.assertEqual(con_observaciones, [self.asignacion])
        self.assertEqual(services.filtrar_asignaciones({'estado': 'liquidado'}), [])

    def test_gestion_asignacion(self):
        segundo = Recibo.objects.create(asignacion=self.asignacion, monto=Decimal('300.00'))

        gestion = services.gestion_asignacion(self.asignacion, str(segundo.pk))

        self.assertEqual(gestion['total_recibido'], Decimal('900.00'))
        self.assertEqual(gestion['diferencia'], Decimal('100.00'))
        self.assertEqual(gestion['recibo_actual'], segundo)
        self.assertEqual([r.posicion for r in gestion['recibos']], [1, 2])
        primero = gestion['recibos'][0]
        self.assertEqual(primero.total_abonado, Decimal('500.00'))
        self.assertEqual(primero.diferencia, Decimal('100.00'))

    def test_gestion_asignacion_sin_recibo_elegido_muestra_el_primero(self):
        self.assertEqual(services.gestion_asignacion(self.asignacion)['recibo_actual'], self.recibo)
        self.assertIsNone(services.gestion_asignacion(self.otra)['recibo_actual'])

    def test_reporte_asignacion(self):
        reporte = services.reporte_asignacion(self.asignacion)
        self.assertEqual(reporte['total_recibido'], Decimal('600.00'))
        self.assertEqual(reporte['estado_etiqueta'], 'Pendiente de revisión')
        self.assertEqual(reporte['nombre_reporte'], '10001_bono-escolar-2025')

    def test_resumen_abonos(self):
        resumen = services.resumen_abonos(self.recibo)
        self.assertEqual(resumen['total_abonado'], Decimal('500.00'))
        self.assertEqual(resumen['diferencia'], Decimal('100.00'))


class BonoServicesTests(LiquidacionBase):
    def test_filtrar_bonos(self):
        # En SQLite icontains solo ignora mayúsculas en ASCII ("útiles" no encuentra "Útiles").
        self.assertEqual(list(services.filtrar_bonos('TILES')), [self.bono_2026])
        self.assertEqual(list(services.filtrar_bonos('501')), [self.bono])
        self.assertEqual(list(services.filtrar_bonos(anio='2025')), [self.bono])
        self.assertEqual(services.filtrar_bonos().count(), 2)
        self.assertEqual(list(services.anios_bonos()), [2026, 2025])


class CargaExcelServicesTests(LiquidacionBase):
    def test_previsualizar_bonos(self):
        archivo = archivo_excel([
            ['id_bono', 'nombre_bono'],
            [501, 'BONO ESCOLAR 2025'],       # ya existe
            [701, 'BONO NUEVO 01/02/2027'],
            [701, 'Repetido, se ignora'],
            [None, 'Sin id, se ignora'],
        ])

        resultado = services.previsualizar_bonos(archivo)

        self.assertEqual(resultado['bonos'], [
            {'id_bono': 501, 'nombre_bono': 'BONO ESCOLAR 2025', 'anio': 2025, 'ya_existe': True},
            {'id_bono': 701, 'nombre_bono': 'BONO NUEVO 01/02/2027', 'anio': 2027, 'ya_existe': False},
        ])

    def test_previsualizar_bonos_errores(self):
        self.assertIn('error', services.previsualizar_bonos(None))
        self.assertIn('error', services.previsualizar_bonos(SimpleUploadedFile('datos.csv', b'a,b')))
        self.assertIn('error', services.previsualizar_bonos(SimpleUploadedFile('roto.xlsx', b'no es excel')))
        self.assertIn('error', services.previsualizar_bonos(archivo_excel([['otra', 'columna']])))

    def test_importar_bonos(self):
        creados, omitidos = services.importar_bonos([
            ('701.0', ' BONO NUEVO 2027 '),
            ('501', 'Otro nombre 2025'),       # id ya existe
            ('702', 'Sin año'),                # se ignora
            (None, 'BONO 2028'),               # se ignora
        ])

        self.assertEqual((creados, omitidos), (1, 1))
        bono = Bono.objects.get(id_sistema=701)
        self.assertEqual((bono.nombre, bono.anio), ('BONO NUEVO 2027', 2027))

    def test_procesar_reporte_recibos(self):
        archivo = archivo_excel([
            COLUMNAS_RECIBOS,
            # Recibo nuevo para la asignación existente, con dos abonos
            ['10001', 501, 1000, 600, 'REQ-1', 1, 11, 400],
            ['10001', 501, 1000, 600, 'REQ-2', 1, 12, 200],
            # Abono repetido (misma planilla parcial)
            ['10001', 501, 1000, 600, 'REQ-2', 1, 12, 200],
            # Asignación nueva para la otra escuela
            [10002.0, 601, 750, 750, 'REQ-3', 1, 13, 750],
            ['99999', 501, 1, 1, 'REQ-4', 1, 14, 1],     # escuela desconocida
            ['10001', 999, 1, 1, 'REQ-5', 1, 15, 1],     # bono desconocido
            ['10001', 501, 1, None, 'REQ-6', 1, 16, 1],  # falta el monto del recibo
        ])

        resultado = services.procesar_reporte_recibos(archivo)

        self.assertEqual(resultado['contadores'], {
            'asignaciones_creadas': 1,
            'asignaciones_existentes': 1,
            'recibos_creados': 2,
            'recibos_existentes': 0,
            'abonos_creados': 3,
            'abonos_existentes': 1,
            'filas_omitidas_escuela': 1,
            'filas_omitidas_bono': 1,
            'filas_omitidas_datos': 1,
        })
        nueva = Asignacion.objects.get(escuela=self.otra_escuela, bono=self.bono_2026)
        self.assertEqual(nueva.valor, Decimal('750.00'))
        recibo = Recibo.objects.get(asignacion=self.asignacion)
        self.assertEqual(recibo.abono_set.count(), 2)

    def test_procesar_reporte_recibos_dos_veces_no_duplica(self):
        filas = [COLUMNAS_RECIBOS, ['10001', 501, 1000, 600, 'REQ-1', 1, 11, 400]]
        services.procesar_reporte_recibos(archivo_excel(filas))

        resultado = services.procesar_reporte_recibos(archivo_excel(filas))

        self.assertEqual(resultado['contadores']['abonos_creados'], 0)
        self.assertEqual(resultado['contadores']['abonos_existentes'], 1)
        self.assertEqual(Abono.objects.count(), 1)

    def test_procesar_reporte_recibos_sin_columnas(self):
        resultado = services.procesar_reporte_recibos(archivo_excel([['codigo_entidad', 'monto']]))
        self.assertIn('error', resultado)


# ===================== Vistas =====================

class LiquidacionVistasTests(LiquidacionBase):
    def setUp(self):
        super().setUp()
        self.usuario = get_user_model().objects.create_superuser(username='admin', password='clave-segura-123')
        self.client.force_login(self.usuario)
        self.recibo = Recibo.objects.create(asignacion=self.asignacion, monto=Decimal('600.00'))

    def test_paginas_principales_cargan(self):
        urls = [
            reverse('home_asignaciones'),
            reverse('home_bonos'),
            reverse('home_carga_excel'),
            reverse('asignacion_gestionar', args=[self.asignacion.pk]),
            reverse('asignacion_detalle', args=[self.asignacion.pk]),
            reverse('recibo_abonos', args=[self.recibo.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_buscar_asignaciones(self):
        respuesta = self.client.get(reverse('buscar_asignaciones'))
        self.assertIsNone(respuesta.context['asignaciones'])

        respuesta = self.client.get(reverse('buscar_asignaciones'), {'escuela': self.escuela.pk})
        asignaciones = list(respuesta.context['asignaciones'])
        self.assertEqual(asignaciones, [self.asignacion])
        self.assertEqual(asignaciones[0].estado_liquidacion, 'pendiente_revision')

    def test_reportes_pdf(self):
        for url in (reverse('asignacion_imprimir', args=[self.asignacion.pk]), reverse('bono_imprimir')):
            with self.subTest(url=url):
                respuesta = self.client.get(url)
                self.assertEqual(respuesta['Content-Type'], 'application/pdf')
        respuesta = self.client.get(reverse('asignacion_imprimir', args=[self.asignacion.pk]))
        self.assertIn('10001_bono-escolar-2025.pdf', respuesta['Content-Disposition'])

    def test_crear_recibo_abono_y_observacion(self):
        respuesta = self.client.post(
            reverse('recibo_nuevo', args=[self.asignacion.pk]), {'recibo-monto': '250.00'},
        )
        recibo = Recibo.objects.get(monto=Decimal('250.00'))
        self.assertEqual(recibo.asignacion, self.asignacion)
        self.assertRedirects(
            respuesta, reverse('asignacion_gestionar', args=[self.asignacion.pk]) + f'?recibo={recibo.pk}',
        )

        self.client.post(reverse('abono_nuevo', args=[recibo.pk]), {
            'abono-monto': '100.00', 'abono-requerimiento': 'R1', 'abono-estado': '1', 'abono-id_planilla_parcial': '9',
        })
        self.assertEqual(recibo.abono_set.get().monto, Decimal('100.00'))

        self.client.post(reverse('observacion_nueva', args=[recibo.pk]), {'observacion-descripcion': 'Falta firma'})
        self.assertEqual(recibo.observacion_set.get().descripcion, 'Falta firma')

    def test_toggle_observacion(self):
        observacion = Observacion.objects.create(recibo=self.recibo, descripcion='Falta firma')

        respuesta = self.client.post(reverse('observacion_toggle', args=[observacion.pk]) + '?origen=detalle')

        observacion.refresh_from_db()
        self.assertTrue(observacion.resuelta)
        self.assertTemplateUsed(respuesta, 'partials/asignacion/_detalle.html')

    def test_crear_asignacion_duplicada_muestra_error(self):
        respuesta = self.client.post(reverse('asignacion_nueva'), {
            'asignacion-escuela': self.escuela.pk, 'asignacion-bono': self.bono.pk, 'asignacion-valor': '10',
        })
        self.assertTemplateUsed(respuesta, 'partials/asignacion/_modal_form.html')
        self.assertEqual(Asignacion.objects.count(), 1)

    def test_carga_de_bonos_preview_y_confirmar(self):
        archivo = archivo_excel([['id_bono', 'nombre_bono'], [701, 'BONO NUEVO 2027']])
        respuesta = self.client.post(reverse('carga_bonos_preview'), {'archivo': archivo})
        self.assertEqual(respuesta.context['bonos'][0]['id_bono'], 701)

        respuesta = self.client.post(reverse('carga_bonos_confirmar'), {
            'id_bono_0': '701', 'nombre_bono_0': 'BONO NUEVO 2027', 'seleccion_0': 'on',
            # Sin marcar: no se crea
            'id_bono_1': '702', 'nombre_bono_1': 'BONO OTRO 2027',
        })
        self.assertEqual(respuesta.context['creados'], 1)
        self.assertTrue(Bono.objects.filter(id_sistema=701).exists())
        self.assertFalse(Bono.objects.filter(id_sistema=702).exists())

    def test_carga_de_recibos(self):
        archivo = archivo_excel([COLUMNAS_RECIBOS, ['10001', 501, 1000, 300, 'REQ-1', 1, 11, 300]])
        respuesta = self.client.post(reverse('carga_recibos_procesar'), {'archivo': archivo})
        self.assertEqual(respuesta.context['contadores']['recibos_creados'], 1)

        respuesta = self.client.post(reverse('carga_recibos_procesar'), {})
        self.assertIn('error', respuesta.context)
