"""Lógica de negocio de programación: visitas, personal, horarios, asistencia y convocatorias.

El cálculo de la agenda por jornadas (cobertura, turnos, colores) vive en agenda.py;
este módulo lo usa para armar resúmenes y reportes. Las funciones no reciben el
request: trabajan con datos ya validados y con modelos.
"""
from collections import defaultdict
from datetime import timedelta

from django.db.models import Count, Exists, OuterRef, Prefetch, Q
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.text import capfirst

from .agenda import Agenda, estado_convocatoria, rango_visible, resumen_estados, sumar_meses
from .models import ORDEN_JORNADA, Asistencia, Convocatoria, ConvocatoriaPersonal, Horario, Jornada, Personal, Programacion

FORMATO_DIA = 'l j \\d\\e F \\d\\e Y'
FORMATO_FECHA = 'j \\d\\e F Y'
ALCANCES_IMPRESION = ('convocatoria', 'semana', 'dia', 'persona', 'sin_cobertura', 'pendientes')


def titulo_periodo(modo, dia):
    if modo == 'dia':
        return capfirst(date_format(dia, FORMATO_DIA))
    if modo == 'mes':
        return capfirst(date_format(dia, 'F Y'))
    inicio, fin = rango_visible('semana', dia)
    if inicio.month == fin.month:
        return f"{inicio.day} – {fin.day} de {date_format(fin, 'F Y')}"
    if inicio.year == fin.year:
        return f"{inicio.day} de {date_format(inicio, 'F')} – {fin.day} de {date_format(fin, 'F Y')}"
    return f"{date_format(inicio, FORMATO_FECHA)} – {date_format(fin, FORMATO_FECHA)}"


def fechas_vecinas(modo, dia):
    """Día que se muestra al ir al periodo anterior y al siguiente."""
    if modo == 'mes':
        return sumar_meses(dia, -1), sumar_meses(dia, 1)
    paso = timedelta(weeks=1) if modo == 'semana' else timedelta(days=1)
    return dia - paso, dia + paso


# ---------------------------------------------------------------------------
# Programaciones (visitas)
# ---------------------------------------------------------------------------

def filtrar_programaciones(filtros):
    programaciones = Programacion.objects.select_related(
        'convocatoria', 'escuela'
    ).order_by('-fecha_programada', ORDEN_JORNADA.desc())

    search = (filtros.get('q') or '').strip()
    convocatoria = filtros.get('convocatoria')
    escuela = filtros.get('escuela')

    if convocatoria:
        programaciones = programaciones.filter(convocatoria=convocatoria)
    if escuela:
        programaciones = programaciones.filter(escuela=escuela)
    if search:
        programaciones = programaciones.filter(
            Q(convocatoria__nombre__icontains=search)
            | Q(escuela__nombre__icontains=search)
            | Q(escuela__nombre_corto__icontains=search)
            | Q(estado__icontains=search)
        )
    return programaciones


def cobertura_de_visita(programacion):
    """(personas que cubren la visita, si queda cubierta)."""
    cobertura = Agenda(programacion.convocatoria, programacion.fecha_programada, programacion.fecha_programada, con_visitas=False)
    return cobertura.cubren_visita(programacion), cobertura.visita_cubierta(programacion)


def resumen_convocatoria(convocatoria, personas, hoy):
    """Indicadores de la convocatoria que acompañan a su agenda."""
    programaciones = convocatoria.programacion_set.all()
    # Cobertura de todo el periodo, para el contador de visitas que ninguna persona cubre.
    periodo = Agenda(convocatoria, convocatoria.fecha_inicio, convocatoria.fecha_fin, personas)
    return {
        'estado_convocatoria': estado_convocatoria(convocatoria, hoy),
        'duracion': (convocatoria.fecha_fin - convocatoria.fecha_inicio).days + 1,
        'dias_restantes': (convocatoria.fecha_fin - hoy).days,
        'estados': resumen_estados(programaciones),
        'sin_cobertura': sum(not programacion.cubierta for programacion in periodo.programaciones),
        'escuelas_visitadas': programaciones.values('escuela').distinct().count(),
    }


def dias_asignados_por_persona(convocatoria):
    """{persona_id: cantidad de días asignados} en la convocatoria."""
    return dict(
        convocatoria.asignaciones.values('persona').annotate(dias=Count('fecha')).values_list('persona', 'dias')
    )


