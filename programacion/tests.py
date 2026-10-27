import json
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from escuela.models import Distrito, Escuela
from . import services
from .agenda import agenda_de_convocatoria, personal_asignado, convocatoria_por_defecto, tonos_por_persona
from .forms import PersonalDelDia, ProgramacionForm
from .models import Asistencia, Personal, Convocatoria, ConvocatoriaPersonal, Horario, Programacion


class ProgramacionFormTests(TestCase):
	def setUp(self):
		distrito = Distrito.objects.create(nombre='Distrito de prueba')
		self.escuela = Escuela.objects.create(
			codigo='HOR-1', nombre='Escuela de prueba', nombre_corto='Escuela prueba', distrito=distrito,
		)
		self.convocatoria = Convocatoria.objects.create(
			nombre='Convocatoria de prueba', descripcion='', fecha_inicio='2026-05-01', fecha_fin='2026-05-31',
		)

	def _formulario(self, jornada, **extra):
		return ProgramacionForm(data={
			'convocatoria': self.convocatoria.pk,
			'fecha_programada': '2026-05-12',
			'jornada': jornada,
			'escuela': self.escuela.pk,
			'estado': 'pendiente',
			**extra,
		})

	def test_ya_no_tiene_campo_de_persona(self):
		form = self._formulario('manana')
		self.assertNotIn('persona', form.fields)
		self.assertTrue(form.is_valid(), form.errors)

	def test_rechaza_fecha_fuera_de_la_convocatoria(self):
		form = self._formulario('manana', fecha_programada='2026-06-02')
		self.assertIn('fecha_programada', form.errors)

	def test_rechaza_escuela_en_jornada_que_se_cruza(self):
		Programacion.objects.create(
			convocatoria=self.convocatoria, fecha_programada='2026-05-12', jornada='manana', escuela=self.escuela,
		)
		for jornada in ('manana', 'completa'):
			with self.subTest(jornada=jornada):
				form = self._formulario(jornada)
				self.assertFalse(form.is_valid())
				self.assertIn('Esta escuela ya tiene otra programación asignada en esa fecha y jornada.', form.non_field_errors())
		self.assertTrue(self._formulario('tarde').is_valid())

	def test_permite_editar_sin_cambiar_jornada(self):
		programacion = Programacion.objects.create(
			convocatoria=self.convocatoria, fecha_programada='2026-05-12', jornada='tarde', escuela=self.escuela,
		)
		programacion.refresh_from_db()
		form = ProgramacionForm(data=self._formulario('tarde').data, instance=programacion)
		self.assertTrue(form.is_valid(), form.errors)


class AgendaBase(TestCase):
	def setUp(self):
		# Un día de la próxima semana, para que ningún turno haya "pasado".
		self.dia = timezone.localdate() + timedelta(days=7)
		distrito = Distrito.objects.create(nombre='Distrito agenda')
		self.escuela = Escuela.objects.create(
			codigo='AGE-1', nombre='Escuela agenda', nombre_corto='Agenda', distrito=distrito,
		)
		self.convocatoria = Convocatoria.objects.create(
			nombre='Convocatoria agenda', descripcion='',
			fecha_inicio=self.dia - timedelta(days=10), fecha_fin=self.dia + timedelta(days=10),
		)
		self.persona = self._persona('Luis', 'Gómez', 'manana')
		self._asignar(self.persona)

	def _persona(self, nombre, apellido, jornada):
		"""Personal con horario solo el día de prueba, en la jornada dada."""
		persona = Personal.objects.create(
			nombre=nombre, apellido=apellido, email=f'{nombre.lower()}.agenda@example.com', institucion='UES',
		)
		Horario.objects.create(persona=persona, dia=self.dia.isoweekday(), fecha_inicio=self.dia, fecha_fin=self.dia, jornada=jornada)
		return persona

	def _asignar(self, persona, fecha=None):
		return ConvocatoriaPersonal.objects.create(convocatoria=self.convocatoria, persona=persona, fecha=fecha or self.dia)

	def _celda(self, calendario, turno):
		fila = next(fila for fila in calendario['filas'] if fila['turno'] == turno)
		return next(celda for celda in fila['celdas'] if celda['fecha'] == self.dia)

	def _agenda(self, modo='dia', convocatoria=None, personas=None, **extra):
		convocatoria = convocatoria or self.convocatoria
		personas = personas if personas is not None else list(personal_asignado(convocatoria))
		return agenda_de_convocatoria(convocatoria, modo, self.dia, personas, tonos_por_persona(personas), **extra)

	def _programar(self, jornada='manana', convocatoria=None):
		return Programacion.objects.create(
			convocatoria=convocatoria or self.convocatoria, escuela=self.escuela, fecha_programada=self.dia, jornada=jornada,
		)


