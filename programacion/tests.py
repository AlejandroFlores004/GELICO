from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from escuela.models import Distrito, Escuela
from .agenda import armar_calendario, tonos_por_auxiliar
from .forms import ProgramacionForm
from .models import Auxiliar, Ausencia, Convocatoria, Horario, Programacion


class ProgramacionCalendarioAuxiliarConvocatoriaTests(TestCase):
	def test_calendario_conserva_horario_y_marca_periodo_de_convocatoria(self):
		auxiliar = Auxiliar.objects.create(
			nombre='Ana',
			apellido='Pérez',
			email='ana.calendario@example.com',
			institucion='Institución de prueba',
		)
		convocatoria = Convocatoria.objects.create(
			nombre='Convocatoria de mayo',
			descripcion='',
			fecha_inicio='2026-05-10',
			fecha_fin='2026-05-20',
		)
		Horario.objects.create(
			auxiliar=auxiliar,
			fecha='2026-05-12',
			hora_inicio='09:00',
			hora_fin='12:00',
		)

		respuesta = self.client.get(reverse('programacion_auxiliar_horario'), {
			'auxiliar': auxiliar.pk,
			'convocatoria': convocatoria.pk,
			'mes': '2026-05',
		})

		self.assertEqual(respuesta.status_code, 200)
		self.assertEqual(respuesta.context['auxiliar'], auxiliar)
		self.assertEqual(respuesta.context['convocatoria'], convocatoria)
		dias = [dia for semana in respuesta.context['calendario_horarios'] for dia in semana]
		dia_con_horario = next(dia for dia in dias if dia['fecha'].isoformat() == '2026-05-12')
		self.assertTrue(dia_con_horario['en_periodo_convocatoria'])
		self.assertEqual(len(dia_con_horario['horarios']), 1)


class ProgramacionHorarioValidationTests(TestCase):
	def setUp(self):
		distrito = Distrito.objects.create(nombre='Distrito de prueba')
		self.escuela = Escuela.objects.create(
			codigo='HOR-1',
			nombre='Escuela de prueba',
			nombre_corto='Escuela prueba',
			distrito=distrito,
		)
		self.convocatoria = Convocatoria.objects.create(
			nombre='Convocatoria de prueba',
			descripcion='',
			fecha_inicio='2026-05-01',
			fecha_fin='2026-05-31',
		)
		self.auxiliar = Auxiliar.objects.create(
			nombre='Ana',
			apellido='Pérez',
			email='ana.validacion@example.com',
			institucion='Institución de prueba',
		)
		Horario.objects.create(
			auxiliar=self.auxiliar,
			fecha='2026-05-12',
			hora_inicio='09:00',
			hora_fin='12:00',
		)

	def _formulario(self, hora):
		return ProgramacionForm(data={
			'convocatoria': self.convocatoria.pk,
			'auxiliar': self.auxiliar.pk,
			'fecha_programada': '2026-05-12',
			'hora_programada': hora,
			'escuela': self.escuela.pk,
			'estado': 'pendiente',
		})

	def test_rechaza_hora_fuera_del_horario_del_auxiliar(self):
		form = self._formulario('12:00')

		self.assertFalse(form.is_valid())
		self.assertTrue(form.non_field_errors())

	def test_acepta_hora_dentro_del_horario_del_auxiliar(self):
		form = self._formulario('11:30')

		self.assertTrue(form.is_valid(), form.errors)

	def test_permite_editar_sin_cambiar_hora_existente(self):
		programacion = Programacion.objects.create(
			convocatoria=self.convocatoria,
			auxiliar=self.auxiliar,
			fecha_programada='2026-05-12',
			hora_programada='13:00',
			escuela=self.escuela,
		)
		form = ProgramacionForm(
			data=self._formulario('13:00').data,
			instance=programacion,
		)

		self.assertTrue(form.is_valid(), form.errors)

	def test_rechaza_auxiliar_asignado_a_la_misma_fecha_y_hora(self):
		Programacion.objects.create(
			convocatoria=self.convocatoria,
			auxiliar=self.auxiliar,
			fecha_programada='2026-05-12',
			hora_programada='10:00',
			escuela=self.escuela,
		)
		form = self._formulario('10:00')

		self.assertFalse(form.is_valid())
		self.assertIn('Este auxiliar ya tiene otra programación asignada en esa fecha y hora.', form.non_field_errors())

	def test_rechaza_escuela_asignada_a_la_misma_fecha_y_hora(self):
		otro_auxiliar = Auxiliar.objects.create(
			nombre='Luis',
			apellido='Gómez',
			email='luis.validacion@example.com',
			institucion='Institución de prueba',
		)
		Horario.objects.create(
			auxiliar=otro_auxiliar,
			fecha='2026-05-12',
			hora_inicio='09:00',
			hora_fin='12:00',
		)
		Programacion.objects.create(
			convocatoria=self.convocatoria,
			auxiliar=otro_auxiliar,
			fecha_programada='2026-05-12',
			hora_programada='10:00',
			escuela=self.escuela,
		)
		form = self._formulario('10:00')

		self.assertFalse(form.is_valid())
		self.assertIn('Esta escuela ya tiene otra programación asignada en esa fecha y hora.', form.non_field_errors())