def reporte_agenda(convocatoria, alcance, dia, persona=None):
    """Datos del PDF de la agenda según el alcance: toda la convocatoria, una semana, un día,
    la hoja de ruta de una persona, las visitas sin cobertura o las pendientes."""
    programaciones = convocatoria.programacion_set.select_related(
        'escuela__distrito',
    ).order_by('fecha_programada', ORDEN_JORNADA, 'escuela__nombre')
    inicio, fin = convocatoria.fecha_inicio, convocatoria.fecha_fin
    subtitulo = f"Del {date_format(inicio, FORMATO_FECHA)} al {date_format(fin, FORMATO_FECHA)}"

    if alcance == 'semana':
        semana_inicio, semana_fin = rango_visible('semana', dia)
        # La semana se recorta al periodo de la convocatoria.
        inicio, fin = max(semana_inicio, inicio), min(semana_fin, fin)
        subtitulo = f"Semana: {titulo_periodo('semana', dia)}"
    elif alcance == 'dia':
        inicio = fin = dia
        subtitulo = capfirst(date_format(dia, FORMATO_DIA))
    elif alcance == 'persona' and persona:
        subtitulo = f"Hoja de ruta de {persona.nombre} {persona.apellido}"
    elif alcance == 'sin_cobertura':
        subtitulo = 'Visitas que ninguna persona cubre'
    elif alcance == 'pendientes':
        programaciones = programaciones.filter(estado='pendiente')
        subtitulo = 'Visitas pendientes'
    programaciones = list(programaciones.filter(fecha_programada__range=(inicio, fin)))

    # Quién cubre cada visita: las personas asignadas a su día cuyo horario incluye su jornada.
    cobertura = Agenda(convocatoria, inicio, fin, con_visitas=False)
    for programacion in programaciones:
        programacion.cubren = cobertura.cubren_visita(programacion)
        programacion.cubierta = cobertura.visita_cubierta(programacion)
    if alcance == 'persona' and persona:
        # Hoja de ruta: las visitas de las jornadas en que trabaja.
        programaciones = [programacion for programacion in programaciones if persona in programacion.cubren]
    elif alcance == 'sin_cobertura':
        programaciones = [programacion for programacion in programaciones if not programacion.cubierta]

    por_dia = defaultdict(list)
    for programacion in programaciones:
        programacion.bloque = programacion.get_jornada_display()
        por_dia[programacion.fecha_programada].append(programacion)

    return {
        'convocatoria': convocatoria,
        'alcance': alcance,
        'subtitulo': subtitulo,
        'persona': persona if alcance == 'persona' else None,
        'dias': [{'fecha': fecha, 'programaciones': lista} for fecha, lista in sorted(por_dia.items())],
        'total': len(programaciones),
        'estados': resumen_estados(programaciones),
        # La hoja de ruta lleva columnas para llenar a mano en campo.
        'para_campo': alcance in ('persona', 'dia'),
    }


# ---------------------------------------------------------------------------
# Personal y horarios
# ---------------------------------------------------------------------------

def filtrar_personas(filtros):
    """Personal filtrados por texto, institución, horario y convocatoria. SIN paginar."""
    personas = Personal.objects.prefetch_related(
        Prefetch(
            'horario_set',
            queryset=Horario.objects.order_by('dia', ORDEN_JORNADA, 'fecha_inicio'),
            to_attr='horarios',
        ),
    ).order_by('apellido', 'nombre')
    if not filtros:
        return personas

    hoy = timezone.localdate()
    fecha, dia, jornada = filtros.get('fecha'), filtros.get('dia'), filtros.get('jornada')

    texto = (filtros.get('q') or '').strip()
    if texto:
        personas = personas.filter(
            Q(nombre__icontains=texto) | Q(apellido__icontains=texto) | Q(email__icontains=texto)
            | Q(telefono__icontains=texto) | Q(institucion__icontains=texto) | Q(cargo__icontains=texto)
        )
    if filtros.get('tipo'):
        personas = personas.filter(tipo=filtros['tipo'])
    if filtros.get('institucion'):
        personas = personas.filter(institucion=filtros['institucion'])

    # Horarios de la persona que cumplen la fecha, el día y la jornada pedidos.
    horarios = Horario.objects.filter(persona=OuterRef('pk'))
    if fecha:
        horarios = horarios.del_dia(fecha)
    if dia:
        horarios = horarios.filter(dia=dia)
    if jornada:
        # Quien trabaja todo el día también trabaja en la mañana y en la tarde.
        horarios = horarios.filter(jornada__in=[jornada] if jornada == Jornada.COMPLETA else [jornada, Jornada.COMPLETA])
    # Elegir fecha, día o jornada sin decir nada del horario se entiende como "trabaja entonces".
    estado = filtros.get('horario') or ('con' if fecha or dia or jornada else '')
    if estado == 'con':
        personas = personas.filter(Exists(horarios))
    elif estado == 'sin':
        personas = personas.filter(~Exists(horarios))
    elif estado == 'vigente':
        personas = personas.filter(Exists(horarios.filter(fecha_inicio__lte=hoy, fecha_fin__gte=hoy)))
    elif estado == 'vencido':
        personas = personas.filter(Exists(horarios)).exclude(Exists(horarios.filter(fecha_fin__gte=hoy)))

    # Con fecha, las asignaciones se miran solo ese día.
    if filtros.get('convocatoria'):
        asignaciones = ConvocatoriaPersonal.objects.filter(persona=OuterRef('pk'), convocatoria=filtros['convocatoria'])
        if fecha:
            asignaciones = asignaciones.filter(fecha=fecha)
        personas = personas.filter(Exists(asignaciones))

    return personas