class AgendaTests(AgendaBase):
	def test_cada_dia_tiene_turno_de_manana_y_de_tarde(self):
		calendario = self._agenda()
		self.assertEqual([fila['turno'] for fila in calendario['filas']], ['manana', 'tarde'])
		self.assertEqual(len(calendario['columnas']), 1)
		self.assertTrue(all(fila['celdas'][0]['puede_programar'] for fila in calendario['filas']))

	def test_cubren_los_personas_de_la_convocatoria_segun_su_horario(self):
		calendario = self._agenda()
		# Su horario es solo de la mañana.
		self.assertEqual(self._celda(calendario, 'manana')['cubren'], [self.persona])
		self.assertEqual(self._celda(calendario, 'tarde')['cubren'], [])

	def test_persona_sin_asignar_a_ese_dia_no_cubre(self):
		self._persona('Eva', 'Paz', 'tarde')  # tiene horario ese día, pero no está asignado
		self.assertEqual(self._celda(self._agenda(), 'tarde')['cubren'], [])

	def test_solo_cubre_los_dias_asignados(self):
		# Mismo horario todas las semanas, pero asignado solo a self.dia.
		Horario.objects.filter(persona=self.persona).update(
			fecha_inicio=self.convocatoria.fecha_inicio, fecha_fin=self.convocatoria.fecha_fin,
		)
		otra_semana = self.dia + timedelta(days=7)
		calendario = agenda_de_convocatoria(
			self.convocatoria, 'semana', otra_semana, [self.persona], tonos_por_persona([self.persona]),
		)
		celda = next(c for c in calendario['filas'][0]['celdas'] if c['fecha'] == otra_semana)
		self.assertEqual(celda['cubren'], [])
		self.assertEqual(self._celda(self._agenda('semana'), 'manana')['cubren'], [self.persona])
		columna = next(c for c in self._agenda('semana')['columnas'] if c['fecha'] == self.dia)
		self.assertEqual([item['persona'] for item in columna['asignados']], [self.persona])

	def test_visita_cubierta_parcial_o_sin_cobertura(self):
		manana = self._programar('manana')
		completa = Programacion.objects.create(
			convocatoria=self.convocatoria, escuela=Escuela.objects.create(codigo='AGE-2', nombre='Otra', nombre_corto='Otra', distrito=self.escuela.distrito),
			fecha_programada=self.dia, jornada='completa',
		)
		calendario = self._agenda()
		self.assertTrue(next(p for p in calendario['programaciones'] if p.pk == manana.pk).cubierta)
		# Todo el día: la mañana la cubre Luis, pero la tarde nadie.
		visita = next(p for p in calendario['programaciones'] if p.pk == completa.pk)
		self.assertEqual(visita.cubren, [self.persona])
		self.assertFalse(visita.cubierta)
		self.assertTrue(calendario['hay_sin_cobertura'])
		# Con alguien en la tarde queda cubierta.
		self._asignar(self._persona('Ana', 'Ruiz', 'tarde'))
		visita = next(p for p in self._agenda()['programaciones'] if p.pk == completa.pk)
		self.assertTrue(visita.cubierta)

	def test_visita_de_todo_el_dia_aparece_en_los_dos_turnos(self):
		completa = self._programar('completa')
		calendario = self._agenda()
		for turno in ('manana', 'tarde'):
			with self.subTest(turno=turno):
				self.assertEqual([p.pk for p in self._celda(calendario, turno)['programaciones']], [completa.pk])

	def test_ausencia_quita_la_cobertura(self):
		Asistencia.objects.create(persona=self.persona, fecha=self.dia, estado='ausente', observacion='Enfermedad')
		self.assertEqual(self._celda(self._agenda(), 'manana')['cubren'], [])

	def test_filtrar_por_persona_muestra_solo_lo_que_cubre(self):
		otra = self._persona('Ana', 'Ruiz', 'tarde')
		self._asignar(otra)
		self._programar('manana')
		tarde = self._programar('tarde')
		# Ana solo trabaja en la tarde: su hoja de ruta no incluye la visita de la mañana.
		calendario = self._agenda('semana', personas=[otra], solo_las_que_cubren=True)
		self.assertEqual([p.pk for p in calendario['programaciones']], [tarde.pk])

	def test_fuera_del_periodo_no_se_programa(self):
		pasada = Convocatoria.objects.create(
			nombre='Pasada', descripcion='', fecha_inicio=self.dia - timedelta(days=30), fecha_fin=self.dia - timedelta(days=20),
		)
		celda = self._celda(self._agenda(convocatoria=pasada), 'manana')
		self.assertTrue(celda['fuera_periodo'])
		self.assertFalse(celda['puede_programar'])

	def test_franja_de_la_convocatoria_en_la_semana(self):
		corta = Convocatoria.objects.create(
			nombre='Corta', descripcion='x', fecha_inicio=self.dia, fecha_fin=self.dia + timedelta(days=1),
		)
		calendario = self._agenda('semana', convocatoria=corta)
		dentro = [c for c in calendario['columnas'] if not c['fuera_periodo']]
		self.assertTrue(dentro[0]['inicia_tramo'])
		self.assertTrue(dentro[-1]['cierra_tramo'])
		self.assertEqual(sum(c['inicia_tramo'] for c in calendario['columnas']), 1)

	def test_convocatoria_por_defecto(self):
		hoy = timezone.localdate()
		Convocatoria.objects.all().delete()
		self.assertIsNone(convocatoria_por_defecto(hoy))
		proxima = Convocatoria.objects.create(nombre='Próxima', descripcion='x', fecha_inicio=hoy + timedelta(days=5), fecha_fin=hoy + timedelta(days=9))
		self.assertEqual(convocatoria_por_defecto(hoy), proxima)
		en_curso = Convocatoria.objects.create(nombre='En curso', descripcion='x', fecha_inicio=hoy - timedelta(days=1), fecha_fin=hoy + timedelta(days=1))
		self.assertEqual(convocatoria_por_defecto(hoy), en_curso)


