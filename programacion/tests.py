from django.test import TestCase
from django.urls import reverse

from escuela.models import Distrito, Escuela
from .forms import ProgramacionForm
from .models import Auxiliar, Convocatoria, Horario, Programacion


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