class AgendaBase(TestCase):
	def setUp(self):
		# Un día de la próxima semana, para que ninguna hora haya "pasado".
		self.dia = timezone.localdate() + timedelta(days=7)
		distrito = Distrito.objects.create(nombre='Distrito agenda')
		self.escuela = Escuela.objects.create(
			codigo='AGE-1', nombre='Escuela agenda', nombre_corto='Agenda', distrito=distrito,
		)
		self.convocatoria = Convocatoria.objects.create(
			nombre='Convocatoria agenda', descripcion='',
			fecha_inicio=self.dia - timedelta(days=10), fecha_fin=self.dia + timedelta(days=10),
		)
		self.auxiliar = Auxiliar.objects.create(
			nombre='Luis', apellido='Gómez', email='luis.agenda@example.com', institucion='UES',
		)
		Horario.objects.create(auxiliar=self.auxiliar, fecha=self.dia, hora_inicio=time(9, 30), hora_fin=time(12))

	def _celda(self, calendario, hora):
		fila = next(fila for fila in calendario['filas'] if fila['hora'] == time(hora))
		return fila['celdas'][0]

	def _dia(self, convocatoria=None):
		auxiliares = [self.auxiliar]
		return armar_calendario('dia', self.dia, auxiliares, tonos_por_auxiliar(auxiliares), convocatoria)


class AgendaTests(AgendaBase):
	def test_horas_libres_respetan_el_horario(self):
		calendario = self._dia()
		self.assertEqual(self._celda(calendario, 9)['hora_libre'], time(9, 30))
		self.assertEqual(self._celda(calendario, 9)['auxiliar_libre'], self.auxiliar.pk)
		self.assertNotIn('hora_libre', self._celda(calendario, 12))
		self.assertFalse(self._celda(calendario, 12)['trabaja'])

	def test_una_programacion_ocupa_su_hora(self):
		programacion = Programacion.objects.create(
			convocatoria=self.convocatoria, auxiliar=self.auxiliar, escuela=self.escuela,
			fecha_programada=self.dia, hora_programada=time(10, 15),
		)
		celda = self._celda(self._dia(), 10)
		self.assertEqual(celda['programaciones'], [programacion])
		self.assertNotIn('hora_libre', celda)

	def test_ausencia_bloquea_el_dia(self):
		Ausencia.objects.create(auxiliar=self.auxiliar, fecha=self.dia, motivo='Enfermedad')
		calendario = self._dia()
		self.assertFalse(calendario['hay_horarios'])
		self.assertNotIn('hora_libre', self._celda(calendario, 9))

	def test_fuera_del_periodo_de_la_convocatoria_no_se_programa(self):
		otra = Convocatoria.objects.create(
			nombre='Pasada', descripcion='', fecha_inicio=self.dia - timedelta(days=30), fecha_fin=self.dia - timedelta(days=20),
		)
		celda = self._celda(self._dia(otra), 9)
		self.assertTrue(celda['fuera_periodo'])
		self.assertNotIn('hora_libre', celda)

	def test_vista_de_mes_cuenta_disponibles(self):
		auxiliares = [self.auxiliar]
		calendario = armar_calendario('mes', self.dia, auxiliares, tonos_por_auxiliar(auxiliares))
		dia = next(d for semana in calendario['semanas'] for d in semana if d['fecha'] == self.dia)
		self.assertEqual(dia['disponibles'], 1)
		self.assertTrue(dia['puede_programar'])