class AsignarPersonalDiaTests(AgendaBase):
	def setUp(self):
		super().setUp()
		self.client.force_login(get_user_model().objects.create_superuser('convocatoria', password='Clave-2026'))
		self.url = f"{reverse('convocatoria_dia_personas', args=[self.convocatoria.pk])}?fecha={self.dia.isoformat()}"

	def _asignados(self, fecha=None):
		return set(self.convocatoria.asignaciones.filter(fecha=fecha or self.dia).values_list('persona__nombre', flat=True))

	def _personas(self, respuesta, lista):
		return [fila['persona'] for fila in respuesta.context[lista]]

	def test_lista_asignados_y_los_que_tienen_horario_ese_dia(self):
		con_horario = self._persona('Ana', 'Ruiz', 'tarde')
		sin_horario = Personal.objects.create(nombre='Eva', apellido='Paz', email='eva.paz@example.com', institucion='UES')
		ausente = self._persona('Leo', 'Sol', 'completa')
		Asistencia.objects.create(persona=ausente, fecha=self.dia, estado='justificado', observacion='Enfermedad')

		respuesta = self.client.get(self.url)
		self.assertEqual(self._personas(respuesta, 'asignados'), [self.persona])
		disponibles = {fila['persona']: fila for fila in respuesta.context['disponibles']}
		self.assertEqual(list(disponibles), [con_horario, ausente])  # por apellido (Ruiz, Sol); sin_horario no aparece
		self.assertNotIn(sin_horario, disponibles)
		self.assertEqual(disponibles[con_horario]['jornadas'], ['Tarde'])
		self.assertTrue(disponibles[con_horario]['puede_agregarse'])
		self.assertFalse(disponibles[ausente]['puede_agregarse'])
		self.assertContains(respuesta, 'Quitar')
		self.assertContains(respuesta, 'Agregar')

	def test_agregar_y_quitar(self):
		ana = self._persona('Ana', 'Ruiz', 'tarde')
		respuesta = self.client.post(self.url, {'agregar': ana.pk})
		self.assertEqual(respuesta['HX-Trigger'], 'agenda-actualizada')
		self.assertEqual(self._asignados(), {'Luis', 'Ana'})
		self.assertEqual(self._personas(respuesta, 'asignados'), [self.persona, ana])

		respuesta = self.client.post(self.url, {'quitar': self.persona.pk})
		self.assertEqual(respuesta['HX-Trigger'], 'agenda-actualizada')
		self.assertEqual(self._asignados(), {'Ana'})
		# El que se quita vuelve a la lista de los que se pueden agregar.
		self.assertIn(self.persona, self._personas(respuesta, 'disponibles'))

	def test_no_agrega_sin_horario_o_ausente(self):
		sin_horario = Personal.objects.create(nombre='Eva', apellido='Paz', email='eva.paz@example.com', institucion='UES')
		ausente = self._persona('Leo', 'Sol', 'completa')
		Asistencia.objects.create(persona=ausente, fecha=self.dia, estado='justificado', observacion='Enfermedad')
		for persona, motivo in ((sin_horario, 'no tiene horario'), (ausente, '«justificado»')):
			with self.subTest(persona=persona.nombre):
				respuesta = self.client.post(self.url, {'agregar': persona.pk})
				self.assertIn(motivo, respuesta.context['error'])
				self.assertNotIn('HX-Trigger', respuesta)
		self.assertEqual(self._asignados(), {'Luis'})

	def test_la_asignacion_es_solo_de_ese_dia(self):
		Horario.objects.filter(persona=self.persona).update(
			fecha_inicio=self.convocatoria.fecha_inicio, fecha_fin=self.convocatoria.fecha_fin,
		)
		otro_dia = self.dia + timedelta(days=7)
		self.assertIsNone(PersonalDelDia(self.convocatoria, otro_dia).agregar(self.persona.pk))
		self.assertEqual(self._asignados(otro_dia), {'Luis'})
		PersonalDelDia(self.convocatoria, otro_dia).quitar(self.persona.pk)
		self.assertEqual(self._asignados(otro_dia), set())
		self.assertEqual(self._asignados(), {'Luis'})

	def test_se_puede_quitar_aunque_ya_no_tenga_horario(self):
		Horario.objects.filter(persona=self.persona).delete()
		respuesta = self.client.get(self.url)
		self.assertEqual(self._personas(respuesta, 'asignados'), [self.persona])
		self.client.post(self.url, {'quitar': self.persona.pk})
		self.assertEqual(self._asignados(), set())

	def _hoy_asignado(self):
		"""Luis con horario y asignado hoy (la inasistencia solo se registra desde ese día)."""
		hoy = timezone.localdate()
		Horario.objects.create(persona=self.persona, dia=hoy.isoweekday(), fecha_inicio=hoy, fecha_fin=hoy, jornada='completa')
		self._asignar(self.persona, hoy)
		return hoy, f"{reverse('convocatoria_dia_personas', args=[self.convocatoria.pk])}?fecha={hoy.isoformat()}"

	def test_registrar_que_no_llego_y_deshacerlo(self):
		hoy, url = self._hoy_asignado()
		visita = Programacion.objects.create(convocatoria=self.convocatoria, escuela=self.escuela, fecha_programada=hoy, jornada='manana')
		self.assertTrue(PersonalDelDia(self.convocatoria, hoy).asignados_ids())

		respuesta = self.client.post(url, {'no_llego': self.persona.pk, 'motivo': 'Enfermo'})
		self.assertEqual(respuesta['HX-Trigger'], 'agenda-actualizada')
		asistencia = Asistencia.objects.get(persona=self.persona, fecha=hoy)
		self.assertEqual((asistencia.estado, asistencia.observacion), ('ausente', 'Enfermo'))
		fila = respuesta.context['asignados'][0]
		self.assertEqual(fila['asistencia'].observacion, 'Enfermo')
		self.assertContains(respuesta, 'Sí llegó')
		# Sigue asignado, pero ya no cubre la visita.
		detalle = self.client.get(reverse('programacion_detalle', args=[visita.pk]))
		self.assertEqual(detalle.context['cubren'], [])

		self.client.post(url, {'si_llego': self.persona.pk})
		self.assertEqual(Asistencia.objects.get(persona=self.persona, fecha=hoy).estado, 'presente')
		self.assertEqual(self.client.get(reverse('programacion_detalle', args=[visita.pk])).context['cubren'], [self.persona])

	def test_motivo_por_defecto(self):
		hoy, url = self._hoy_asignado()
		self.client.post(url, {'no_llego': self.persona.pk, 'motivo': '  '})
		self.assertEqual(Asistencia.objects.get(persona=self.persona, fecha=hoy).observacion, PersonalDelDia.MOTIVO_POR_DEFECTO)

	def test_no_se_registra_en_un_dia_que_no_ha_llegado(self):
		respuesta = self.client.post(self.url, {'no_llego': self.persona.pk})  # self.dia es la próxima semana
		self.assertIn('a partir de ese día', respuesta.context['error'])
		self.assertFalse(Asistencia.objects.exists())
		self.assertFalse(self.client.get(self.url).context['del_dia'].se_puede_registrar_inasistencia)

	def test_solo_se_registra_a_asignados(self):
		hoy, url = self._hoy_asignado()
		otra = self._persona('Ana', 'Ruiz', 'tarde')
		respuesta = self.client.post(url, {'no_llego': otra.pk})
		self.assertIn('asignadas', respuesta.context['error'])

	def test_inasistencia_pide_permiso_de_asistencia(self):
		hoy, url = self._hoy_asignado()
		usuario = get_user_model().objects.create_user('coordinador', password='Clave-2026')
		usuario.user_permissions.add(*Permission.objects.filter(codename__in=['add_convocatoriapersonal', 'delete_convocatoriapersonal']))
		self.client.force_login(usuario)
		self.assertEqual(self.client.post(url, {'no_llego': self.persona.pk}).status_code, 403)
		self.assertFalse(Asistencia.objects.exists())

	def test_rechaza_dia_fuera_de_la_convocatoria(self):
		fuera = self.convocatoria.fecha_fin + timedelta(days=1)
		url = f"{reverse('convocatoria_dia_personas', args=[self.convocatoria.pk])}?fecha={fuera.isoformat()}"
		self.assertEqual(self.client.get(url).status_code, 400)

	def test_validacion_del_modelo(self):
		asignacion = ConvocatoriaPersonal(convocatoria=self.convocatoria, persona=self.persona, fecha=self.dia + timedelta(days=1))
		with self.assertRaises(ValidationError):
			asignacion.clean()


