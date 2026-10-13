from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from escuela.models import Distrito, Escuela
from .agenda import agenda_de_convocatoria, convocatoria_por_defecto, tonos_por_auxiliar
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
		# Un día de la próxima semana, para que ningún bloque haya "pasado".
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
		return agenda_de_convocatoria(
			convocatoria or self.convocatoria, 'dia', self.dia, auxiliares, tonos_por_auxiliar(auxiliares),
		)

	def _programar(self, hora, convocatoria=None):
		return Programacion.objects.create(
			convocatoria=convocatoria or self.convocatoria, auxiliar=self.auxiliar, escuela=self.escuela,
			fecha_programada=self.dia, hora_programada=hora,
		)


class AgendaTests(AgendaBase):
	def test_todos_los_bloques_del_periodo_se_pueden_programar(self):
		calendario = self._dia()
		self.assertEqual([fila['hora'] for fila in calendario['filas']], [time(hora) for hora in range(7, 17)])
		self.assertTrue(all(fila['celdas'][0]['puede_programar'] for fila in calendario['filas']))

	def test_disponibilidad_segun_el_horario(self):
		calendario = self._dia()
		# El horario 9:30–12:00 se cruza con los bloques de 9, 10 y 11.
		self.assertEqual(self._celda(calendario, 9)['disponibles'], [self.auxiliar])
		self.assertEqual(self._celda(calendario, 11)['disponibles'], [self.auxiliar])
		self.assertEqual(self._celda(calendario, 12)['disponibles'], [])

	def test_una_visita_ocupa_su_bloque_incluso_en_otra_convocatoria(self):
		otra = Convocatoria.objects.create(
			nombre='Otra', descripcion='', fecha_inicio=self.dia, fecha_fin=self.dia,
		)
		self._programar(time(10), convocatoria=otra)
		propia = self._programar(time(11))
		calendario = self._dia()
		self.assertEqual(self._celda(calendario, 10)['programaciones'], [])
		self.assertEqual(self._celda(calendario, 10)['disponibles'], [])
		self.assertEqual(self._celda(calendario, 11)['programaciones'], [propia])

	def test_ausencia_quita_la_disponibilidad(self):
		Ausencia.objects.create(auxiliar=self.auxiliar, fecha=self.dia, motivo='Enfermedad')
		self.assertEqual(self._celda(self._dia(), 10)['disponibles'], [])

	def test_fuera_del_periodo_no_se_programa(self):
		pasada = Convocatoria.objects.create(
			nombre='Pasada', descripcion='', fecha_inicio=self.dia - timedelta(days=30), fecha_fin=self.dia - timedelta(days=20),
		)
		celda = self._celda(self._dia(pasada), 9)
		self.assertTrue(celda['fuera_periodo'])
		self.assertFalse(celda['puede_programar'])

	def test_franja_de_la_convocatoria_en_la_semana(self):
		corta = Convocatoria.objects.create(
			nombre='Corta', descripcion='x', fecha_inicio=self.dia, fecha_fin=self.dia + timedelta(days=1),
		)
		auxiliares = [self.auxiliar]
		calendario = agenda_de_convocatoria(corta, 'semana', self.dia, auxiliares, tonos_por_auxiliar(auxiliares))
		dentro = [c for c in calendario['columnas'] if not c['fuera_periodo']]
		self.assertTrue(dentro[0]['inicia_tramo'])
		self.assertTrue(dentro[-1]['cierra_tramo'])
		self.assertEqual(sum(c['inicia_tramo'] for c in calendario['columnas']), 1)

	def test_visita_sin_auxiliar_aparece_sin_ocupar_el_bloque(self):
		sin_auxiliar = Programacion.objects.create(
			convocatoria=self.convocatoria, escuela=self.escuela, fecha_programada=self.dia, hora_programada=time(10),
		)
		auxiliares = [self.auxiliar]
		semana = agenda_de_convocatoria(self.convocatoria, 'semana', self.dia, auxiliares, tonos_por_auxiliar(auxiliares))
		self.assertTrue(semana['hay_sin_auxiliar'])
		fila = next(f for f in semana['filas'] if f['hora'] == time(10))
		celda = next(c for c in fila['celdas'] if c['fecha'] == self.dia)
		self.assertEqual(celda['programaciones'], [sin_auxiliar])
		# El auxiliar sigue disponible en ese bloque.
		self.assertEqual(celda['disponibles'], [self.auxiliar])

		otro = Auxiliar.objects.create(nombre='Ana', apellido='Ruiz', email='ana.ruiz@example.com', institucion='UES')
		Horario.objects.create(auxiliar=otro, fecha=self.dia, hora_inicio=time(8), hora_fin=time(9))
		auxiliares = [self.auxiliar, otro]
		dia = agenda_de_convocatoria(self.convocatoria, 'dia', self.dia, auxiliares, tonos_por_auxiliar(auxiliares))
		self.assertTrue(dia['columnas'][-1].get('solo_sin_auxiliar'))

		filtrado = agenda_de_convocatoria(
			self.convocatoria, 'semana', self.dia, [self.auxiliar], tonos_por_auxiliar([self.auxiliar]), incluir_sin_auxiliar=False,
		)
		self.assertFalse(filtrado['hay_sin_auxiliar'])

	def test_convocatoria_por_defecto(self):
		hoy = timezone.localdate()
		Convocatoria.objects.all().delete()
		self.assertIsNone(convocatoria_por_defecto(hoy))
		proxima = Convocatoria.objects.create(nombre='Próxima', descripcion='x', fecha_inicio=hoy + timedelta(days=5), fecha_fin=hoy + timedelta(days=9))
		self.assertEqual(convocatoria_por_defecto(hoy), proxima)
		en_curso = Convocatoria.objects.create(nombre='En curso', descripcion='x', fecha_inicio=hoy - timedelta(days=1), fecha_fin=hoy + timedelta(days=1))
		self.assertEqual(convocatoria_por_defecto(hoy), en_curso)