def cargos_existentes():
    """Cargos ya usados por el personal de planta, para sugerirlos al escribir uno nuevo."""
    return list(
        Personal.objects.filter(tipo=Personal.Tipo.PLANTA).exclude(cargo='').order_by('cargo').values_list('cargo', flat=True).distinct()
    )


def con_estado_horario(personas):
    """Marca cada practicante según su horario: sin horario, vigente hoy, por empezar o vencido.
    El personal de planta no tiene horario fijo ('no_aplica')."""
    hoy = timezone.localdate()
    for persona in personas:
        if not persona.es_practicante:
            persona.estado_horario = 'no_aplica'
        elif not persona.horarios:
            persona.estado_horario = 'sin'
        elif any(h.fecha_inicio <= hoy <= h.fecha_fin for h in persona.horarios):
            persona.estado_horario = 'vigente'
        elif any(h.fecha_inicio > hoy for h in persona.horarios):
            persona.estado_horario = 'futuro'
        else:
            persona.estado_horario = 'vencido'
    return personas


def horario_inicial(persona_id):
    """Valores con que se abre un horario nuevo. Lo usual es agregar más días al mismo
    periodo de labores: se propone el del último horario de la persona."""
    inicial = {'persona': persona_id}
    ultimo = Horario.objects.filter(persona_id=persona_id).order_by('-fecha_fin').first() if persona_id else None
    if ultimo:
        inicial.update(fecha_inicio=ultimo.fecha_inicio, fecha_fin=ultimo.fecha_fin)
    return inicial


# ---------------------------------------------------------------------------
# Asistencia (solo practicantes)
# ---------------------------------------------------------------------------

def registrar_asistencia(persona_id, fecha, estado, observacion='', validar=True):
    """Crea o cambia la asistencia del practicante ese día (hay una por día).

    Con validar=True revisa las reglas del modelo (que sea practicante, que tenga horario ese día,
    que por adelantado solo se registre "justificado") y lanza ValidationError si no se cumplen.
    """
    asistencia = Asistencia.objects.filter(persona_id=persona_id, fecha=fecha).first() or Asistencia(persona_id=persona_id, fecha=fecha)
    asistencia.estado = estado
    asistencia.observacion = (observacion or '').strip()
    if validar:
        asistencia.full_clean(validate_unique=False)
    asistencia.save()
    return asistencia


def quitar_asistencia(persona_id, fecha):
    """Deja el día "sin registrar". delete() por objeto para que la auditoría registre la baja."""
    for asistencia in Asistencia.objects.filter(persona_id=persona_id, fecha=fecha):
        asistencia.delete()


def pase_de_lista(fecha):
    """Practicantes que trabajan ese día según su horario, con su asistencia (o None si falta
    registrarla), sus jornadas y las convocatorias a las que están asignados ese día."""
    horarios = Horario.objects.del_dia(fecha).filter(persona__tipo=Personal.Tipo.PRACTICANTE).select_related('persona')
    jornadas = defaultdict(list)
    for horario in sorted(horarios, key=lambda horario: Jornada.values.index(horario.jornada)):
        jornadas[horario.persona_id].append(horario.get_jornada_display())

    asistencias = {asistencia.persona_id: asistencia for asistencia in Asistencia.objects.filter(fecha=fecha, persona__in=jornadas)}
    convocatorias = defaultdict(list)
    for asignacion in ConvocatoriaPersonal.objects.filter(fecha=fecha, persona__in=jornadas).select_related('convocatoria'):
        convocatorias[asignacion.persona_id].append(asignacion.convocatoria)

    personas = Personal.objects.filter(pk__in=jornadas).order_by('apellido', 'nombre')
    return [
        {
            'persona': persona,
            'jornadas': jornadas[persona.pk],
            'asistencia': asistencias.get(persona.pk),
            'convocatorias': convocatorias[persona.pk],
        }
        for persona in personas
    ]