class ProgramacionPaginaTests(AgendaBase):
	def setUp(self):
		super().setUp()
		get_user_model().objects.create_superuser('agenda', password='Clave-2026')
		self.client.login(username='agenda', password='Clave-2026')

	def _datos(self, **extra):
		return {
			'convocatoria': self.convocatoria.pk, 'escuela': self.escuela.pk,
			'fecha_programada': self.dia.isoformat(), 'jornada': 'manana', 'estado': 'pendiente', **extra,
		}

	def test_calendario_abre_la_agenda_semanal_de_la_convocatoria(self):
		respuesta = self.client.get(reverse('home_programacion'))
		self.assertEqual(respuesta.status_code, 200)
		self.assertEqual(respuesta.context['convocatoria'], self.convocatoria)
		self.assertEqual(respuesta.context['modo'], 'semana')
		self.assertEqual(respuesta.context['personas'], [self.persona])
		self.assertContains(respuesta, 'Estás programando en la convocatoria')
		semana = self.client.get(reverse('home_programacion'), {'convocatoria': self.convocatoria.pk, 'fecha': self.dia.isoformat()})
		self.assertContains(semana, 'Agregar o quitar personas del')  # el día de prueba ya tiene a Luis

	def test_agenda_en_cada_modo_y_listas(self):
		self._programar('completa')
		for parametros in ({'modo': 'mes'}, {'modo': 'semana'}, {'modo': 'dia'}, {'modo': 'semana', 'persona': self.persona.pk}, {'seccion': 'convocatorias'}, {'seccion': 'programaciones'}):
			with self.subTest(**parametros):
				respuesta = self.client.get(reverse('home_programacion'), {
					'convocatoria': self.convocatoria.pk, 'fecha': self.dia.isoformat(), **parametros,
				})
				self.assertEqual(respuesta.status_code, 200)

	def test_la_agenda_muestra_el_codigo_y_abre_el_detalle(self):
		programacion = self._programar('manana')
		respuesta = self.client.get(reverse('home_programacion'), {'convocatoria': self.convocatoria.pk, 'fecha': self.dia.isoformat()})
		self.assertContains(respuesta, reverse('programacion_detalle', args=[programacion.pk]))
		self.assertContains(respuesta, f'>{self.escuela.codigo}</span>', html=False)

		detalle = self.client.get(reverse('programacion_detalle', args=[programacion.pk]))
		self.assertContains(detalle, self.escuela.nombre)
		self.assertContains(detalle, self.escuela.codigo)
		self.assertEqual(detalle.context['cubren'], [self.persona])
		self.assertTrue(detalle.context['cubierta'])
		self.assertContains(detalle, reverse('programacion_editar', args=[programacion.pk]))

	def test_detalle_de_visita_sin_cobertura(self):
		programacion = self._programar('tarde')  # Luis solo trabaja en la mañana
		detalle = self.client.get(reverse('programacion_detalle', args=[programacion.pk]))
		self.assertEqual(detalle.context['cubren'], [])
		self.assertFalse(detalle.context['cubierta'])

	def test_contador_de_visitas_sin_cobertura(self):
		self._programar('tarde')  # Luis solo trabaja en la mañana
		respuesta = self.client.get(reverse('home_programacion'), {'convocatoria': self.convocatoria.pk})
		self.assertEqual(respuesta.context['sin_cobertura'], 1)

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

	def test_turno_abre_el_formulario_con_la_convocatoria_fija_y_quien_cubre(self):
		respuesta = self.client.get(reverse('programacion_nueva'), {
			'origen': 'convocatoria', 'convocatoria': self.convocatoria.pk, 'fecha': self.dia.isoformat(), 'jornada': 'manana',
		})
		form = respuesta.context['form']
		self.assertEqual(form.initial['jornada'], 'manana')
		self.assertEqual(form.fields['convocatoria'].initial, self.convocatoria.pk)
		self.assertTrue(form.fields['convocatoria'].widget.is_hidden)
		self.assertEqual(respuesta.context['cubren'], [self.persona])
		self.assertTrue(respuesta.context['cubierta'])

	def test_cobertura_en_el_formulario(self):
		url = reverse('programacion_cobertura')
		base = {'convocatoria': self.convocatoria.pk, 'fecha_programada': self.dia.isoformat()}
		self.assertEqual(self.client.get(url, {**base, 'jornada': 'manana'}).context['cubren'], [self.persona])
		for jornada in ('tarde', 'completa'):
			with self.subTest(jornada=jornada):
				respuesta = self.client.get(url, {**base, 'jornada': jornada})
				self.assertFalse(respuesta.context['cubierta'])
		self.assertContains(self.client.get(url, {**base, 'jornada': 'tarde'}), 'Ninguna persona asignada a ese día trabaja esta jornada')
		self.assertContains(self.client.get(url, {'convocatoria': self.convocatoria.pk}), 'Elige la fecha y la jornada')

	def test_guardar_desde_la_agenda_avisa_para_refrescarla(self):
		url = f"{reverse('programacion_nueva')}?origen=convocatoria&convocatoria={self.convocatoria.pk}"
		respuesta = self.client.post(url, self._datos())
		self.assertEqual(respuesta['HX-Trigger'], 'agenda-actualizada')
		self.assertNotContains(respuesta, 'listado-programaciones')
		self.assertTrue(Programacion.objects.filter(jornada='manana').exists())

	def test_se_guarda_aunque_nadie_cubra_la_jornada(self):
		self.client.post(reverse('programacion_nueva'), self._datos(jornada='tarde'))
		self.assertTrue(Programacion.objects.filter(jornada='tarde').exists())

	def test_impresiones_de_la_agenda(self):
		self._programar('manana')
		self._programar('tarde')
		base = {'convocatoria': self.convocatoria.pk, 'fecha': self.dia.isoformat()}
		for alcance in ('convocatoria', 'semana', 'dia', 'control'):
			with self.subTest(alcance=alcance):
				respuesta = self.client.get(reverse('agenda_imprimir'), {**base, 'alcance': alcance})
				self.assertEqual(respuesta['Content-Type'], 'application/pdf')
				self.assertTrue(respuesta.content.startswith(b'%PDF'))

	def test_eliminar_convocatoria_desde_su_agenda_vuelve_al_calendario(self):
		respuesta = self.client.post(f"{reverse('convocatoria_eliminar', args=[self.convocatoria.pk])}?origen=convocatoria")
		self.assertEqual(respuesta['HX-Redirect'], reverse('home_programacion'))

	def test_cambio_rapido_de_estado(self):
		programacion = self._programar('manana')
		programacion.fecha_programada = timezone.localdate() - timedelta(days=1)
		programacion.save()
		respuesta = self.client.post(reverse('programacion_estado', args=[programacion.pk]), {'estado': 'completado'})
		self.assertEqual(respuesta['HX-Trigger'], 'agenda-actualizada')
		programacion.refresh_from_db()
		self.assertEqual(programacion.estado, 'completado')

	def test_no_cambia_estado_antes_de_la_jornada(self):
		programacion = self._programar('manana')
		self.client.post(reverse('programacion_estado', args=[programacion.pk]), {'estado': 'completado'})
		programacion.refresh_from_db()
		self.assertEqual(programacion.estado, 'pendiente')

	def test_crear_no_pide_estado_y_queda_pendiente(self):
		respuesta = self.client.get(reverse('programacion_nueva'))
		self.assertNotIn('estado', respuesta.context['form'].fields)
		self.client.post(reverse('programacion_nueva'), self._datos(estado='completado'))
		self.assertEqual(Programacion.objects.get().estado, 'pendiente')

	def test_estado_editable_solo_desde_la_jornada_de_la_visita(self):
		futura = self._programar('manana')
		self.assertNotIn('estado', ProgramacionForm(instance=futura).fields)
		futura.fecha_programada = timezone.localdate() - timedelta(days=1)
		self.assertIn('estado', ProgramacionForm(instance=futura).fields)


