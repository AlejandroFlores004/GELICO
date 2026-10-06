from datetime import date, time

from django.test import TestCase
from django.urls import reverse

from escuela.models import Distrito, Escuela
from .models import Auxiliar, Convocatoria, Programacion


class ProgramacionTests(TestCase):
	def setUp(self):
		distrito = Distrito.objects.create(nombre="Distrito de prueba")
		self.escuela = Escuela.objects.create(
			codigo="CAL-1",
			nombre="Escuela del calendario",
			nombre_corto="Escuela calendario",
			distrito=distrito,
		)
		self.convocatoria = Convocatoria.objects.create(
			nombre="Convocatoria de prueba",
			descripcion="",
			fecha_inicio=date(2026, 5, 1),
			fecha_fin=date(2026, 5, 31),
		)
		self.auxiliar = Auxiliar.objects.create(
			nombre="Ana",
			apellido="Pérez",
			email="ana.calendario@example.com",
			institucion="Institución de prueba",
		)
		self.programacion = Programacion.objects.create(
			convocatoria=self.convocatoria,
			auxiliar=self.auxiliar,
			fecha_programada=date(2026, 5, 12),
			hora_programada=time(9, 30),
			escuela=self.escuela,
		)

	def test_lista_programaciones_y_relaciones(self):
		respuesta = self.client.get(reverse('home_programacion'))

		self.assertEqual(respuesta.status_code, 200)
		self.assertContains(respuesta, "Convocatoria de prueba")
		self.assertContains(respuesta, "Escuela calendario")
		self.assertContains(respuesta, "09:30")
		self.assertContains(respuesta, "Ana Pérez")

	def test_crea_programacion_desde_el_formulario(self):
		respuesta = self.client.post(reverse('programacion_nueva'), {
			'convocatoria': self.convocatoria.pk,
			'auxiliar': self.auxiliar.pk,
			'fecha_programada': '2026-05-13',
			'hora_programada': '10:00',
			'escuela': self.escuela.pk,
			'estado': 'pendiente',
		})

		self.assertEqual(respuesta.status_code, 200)
		self.assertEqual(Programacion.objects.count(), 2)
		self.assertContains(respuesta, 'listado-programaciones')