class ProgramacionPaginaTests(AgendaBase):
	def setUp(self):
		super().setUp()
		get_user_model().objects.create_user('agenda', password='Clave-2026')
		self.client.login(username='agenda', password='Clave-2026')

	def test_secciones_y_modos_cargan(self):
		for parametros in ({'modo': 'mes'}, {'modo': 'semana'}, {'modo': 'dia'}, {'seccion': 'programaciones'}, {'seccion': 'convocatorias'}):
			with self.subTest(**parametros):
				respuesta = self.client.get(reverse('home_programacion'), {'fecha': self.dia.isoformat(), **parametros})
				self.assertEqual(respuesta.status_code, 200)

	def test_rutas_anteriores_redirigen(self):
		self.assertRedirects(self.client.get(reverse('home_calendario')), reverse('home_programacion'))
		self.assertRedirects(
			self.client.get(reverse('home_convocatorias')), f"{reverse('home_programacion')}?seccion=convocatorias",
		)

	def test_espacio_libre_abre_el_formulario_prellenado(self):
		respuesta = self.client.get(reverse('programacion_nueva'), {
			'origen': 'calendario', 'fecha': self.dia.isoformat(), 'hora': '09:30', 'auxiliar': self.auxiliar.pk,
		})
		inicial = respuesta.context['form'].initial
		self.assertEqual(inicial['fecha_programada'], self.dia)
		self.assertEqual(inicial['hora_programada'], time(9, 30))
		self.assertEqual(inicial['auxiliar'], self.auxiliar.pk)
		# Solo una convocatoria cubre ese día: se propone sola.
		self.assertEqual(inicial['convocatoria'], self.convocatoria.pk)

	def test_guardar_desde_el_calendario_avisa_para_refrescarlo(self):
		url = f"{reverse('programacion_nueva')}?origen=calendario"
		respuesta = self.client.post(url, {
			'convocatoria': self.convocatoria.pk, 'auxiliar': self.auxiliar.pk, 'escuela': self.escuela.pk,
			'fecha_programada': self.dia.isoformat(), 'hora_programada': '10:00', 'estado': 'pendiente',
		})
		self.assertEqual(respuesta['HX-Trigger'], 'agenda-actualizada')
		self.assertNotContains(respuesta, 'listado-programaciones')
		self.assertTrue(Programacion.objects.filter(hora_programada='10:00').exists())

	def test_cambio_rapido_de_estado(self):
		programacion = Programacion.objects.create(
			convocatoria=self.convocatoria, auxiliar=self.auxiliar, escuela=self.escuela,
			fecha_programada=self.dia, hora_programada=time(10),
		)
		respuesta = self.client.post(reverse('programacion_estado', args=[programacion.pk]), {'estado': 'completado'})
		self.assertEqual(respuesta['HX-Trigger'], 'agenda-actualizada')
		programacion.refresh_from_db()
		self.assertEqual(programacion.estado, 'completado')