class HorarioSemanalTests(TestCase):
	"""El horario se repite cada semana en su día, solo dentro del periodo de labores."""

	def setUp(self):
		self.client.force_login(get_user_model().objects.create_superuser('horarios', password='Clave-2026'))
		self.persona = Personal.objects.create(
			nombre='Luis', apellido='Gómez', email='luis.semanal@example.com', institucion='Institución de prueba',
		)
		# Lunes en la mañana, del lunes 4 al domingo 31 de mayo de 2026.
		self.horario = Horario.objects.create(
			persona=self.persona, dia=Horario.Dia.LUNES, jornada='manana',
			fecha_inicio=date(2026, 5, 4), fecha_fin=date(2026, 5, 31),
		)

	def _datos(self, **cambios):
		"""Semana con martes y jueves en la tarde, en todo mayo."""
		datos = {
			'activo_2': 'on', 'jornada_2': 'tarde', 'activo_4': 'on', 'jornada_4': 'tarde',
			'fecha_inicio': '2026-05-04', 'fecha_fin': '2026-05-31',
		}
		datos.update(cambios)
		return datos

	def _guardar(self, persona=None, **cambios):
		return self.client.post(reverse('horario_editar', args=[(persona or self.persona).pk]), self._datos(**cambios))

	def test_aplica_cada_semana_dentro_del_periodo(self):
		lunes_de_mayo = [date(2026, 5, dia) for dia in (4, 11, 18, 25)]
		for fecha in lunes_de_mayo:
			self.assertTrue(Horario.objects.del_dia(fecha).exists(), fecha)
		self.assertFalse(Horario.objects.del_dia(date(2026, 5, 5)).exists())  # martes
		self.assertFalse(Horario.objects.del_dia(date(2026, 6, 1)).exists())  # lunes fuera del periodo

		# Solo se le puede asignar a los lunes de su periodo.
		mayo = Convocatoria.objects.create(nombre='Mayo', descripcion='', fecha_inicio=date(2026, 5, 1), fecha_fin=date(2026, 5, 31))
		for dia in range(1, 32):
			fecha = date(2026, 5, dia)
			with self.subTest(fecha=fecha):
				self.assertEqual(PersonalDelDia(mayo, fecha).puede_agregarse(self.persona), fecha in lunes_de_mayo)

	def test_guardar_reemplaza_el_horario(self):
		# Tiene uno solo: el lunes que tenía se reemplaza por la semana marcada.
		respuesta = self._guardar()
		self.assertEqual(respuesta.status_code, 200)
		self.assertEqual(
			sorted(Horario.objects.filter(persona=self.persona).values_list('dia', 'jornada')),
			[(Horario.Dia.MARTES, 'tarde'), (Horario.Dia.JUEVES, 'tarde')],
		)

	def test_se_abre_con_el_horario_que_tiene(self):
		form = self.client.get(reverse('horario_editar', args=[self.persona.pk])).context['form']
		self.assertTrue(form['activo_1'].value())
		self.assertEqual(form['jornada_1'].value(), 'manana')
		self.assertFalse(form['activo_2'].value())
		self.assertEqual(form['fecha_inicio'].value(), date(2026, 5, 4))

	def test_exige_un_dia_su_jornada_y_periodo_valido(self):
		errores = self._guardar(activo_2='', activo_4='', fecha_fin='2026-05-01').context['form'].errors
		self.assertIn('__all__', errores)
		self.assertIn('fecha_fin', errores)
		self.assertIn('jornada_3', self._guardar(activo_3='on').context['form'].errors)
		self.assertEqual(Horario.objects.get(persona=self.persona), self.horario)

	def test_eliminar_quita_todo_el_horario(self):
		self._guardar()
		self.client.post(reverse('horario_eliminar', args=[self.persona.pk]))
		self.assertFalse(Horario.objects.filter(persona=self.persona).exists())

	def test_asistencia_solo_en_dia_con_horario(self):
		datos = {'persona': self.persona.pk, 'estado': 'ausente', 'observacion': 'Consulta médica'}
		respuesta = self.client.post(reverse('asistencia_registrar'), {**datos, 'fecha': '2026-05-05'})  # martes
		self.assertIn('no tiene horario', respuesta.context['error'])
		self.client.post(reverse('asistencia_registrar'), {**datos, 'fecha': '2026-05-11'})  # lunes
		self.assertTrue(Asistencia.objects.filter(persona=self.persona, fecha=date(2026, 5, 11), estado='ausente').exists())


class FiltrosPersonalTests(TestCase):
	def setUp(self):
		self.client.force_login(get_user_model().objects.create_superuser('filtros', password='Clave-2026'))
		self.hoy = timezone.localdate()
		self.lunes = self.hoy + timedelta(days=(1 - self.hoy.isoweekday()) % 7 or 7)  # próximo lunes

		def persona(nombre, institucion='UES'):
			return Personal.objects.create(nombre=nombre, apellido='Prueba', email=f'{nombre.lower()}.filtro@example.com', institucion=institucion)

		def horario(aux, dia, jornada, inicio, fin):
			Horario.objects.create(persona=aux, dia=dia, jornada=jornada, fecha_inicio=inicio, fecha_fin=fin)

		mes = timedelta(days=30)
		self.manana = persona('Mañanero')
		horario(self.manana, Horario.Dia.LUNES, 'manana', self.hoy - mes, self.hoy + mes)
		self.completo = persona('Completo', 'UCA')
		horario(self.completo, Horario.Dia.LUNES, 'completa', self.hoy - mes, self.hoy + mes)
		self.vencido = persona('Vencido')
		horario(self.vencido, Horario.Dia.LUNES, 'tarde', self.hoy - 3 * mes, self.hoy - 2 * mes)
		self.sin_horario = persona('Libre', 'UCA')

	def _nombres(self, **filtros):
		respuesta = self.client.get(reverse('buscar_personas'), filtros)
		self.assertEqual(respuesta.status_code, 200)
		return {persona.nombre for persona in respuesta.context['personas']}

	def test_sin_filtros_lista_todos(self):
		self.assertEqual(self._nombres(), {'Mañanero', 'Completo', 'Vencido', 'Libre'})

	def test_con_y_sin_horario(self):
		self.assertEqual(self._nombres(horario='con'), {'Mañanero', 'Completo', 'Vencido'})
		self.assertEqual(self._nombres(horario='sin'), {'Libre'})
		self.assertEqual(self._nombres(horario='vigente'), {'Mañanero', 'Completo'})
		self.assertEqual(self._nombres(horario='vencido'), {'Vencido'})

	def test_por_fecha(self):
		lunes = self.lunes.isoformat()
		self.assertEqual(self._nombres(fecha=lunes), {'Mañanero', 'Completo'})
		# "Sin horario" con fecha: los que no trabajan ese día.
		self.assertEqual(self._nombres(fecha=lunes, horario='sin'), {'Vencido', 'Libre'})
		martes = (self.lunes + timedelta(days=1)).isoformat()
		self.assertEqual(self._nombres(fecha=martes), set())

	def test_por_dia_y_jornada(self):
		self.assertEqual(self._nombres(dia=Horario.Dia.LUNES), {'Mañanero', 'Completo', 'Vencido'})
		# Quien trabaja todo el día también cuenta para la mañana y la tarde.
		self.assertEqual(self._nombres(jornada='manana'), {'Mañanero', 'Completo'})
		self.assertEqual(self._nombres(jornada='tarde'), {'Completo', 'Vencido'})
		self.assertEqual(self._nombres(jornada='completa'), {'Completo'})
		self.assertEqual(self._nombres(fecha=self.lunes.isoformat(), jornada='tarde'), {'Completo'})

	def test_texto_e_institucion(self):
		self.assertEqual(self._nombres(q='libre'), {'Libre'})
		self.assertEqual(self._nombres(institucion='UCA'), {'Completo', 'Libre'})
		self.assertEqual(self._nombres(institucion='UCA', horario='sin'), {'Libre'})

	def test_asignados_en_convocatoria(self):
		convocatoria = Convocatoria.objects.create(nombre='Filtro', descripcion='', fecha_inicio=self.lunes, fecha_fin=self.lunes + timedelta(days=6))
		ConvocatoriaPersonal.objects.create(convocatoria=convocatoria, persona=self.completo, fecha=self.lunes)
		self.assertEqual(self._nombres(convocatoria=convocatoria.pk), {'Completo'})
		self.assertEqual(self._nombres(convocatoria=convocatoria.pk, fecha=(self.lunes + timedelta(days=7)).isoformat()), set())

	def test_estado_del_horario_en_el_listado(self):
		respuesta = self.client.get(reverse('home_personal'))
		estados = {persona.nombre: persona.estado_horario for persona in respuesta.context['personas']}
		self.assertEqual(estados, {'Mañanero': 'vigente', 'Completo': 'vigente', 'Vencido': 'vencido', 'Libre': 'sin'})
		self.assertContains(respuesta, 'Sin horario')

	def test_imprimir_respeta_los_filtros(self):
		respuesta = self.client.get(reverse('persona_imprimir'), {'horario': 'sin'})
		self.assertEqual(respuesta['Content-Type'], 'application/pdf')

	def test_al_crear_devuelve_el_listado_para_actualizarlo(self):
		respuesta = self.client.post(f"{reverse('persona_nuevo')}?horario=sin", {
			'tipo': 'practicante', 'nombre': 'Nuevo', 'apellido': 'Prueba', 'email': 'nuevo.filtro@example.com',
			'telefono': '', 'institucion': 'UES',
		})
		self.assertContains(respuesta, 'id="listado-personas" hx-swap-oob="true"')
		# El listado vuelve con los filtros que estaban aplicados.
		self.assertEqual({a.nombre for a in respuesta.context['personas']}, {'Libre', 'Nuevo'})