def resumen_pase_de_lista(filas):
    """Cuántos hay en cada estado y cuántos faltan por registrar."""
    resumen = {estado: 0 for estado in Asistencia.Estado.values}
    for fila in filas:
        if fila['asistencia']:
            resumen[fila['asistencia'].estado] += 1
    resumen['total'] = len(filas)
    resumen['pendientes'] = sum(1 for fila in filas if fila['asistencia'] is None)
    resumen['registrados'] = resumen['total'] - resumen['pendientes']
    return resumen


def marcar_pendientes_presentes(fecha):
    """Marca como presentes a los practicantes de ese día que aún no tienen asistencia. Devuelve cuántos."""
    pendientes = [fila['persona'] for fila in pase_de_lista(fecha) if fila['asistencia'] is None]
    for persona in pendientes:
        registrar_asistencia(persona.pk, fecha, Asistencia.Estado.PRESENTE, validar=False)
    return len(pendientes)


def dias_sin_pase_de_lista(hasta, dias=14):
    """Días (de los últimos `dias`, hasta la fecha dada inclusive) en que algún practicante que
    trabajaba según su horario no tiene la asistencia registrada: [(fecha, pendientes)], recientes primero."""
    resultado = []
    for atras in range(dias):
        fecha = hasta - timedelta(days=atras)
        con_horario = set(
            Horario.objects.del_dia(fecha).filter(persona__tipo=Personal.Tipo.PRACTICANTE).values_list('persona_id', flat=True)
        )
        if not con_horario:
            continue
        registrados = set(Asistencia.objects.filter(fecha=fecha, persona__in=con_horario).values_list('persona_id', flat=True))
        pendientes = len(con_horario - registrados)
        if pendientes:
            resultado.append((fecha, pendientes))
    return resultado


def filtrar_asistencias(filtros):
    """Historial de asistencia por practicante, rango de fechas y estado. SIN paginar."""
    asistencias = Asistencia.objects.select_related('persona').order_by('-fecha', 'persona__apellido', 'persona__nombre')
    if filtros.get('persona'):
        asistencias = asistencias.filter(persona=filtros['persona'])
    if filtros.get('desde'):
        asistencias = asistencias.filter(fecha__gte=filtros['desde'])
    if filtros.get('hasta'):
        asistencias = asistencias.filter(fecha__lte=filtros['hasta'])
    if filtros.get('estado'):
        asistencias = asistencias.filter(estado=filtros['estado'])
    return asistencias


def resumen_por_practicante(asistencias):
    """Por practicante: cuántos días en cada estado y el % de asistencia (presente o tarde sobre
    los días en que se esperaba que fuera; los justificados no cuentan en contra)."""
    filas = {}
    for persona_id, estado, total in asistencias.order_by().values_list('persona', 'estado').annotate(total=Count('id')):
        filas.setdefault(persona_id, {estado: 0 for estado in Asistencia.Estado.values})[estado] = total
    personas = Personal.objects.in_bulk(filas)
    resumen = []
    for persona_id, conteo in filas.items():
        asistio = conteo['presente'] + conteo['tarde']
        esperados = asistio + conteo['ausente']
        resumen.append({
            'persona': personas[persona_id],
            **conteo,
            'total': sum(conteo.values()),
            'porcentaje': round(asistio * 100 / esperados) if esperados else None,
        })
    return sorted(resumen, key=lambda fila: (fila['persona'].apellido, fila['persona'].nombre))


# ---------------------------------------------------------------------------
# Convocatorias
# ---------------------------------------------------------------------------

def filtrar_convocatorias(search='', fecha_inicio=None, fecha_fin=None):
    """Convocatorias por nombre/descripción y dentro del rango de fechas. SIN paginar."""
    convocatorias = Convocatoria.objects.all().order_by('fecha_inicio')
    if search:
        convocatorias = convocatorias.filter(Q(nombre__icontains=search) | Q(descripcion__icontains=search))
    if fecha_inicio:
        convocatorias = convocatorias.filter(fecha_inicio__gte=fecha_inicio)
    if fecha_fin:
        convocatorias = convocatorias.filter(fecha_fin__lte=fecha_fin)
    return convocatorias