class ProgramacionPaginaTests(AgendaBase):
	def setUp(self):
		super().setUp()
		get_user_model().objects.create_user('agenda', password='Clave-2026')
		self.client.login(username='agenda', password='Clave-2026')

	def _datos(self, **extra):
		return {
			'convocatoria': self.convocatoria.pk, 'auxiliar': self.auxiliar.pk, 'escuela': self.escuela.pk,
			'fecha_programada': self.dia.isoformat(), 'hora_programada': '10:00:00', 'estado': 'pendiente', **extra,
		}

	def test_calendario_abre_la_agenda_semanal_de_la_convocatoria(self):
		respuesta = self.client.get(reverse('home_programacion'))
		self.assertEqual(respuesta.status_code, 200)
		self.assertEqual(respuesta.context['convocatoria'], self.convocatoria)
		self.assertEqual(respuesta.context['modo'], 'semana')
		self.assertContains(respuesta, 'Estás programando en la convocatoria')

	def test_agenda_en_cada_modo_y_listas(self):
		for parametros in ({'modo': 'mes'}, {'modo': 'semana'}, {'modo': 'dia'}, {'seccion': 'convocatorias'}, {'seccion': 'programaciones'}):
			with self.subTest(**parametros):
				respuesta = self.client.get(reverse('home_programacion'), {
					'convocatoria': self.convocatoria.pk, 'fecha': self.dia.isoformat(), **parametros,
				})
				self.assertEqual(respuesta.status_code, 200)

	def test_sin_convocatorias_invita_a_crear_una(self):
		Convocatoria.objects.all().delete()
		self.assertContains(self.client.get(reverse('home_programacion')), 'Aún no hay convocatorias')

	def test_rutas_anteriores_redirigen(self):
		self.assertRedirects(self.client.get(reverse('home_calendario')), reverse('home_programacion'))
		self.assertRedirects(
			self.client.get(reverse('home_convocatorias')), f"{reverse('home_programacion')}?seccion=convocatorias",
		)
		self.assertRedirects(
			self.client.get(reverse('convocatoria_agenda', args=[self.convocatoria.pk])),
			f"{reverse('home_programacion')}?convocatoria={self.convocatoria.pk}",
		)

	def test_crear_convocatoria_desde_el_calendario_lleva_a_su_agenda(self):
		respuesta = self.client.post(f"{reverse('convocatoria_nueva')}?origen=calendario", {
			'nombre': 'Nueva', 'descripcion': 'Prueba', 'fecha_inicio': self.dia.isoformat(), 'fecha_fin': self.dia.isoformat(),
		})
		nueva = Convocatoria.objects.get(nombre='Nueva')
		self.assertEqual(respuesta['HX-Redirect'], f"{reverse('home_programacion')}?convocatoria={nueva.pk}")

	def test_bloque_abre_el_formulario_con_la_convocatoria_fija(self):
		respuesta = self.client.get(reverse('programacion_nueva'), {
			'origen': 'convocatoria', 'convocatoria': self.convocatoria.pk,
			'fecha': self.dia.isoformat(), 'hora': '10:00', 'auxiliar': self.auxiliar.pk,
		})
		form = respuesta.context['form']
		self.assertEqual(form.initial['hora_programada'], time(10))
		self.assertEqual(form.fields['convocatoria'].initial, self.convocatoria.pk)
		self.assertTrue(form.fields['convocatoria'].widget.is_hidden)
		self.assertEqual(respuesta.context['disponibles_bloque'], [self.auxiliar])

	def test_guardar_desde_la_agenda_avisa_para_refrescarla(self):
		url = f"{reverse('programacion_nueva')}?origen=convocatoria&convocatoria={self.convocatoria.pk}"
		respuesta = self.client.post(url, self._datos())
		self.assertEqual(respuesta['HX-Trigger'], 'agenda-actualizada')
		self.assertNotContains(respuesta, 'listado-programaciones')
		self.assertTrue(Programacion.objects.filter(hora_programada=time(10)).exists())

	def test_se_puede_programar_sin_auxiliar(self):
		url = f"{reverse('programacion_nueva')}?origen=convocatoria&convocatoria={self.convocatoria.pk}"
		respuesta = self.client.post(url, self._datos(auxiliar=''))
		self.assertEqual(respuesta['HX-Trigger'], 'agenda-actualizada')
		programacion = Programacion.objects.get()
		self.assertIsNone(programacion.auxiliar)
		self.assertIn('Sin auxiliar', str(programacion))
		for parametros in ({}, {'seccion': 'programaciones'}):
			with self.subTest(**parametros):
				pagina = self.client.get(reverse('home_programacion'), {'convocatoria': self.convocatoria.pk, 'fecha': self.dia.isoformat(), **parametros})
				self.assertContains(pagina, 'Sin a')

	def test_impresiones_de_la_agenda(self):
		self._programar(time(10))
		Programacion.objects.create(
			convocatoria=self.convocatoria, escuela=self.escuela, fecha_programada=self.dia, hora_programada=time(11),
		)
		base = {'convocatoria': self.convocatoria.pk, 'fecha': self.dia.isoformat()}
		for alcance in ('convocatoria', 'semana', 'dia', 'auxiliar', 'sin_auxiliar', 'pendientes'):
			with self.subTest(alcance=alcance):
				respuesta = self.client.get(reverse('agenda_imprimir'), {**base, 'alcance': alcance, 'auxiliar': self.auxiliar.pk})
				self.assertEqual(respuesta['Content-Type'], 'application/pdf')
				self.assertTrue(respuesta.content.startswith(b'%PDF'))

	def test_rechaza_fecha_fuera_del_periodo(self):
		fuera = self.convocatoria.fecha_fin + timedelta(days=1)
		Horario.objects.create(auxiliar=self.auxiliar, fecha=fuera, hora_inicio=time(8), hora_fin=time(12))
		respuesta = self.client.post(reverse('programacion_nueva'), self._datos(fecha_programada=fuera.isoformat()))
		self.assertIn('fecha_programada', respuesta.context['form'].errors)

	def test_rechaza_auxiliar_ocupado_en_el_mismo_bloque(self):
		self._programar(time(10, 15))
		respuesta = self.client.post(reverse('programacion_nueva'), self._datos())
		self.assertIn('Este auxiliar ya tiene otra programación asignada en esa fecha y hora.', respuesta.context['form'].non_field_errors())

	def test_eliminar_convocatoria_desde_su_agenda_vuelve_al_calendario(self):
		respuesta = self.client.post(f"{reverse('convocatoria_eliminar', args=[self.convocatoria.pk])}?origen=convocatoria")
		self.assertEqual(respuesta['HX-Redirect'], reverse('home_programacion'))

	def test_cambio_rapido_de_estado(self):
		programacion = self._programar(time(10))
		programacion.fecha_programada = timezone.localdate() - timedelta(days=1)
		programacion.save()
		respuesta = self.client.post(reverse('programacion_estado', args=[programacion.pk]), {'estado': 'completado'})
		self.assertEqual(respuesta['HX-Trigger'], 'agenda-actualizada')
		programacion.refresh_from_db()
		self.assertEqual(programacion.estado, 'completado')

	def test_no_cambia_estado_antes_de_la_hora(self):
		programacion = self._programar(time(10))
		self.client.post(reverse('programacion_estado', args=[programacion.pk]), {'estado': 'completado'})
		programacion.refresh_from_db()
		self.assertEqual(programacion.estado, 'pendiente')

	def test_crear_no_pide_estado_y_queda_pendiente(self):
		respuesta = self.client.get(reverse('programacion_nueva'))
		self.assertNotIn('estado', respuesta.context['form'].fields)
		self.client.post(reverse('programacion_nueva'), self._datos(estado='completado'))
		self.assertEqual(Programacion.objects.get().estado, 'pendiente')

	def test_estado_editable_solo_desde_la_hora_de_la_visita(self):
		futura = self._programar(time(10))
		self.assertNotIn('estado', ProgramacionForm(instance=futura).fields)
		futura.fecha_programada = timezone.localdate() - timedelta(days=1)
		self.assertIn('estado', ProgramacionForm(instance=futura).fields)