class ProgramacionServicesTests(AgendaBase):
	"""Lógica de programacion/services.py, sin pasar por las vistas."""

	def test_fechas_vecinas(self):
		dia = date(2026, 1, 31)
		self.assertEqual(services.fechas_vecinas('dia', dia), (date(2026, 1, 30), date(2026, 2, 1)))
		self.assertEqual(services.fechas_vecinas('semana', dia), (date(2026, 1, 24), date(2026, 2, 7)))
		self.assertEqual(services.fechas_vecinas('mes', dia), (date(2025, 12, 1), date(2026, 2, 1)))

	def test_titulo_periodo(self):
		self.assertEqual(services.titulo_periodo('semana', date(2026, 5, 13)), '10 – 16 de mayo 2026')
		self.assertEqual(services.titulo_periodo('mes', date(2026, 5, 13)), 'Mayo 2026')

	def test_filtrar_programaciones(self):
		visita = self._programar()
		self.assertEqual(list(services.filtrar_programaciones({'escuela': self.escuela})), [visita])
		self.assertEqual(list(services.filtrar_programaciones({'q': 'agenda'})), [visita])
		self.assertEqual(list(services.filtrar_programaciones({'q': 'no existe'})), [])

	def test_cobertura_de_visita(self):
		cubren, cubierta = services.cobertura_de_visita(self._programar('manana'))
		self.assertEqual(list(cubren), [self.persona])
		self.assertTrue(cubierta)

		cubren, cubierta = services.cobertura_de_visita(self._programar('tarde'))
		self.assertFalse(cubierta)

	def test_resumen_convocatoria(self):
		self._programar('manana')
		self._programar('tarde')  # la persona solo trabaja en la mañana

		resumen = services.resumen_convocatoria(self.convocatoria, [self.persona], timezone.localdate())

		self.assertEqual(resumen['duracion'], 21)
		self.assertEqual(resumen['sin_cobertura'], 1)
		self.assertEqual(resumen['escuelas_visitadas'], 1)
		self.assertEqual(services.dias_asignados_por_persona(self.convocatoria), {self.persona.pk: 1})

	def test_reporte_agenda_por_alcance(self):
		manana = self._programar('manana')
		tarde = self._programar('tarde')
		fuera_de_la_semana = Programacion.objects.create(
			convocatoria=self.convocatoria, escuela=self.escuela, jornada='manana',
			fecha_programada=self.dia + timedelta(days=7),
		)

		def visitas(alcance, dia=self.dia):
			reporte = services.reporte_agenda(self.convocatoria, alcance, dia)
			return [p for dia in reporte['dias'] for p in dia['programaciones']]

		self.assertEqual(visitas('convocatoria'), [manana, tarde, fuera_de_la_semana])
		self.assertEqual(visitas('semana'), [manana, tarde])
		self.assertEqual(visitas('dia'), [manana, tarde])
		self.assertEqual(visitas('dia', self.dia + timedelta(days=1)), [])
		self.assertEqual(visitas('control'), [manana, tarde])
		control = services.reporte_agenda(self.convocatoria, 'control', self.dia)
		self.assertTrue(control['control'])
		self.assertEqual(control['personal_del_dia'], [self.persona])
		self.assertEqual(control['personal_del_dia'][0].jornada, 'Mañana')
		self.assertEqual(services.reporte_agenda(self.convocatoria, 'convocatoria', self.dia)['total'], 3)

	def test_estado_horario_y_horario_inicial(self):
		persona = services.con_estado_horario(list(services.filtrar_personas({'q': 'Luis'})))[0]
		# El horario de prueba empieza la próxima semana.
		self.assertEqual(persona.estado_horario, 'futuro')


		inicial = services.horario_inicial(self.persona)
		self.assertEqual((inicial['fecha_inicio'], inicial['fecha_fin']), (self.dia, self.dia))

	def test_filtrar_asistencias(self):
		otro = self._persona('Ana', 'Ruiz', 'tarde')
		justificada = Asistencia.objects.create(persona=self.persona, fecha=self.dia, estado='justificado', observacion='Cita médica')
		Asistencia.objects.create(persona=otro, fecha=self.dia, estado='presente')

		self.assertEqual(list(services.filtrar_asistencias({'estado': 'justificado'})), [justificada])
		self.assertEqual(list(services.filtrar_asistencias({'persona': self.persona})), [justificada])
		self.assertEqual(services.filtrar_asistencias({'desde': self.dia + timedelta(days=1)}).count(), 0)

	def test_filtrar_convocatorias(self):
		otra = Convocatoria.objects.create(
			nombre='Otra', descripcion='Segunda ronda',
			fecha_inicio=self.dia + timedelta(days=30), fecha_fin=self.dia + timedelta(days=40),
		)
		self.assertEqual(list(services.filtrar_convocatorias('ronda')), [otra])
		self.assertEqual(list(services.filtrar_convocatorias(fecha_inicio=self.dia)), [otra])
		self.assertEqual(list(services.filtrar_convocatorias(fecha_fin=self.dia + timedelta(days=10))), [self.convocatoria])



class PersonalPlantaTests(AgendaBase):
	"""El personal de planta no tiene horario fijo: asignado a un día, cubre la jornada completa."""

	def setUp(self):
		super().setUp()
		self.contador = Personal.objects.create(
			tipo=Personal.Tipo.PLANTA, nombre='Rosa', apellido='Mejía', email='rosa.planta@example.com', cargo='Contador',
		)

	def test_validacion_de_cargo_e_institucion(self):
		with self.assertRaises(ValidationError):
			Personal(tipo=Personal.Tipo.PLANTA, nombre='Sin', apellido='Cargo', email='sin.cargo@example.com').full_clean()
		with self.assertRaises(ValidationError):
			Personal(tipo=Personal.Tipo.PRACTICANTE, nombre='Sin', apellido='Inst', email='sin.inst@example.com').full_clean()
		self.assertEqual(self.contador.detalle, 'Contador')
		self.assertEqual(self.persona.detalle, 'UES')

	def test_se_asigna_sin_horario_y_cubre_todo_el_dia(self):
		del_dia = PersonalDelDia(self.convocatoria, self.dia)
		_, disponibles = del_dia.opciones()
		self.assertIn(self.contador, [fila['persona'] for fila in disponibles])
		self.assertIsNone(del_dia.agregar(self.contador.pk))

		completa = self._programar('completa')
		calendario = self._agenda()
		for turno in ('manana', 'tarde'):
			with self.subTest(turno=turno):
				self.assertIn(self.contador, self._celda(calendario, turno)['cubren'])
		cubren, cubierta = services.cobertura_de_visita(completa)
		self.assertIn(self.contador, cubren)
		self.assertTrue(cubierta)

	def test_validacion_de_la_asignacion(self):
		# El practicante necesita horario ese día; el de planta no.
		otro_dia = self.dia + timedelta(days=1)
		ConvocatoriaPersonal(convocatoria=self.convocatoria, persona=self.contador, fecha=otro_dia).full_clean()
		with self.assertRaises(ValidationError):
			ConvocatoriaPersonal(convocatoria=self.convocatoria, persona=self.persona, fecha=otro_dia).full_clean()

	def test_no_se_le_toma_asistencia(self):
		hoy = timezone.localdate()
		self._asignar(self.contador, hoy)
		error = PersonalDelDia(self.convocatoria, hoy).registrar_inasistencia(self.contador.pk)
		self.assertIn('planta', error)
		with self.assertRaises(ValidationError):
			services.registrar_asistencia(self.contador.pk, hoy, 'presente')
		self.assertNotIn(self.contador, [fila['persona'] for fila in services.pase_de_lista(hoy)])

	def test_formulario_guarda_solo_el_dato_de_su_tipo(self):
		self.client.force_login(get_user_model().objects.create_superuser('planta', password='Clave-2026'))
		self.client.post(reverse('persona_nuevo'), {
			'tipo': 'planta', 'nombre': 'Mario', 'apellido': 'Cruz', 'email': 'mario.cruz@example.com',
			'cargo': 'Contador', 'institucion': 'UES',
		})
		mario = Personal.objects.get(email='mario.cruz@example.com')
		self.assertEqual((mario.tipo, mario.cargo, mario.institucion), ('planta', 'Contador', ''))

		respuesta = self.client.post(reverse('persona_nuevo'), {
			'tipo': 'planta', 'nombre': 'Ana', 'apellido': 'Sin', 'email': 'ana.sin@example.com',
		})
		self.assertIn('cargo', respuesta.context['form'].errors)

	def test_horario_solo_para_practicantes(self):
		self.client.force_login(get_user_model().objects.create_superuser('horario-planta', password='Clave-2026'))
		self.assertEqual(self.client.get(reverse('horario_editar', args=[self.contador.pk])).status_code, 404)


class DesactivarPersonalTests(AgendaBase):
	"""Al personal no se le elimina (se perdería su historial): se desactiva."""

	def setUp(self):
		super().setUp()
		self.client.force_login(get_user_model().objects.create_superuser('desactivar', password='Clave-2026'))
		self.hoy = timezone.localdate()
		# Además del horario de la próxima semana (AgendaBase), uno que ya empezó y sigue vigente.
		self.vigente = Horario.objects.create(
			persona=self.persona, dia=1, jornada='manana',
			fecha_inicio=self.hoy - timedelta(days=30), fecha_fin=self.hoy + timedelta(days=30),
		)
		self.asistencia = Asistencia.objects.create(persona=self.persona, fecha=self.hoy - timedelta(days=7), estado='presente')

	def _cambiar_estado(self):
		return self.client.post(reverse('persona_estado', args=[self.persona.pk]))

	def test_desactivar_conserva_el_historial(self):
		self.assertEqual(self._cambiar_estado().status_code, 200)
		self.persona.refresh_from_db()
		self.assertFalse(self.persona.activo)
		self.assertTrue(Asistencia.objects.filter(pk=self.asistencia.pk).exists())
		# El horario vigente termina hoy; el que empezaba después se quita, igual que la asignación futura.
		self.assertEqual(list(Horario.objects.filter(persona=self.persona)), [self.vigente])
		self.vigente.refresh_from_db()
		self.assertEqual(self.vigente.fecha_fin, self.hoy)
		self.assertFalse(self.convocatoria.asignaciones.filter(persona=self.persona).exists())

	def test_inactivo_no_se_lista_ni_se_asigna(self):
		self._cambiar_estado()
		self.persona.refresh_from_db()
		self.assertNotIn(self.persona, services.filtrar_personas({}))
		self.assertIn(self.persona, services.filtrar_personas({'estado': 'inactivos'}))
		self.assertIn('inactivo', PersonalDelDia(self.convocatoria, self.dia).agregar(self.persona.pk))
		self.assertEqual(self.client.get(reverse('horario_editar', args=[self.persona.pk])).status_code, 404)

	def test_se_puede_activar_de_nuevo(self):
		self._cambiar_estado()
		self._cambiar_estado()
		self.persona.refresh_from_db()
		self.assertTrue(self.persona.activo)
		self.assertIn(self.persona, services.filtrar_personas({}))


class AsistenciaTests(TestCase):
	"""Pase de lista de los practicantes según su horario."""

	def setUp(self):
		self.hoy = timezone.localdate()
		self.client.force_login(get_user_model().objects.create_superuser('asistencia', password='Clave-2026'))

		def practicante(nombre, jornada='manana'):
			persona = Personal.objects.create(nombre=nombre, apellido='Prueba', email=f'{nombre.lower()}.asis@example.com', institucion='UES')
			Horario.objects.create(
				persona=persona, dia=self.hoy.isoweekday(), jornada=jornada,
				fecha_inicio=self.hoy - timedelta(days=30), fecha_fin=self.hoy + timedelta(days=30),
			)
			return persona

		self.ana = practicante('Ana')
		self.beto = practicante('Beto', 'tarde')
		# Sin horario hoy: no aparece en el pase de lista.
		Personal.objects.create(nombre='Ciro', apellido='Prueba', email='ciro.asis@example.com', institucion='UES')

	def _registrar(self, persona, estado, fecha=None, **extra):
		"""Registra la asistencia como lo hace el pase de lista (extra: observación)."""
		return self.client.post(reverse('asistencia_registrar'), {
			'persona': persona.pk, 'fecha': (fecha or self.hoy).isoformat(), 'estado': estado, **extra,
		})

	def test_pase_de_lista_del_dia(self):
		respuesta = self.client.get(reverse('home_asistencia'))
		self.assertEqual(respuesta.status_code, 200)
		self.assertEqual([fila['persona'] for fila in respuesta.context['filas']], [self.ana, self.beto])
		self.assertEqual(respuesta.context['filas'][1]['jornadas'], ['Tarde'])
		self.assertEqual(respuesta.context['resumen']['pendientes'], 2)

	def test_registrar_cambiar_y_quitar(self):
		respuesta = self._registrar(self.ana, 'tarde', observacion='Llegó 8:20')
		self.assertEqual(respuesta.context['resumen']['tarde'], 1)
		asistencia = Asistencia.objects.get(persona=self.ana, fecha=self.hoy)
		self.assertEqual((asistencia.estado, asistencia.observacion), ('tarde', 'Llegó 8:20'))

		self._registrar(self.ana, 'presente')
		self.assertEqual(Asistencia.objects.get(persona=self.ana, fecha=self.hoy).estado, 'presente')
		self.assertEqual(Asistencia.objects.count(), 1)  # una por día

		self.client.post(reverse('asistencia_quitar'), {'persona': self.ana.pk, 'fecha': self.hoy.isoformat()})
		self.assertFalse(Asistencia.objects.exists())

	def test_aviso_al_registrar_por_htmx(self):
		respuesta = self.client.post(
			reverse('asistencia_registrar'),
			{'persona': self.ana.pk, 'fecha': self.hoy.isoformat(), 'estado': 'ausente'},
			HTTP_HX_REQUEST='true',
		)
		self.assertEqual(json.loads(respuesta['HX-Trigger'])['aviso']['avisos'][0]['texto'], 'Ana Prueba: ausente.')

	def test_marcar_pendientes_como_presentes(self):
		self._registrar(self.beto, 'ausente')
		self.client.post(reverse('asistencia_todos_presentes'), {'fecha': self.hoy.isoformat()})
		estados = dict(Asistencia.objects.values_list('persona__nombre', 'estado'))
		self.assertEqual(estados, {'Ana': 'presente', 'Beto': 'ausente'})  # no pisa lo ya registrado

	def test_dia_futuro_solo_permisos(self):
		manana = self.hoy + timedelta(days=7)  # mismo día de la semana: tiene horario
		respuesta = self._registrar(self.ana, 'presente', manana)
		self.assertIn('adelantado', respuesta.context['error'])
		self._registrar(self.ana, 'justificado', manana, observacion='Examen')
		self.assertEqual(Asistencia.objects.get(fecha=manana).estado, 'justificado')

		respuesta = self.client.post(reverse('asistencia_todos_presentes'), {'fecha': manana.isoformat()})
		self.assertIn('aún no llega', respuesta.context['error'])

	def test_ausente_o_justificado_no_cubre_ni_se_asigna(self):
		convocatoria = Convocatoria.objects.create(
			nombre='Ronda', descripcion='', fecha_inicio=self.hoy, fecha_fin=self.hoy + timedelta(days=10),
		)
		ConvocatoriaPersonal.objects.create(convocatoria=convocatoria, persona=self.ana, fecha=self.hoy)
		escuela = Escuela.objects.create(
			codigo='ASI-1', nombre='Escuela asistencia', nombre_corto='Asistencia',
			distrito=Distrito.objects.create(nombre='Distrito asistencia'),
		)
		visita = Programacion.objects.create(convocatoria=convocatoria, escuela=escuela, fecha_programada=self.hoy, jornada='manana')
		self.assertEqual(services.cobertura_de_visita(visita)[0], [self.ana])

		self._registrar(self.ana, 'tarde')
		self.assertEqual(services.cobertura_de_visita(visita)[0], [self.ana])  # llegó tarde, pero llegó

		self._registrar(self.ana, 'justificado')
		self.assertEqual(services.cobertura_de_visita(visita)[0], [])
		self._registrar(self.beto, 'ausente')
		self.assertIn('«ausente»', PersonalDelDia(convocatoria, self.hoy).agregar(self.beto.pk))

	def test_historial_resumen_e_imprimir(self):
		ayer = self.hoy - timedelta(days=7)
		Asistencia.objects.create(persona=self.ana, fecha=ayer, estado='presente')
		Asistencia.objects.create(persona=self.ana, fecha=self.hoy, estado='ausente')
		Asistencia.objects.create(persona=self.beto, fecha=self.hoy, estado='justificado')

		resumen = {fila['persona'].nombre: fila for fila in services.resumen_por_practicante(Asistencia.objects.all())}
		self.assertEqual(resumen['Ana']['porcentaje'], 50)
		self.assertIsNone(resumen['Beto']['porcentaje'])  # solo justificados: no hay días esperados

		respuesta = self.client.get(reverse('home_asistencia'), {'vista': 'historial', 'persona': self.ana.pk})
		self.assertEqual(respuesta.context['asistencias'].paginator.count, 2)
		respuesta = self.client.get(reverse('buscar_asistencias'), {'estado': 'justificado'})
		self.assertEqual([a.persona for a in respuesta.context['asistencias']], [self.beto])

		pdf = self.client.get(reverse('asistencia_imprimir'))
		self.assertEqual(pdf['Content-Type'], 'application/pdf')

	def test_dias_sin_pase_de_lista(self):
		hace_una_semana = self.hoy - timedelta(days=7)
		Asistencia.objects.create(persona=self.ana, fecha=hace_una_semana, estado='presente')

		pendientes = dict(services.dias_sin_pase_de_lista(self.hoy, dias=14))
		self.assertEqual(pendientes[self.hoy], 2)
		self.assertEqual(pendientes[hace_una_semana], 1)  # faltó Beto

		services.marcar_pendientes_presentes(self.hoy)
		self.assertNotIn(self.hoy, dict(services.dias_sin_pase_de_lista(self.hoy, dias=14)))

	def test_permisos(self):
		usuario = get_user_model().objects.create_user('solo_ver', password='Clave-2026')
		usuario.user_permissions.add(Permission.objects.get(codename='view_asistencia'))
		self.client.force_login(usuario)
		self.assertEqual(self.client.get(reverse('home_asistencia')).status_code, 200)
		self.assertEqual(self._registrar(self.ana, 'presente').status_code, 403)
