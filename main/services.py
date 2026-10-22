"""Lógica del panel de inicio y de la consulta de auditoría.

Las funciones de este módulo no reciben el request: trabajan con datos ya
validados (el cleaned_data de los formularios) y con modelos.
"""
import json
from datetime import timedelta, timezone as dt_timezone
from decimal import Decimal

from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models import Count, DecimalField, F, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.text import capfirst
from easyaudit.models import CRUDEvent, LoginEvent, RequestEvent

from escuela.models import Encargado, Escuela
from liquidacion.models import ESTADO_LIQUIDACION_CHOICES, Asignacion, Bono, Observacion, Recibo
from programacion.models import ORDEN_JORNADA, Asistencia, Convocatoria, Programacion
from .forms import NOMBRES_APPS

CERO = Decimal('0')
# SQLite opera los decimales como flotantes: una asignación saldada puede quedar en -1E-12.
MEDIO_CENTAVO = Decimal('0.005')
APPS_AUDITADAS = ['escuela', 'liquidacion', 'programacion']
ACCIONES_AUDITORIA = {
    CRUDEvent.CREATE: 'creó',
    CRUDEvent.UPDATE: 'actualizó',
    CRUDEvent.DELETE: 'eliminó',
}


def porcentaje(parte, total):
    if not total:
        return 0
    return round(float(parte) / float(total) * 100, 1)


# ---------------------------------------------------------------------------
# Panel de inicio
# ---------------------------------------------------------------------------

def anios_disponibles():
    return list(Bono.objects.order_by('-anio').values_list('anio', flat=True).distinct())


def elegir_anio(valor, anios):
    """Año del panel: por defecto el año de bonos más reciente; 'todos' quita el filtro (None)."""
    if valor == 'todos':
        return None
    if valor and valor.isdigit() and int(valor) in anios:
        return int(valor)
    return anios[0] if anios else None


def resumen_liquidacion(asignaciones, recibos):
    """Totales de monto asignado/recibido y conteo de asignaciones por estado."""
    asignado = asignaciones.aggregate(total=Sum('valor'))['total'] or CERO
    recibido = recibos.aggregate(total=Sum('monto'))['total'] or CERO

    # Mismo criterio que liquidacion.services.estado_liquidacion, pero agregado en BD.
    conteos = asignaciones.annotate(
        obs_total=Count('recibo__observacion'),
        obs_abiertas=Count('recibo__observacion', filter=Q(recibo__observacion__resuelta=False)),
    ).values_list('obs_total', 'obs_abiertas')

    por_estado = {clave: 0 for clave, _ in ESTADO_LIQUIDACION_CHOICES}
    for obs_total, obs_abiertas in conteos:
        if not obs_total:
            por_estado['pendiente_revision'] += 1
        elif not obs_abiertas:
            por_estado['liquidado'] += 1
        else:
            por_estado['liquidado_con_observaciones'] += 1

    total_asignaciones = sum(por_estado.values())
    estados = [
        {
            'clave': clave,
            'nombre': nombre,
            'cantidad': por_estado[clave],
            'porcentaje': porcentaje(por_estado[clave], total_asignaciones),
        }
        for clave, nombre in ESTADO_LIQUIDACION_CHOICES
    ]

    return {
        'asignado': asignado,
        'recibido': recibido,
        'pendiente': asignado - recibido,
        'porcentaje_recibido': porcentaje(recibido, asignado),
        'total_asignaciones': total_asignaciones,
        'total_escuelas': asignaciones.values('escuela').distinct().count(),
        'estados': estados,
    }


def avance_por(asignaciones, recibos, campo_id, campo_nombre):
    """Asignado vs. recibido agrupado por un campo (bono, distrito...).

    Se hacen dos consultas separadas porque sumar valor y recibos en el mismo
    JOIN duplicaría el valor de cada asignación por cada recibo que tenga.
    """
    filas = {
        fila[campo_id]: {
            'id': fila[campo_id],
            'nombre': fila[campo_nombre],
            'asignaciones': fila['asignaciones'],
            'asignado': fila['asignado'],
            'recibido': CERO,
        }
        for fila in asignaciones.values(campo_id, campo_nombre).annotate(
            asignaciones=Count('id'), asignado=Sum('valor'),
        )
    }
    for fila in recibos.values(f'asignacion__{campo_id}').annotate(recibido=Sum('monto')):
        if fila[f'asignacion__{campo_id}'] in filas:
            filas[fila[f'asignacion__{campo_id}']]['recibido'] = fila['recibido']

    for fila in filas.values():
        fila['pendiente'] = fila['asignado'] - fila['recibido']
        fila['porcentaje'] = porcentaje(fila['recibido'], fila['asignado'])

    return sorted(filas.values(), key=lambda fila: fila['asignado'], reverse=True)


def actividad_reciente(limite=8, ventana=timedelta(minutes=5)):
    """Últimos cambios auditados, agrupando ráfagas (p. ej. una carga de Excel) en una sola fila."""
    eventos = CRUDEvent.objects.filter(
        content_type__app_label__in=APPS_AUDITADAS,
        event_type__in=ACCIONES_AUDITORIA.keys(),
    ).select_related('content_type', 'user').order_by('-datetime')[:300]

    grupos = []
    for evento in eventos:
        ultimo = grupos[-1] if grupos else None
        if (
            ultimo
            and ultimo['clave'] == (evento.content_type_id, evento.event_type, evento.user_id)
            and ultimo['desde'] - evento.datetime <= ventana
        ):
            ultimo['cantidad'] += 1
            ultimo['desde'] = evento.datetime
            continue
        if len(grupos) == limite:
            break

        modelo = evento.content_type.model_class()
        grupos.append({
            'clave': (evento.content_type_id, evento.event_type, evento.user_id),
            'tipo': evento.event_type,
            'accion': ACCIONES_AUDITORIA[evento.event_type],
            'modelo': modelo._meta.verbose_name if modelo else evento.content_type.model,
            'modelo_plural': modelo._meta.verbose_name_plural if modelo else evento.content_type.model,
            'objeto': evento.object_repr,
            'usuario': (evento.user.get_full_name() or evento.user.username) if evento.user else 'Sistema',
            'fecha': evento.datetime,
            'desde': evento.datetime,
            'cantidad': 1,
        })

    return grupos


def panel_inicio(anio, hoy):
    """Todos los indicadores del panel de inicio para el año dado (None = todos los años)."""
    asignaciones = Asignacion.objects.all()
    recibos = Recibo.objects.all()
    observaciones = Observacion.objects.filter(resuelta=False)
    if anio:
        asignaciones = asignaciones.filter(bono__anio=anio)
        recibos = recibos.filter(asignacion__bono__anio=anio)
        observaciones = observaciones.filter(recibo__asignacion__bono__anio=anio)

    asignaciones_con_saldo = asignaciones.select_related('escuela', 'bono').annotate(
        total_recibido=Coalesce(
            Sum('recibo__monto'), CERO,
            output_field=DecimalField(max_digits=10, decimal_places=2),
        )
    ).annotate(diferencia=F('valor') - F('total_recibido'))
    con_saldo = asignaciones_con_saldo.filter(diferencia__gt=MEDIO_CENTAVO)
    sobrepagadas = asignaciones_con_saldo.filter(diferencia__lt=-MEDIO_CENTAVO)

    escuelas_activas = Escuela.objects.filter(estado=True)
    convocatoria_vigente = Convocatoria.objects.filter(
        fecha_inicio__lte=hoy, fecha_fin__gte=hoy,
    ).order_by('fecha_fin').first()

    panel = {
        'resumen': resumen_liquidacion(asignaciones, recibos),
        'avance_bonos': avance_por(asignaciones, recibos, 'bono_id', 'bono__nombre'),
        'avance_distritos': avance_por(
            asignaciones, recibos, 'escuela__distrito_id', 'escuela__distrito__nombre',
        ),
        'mayores_saldos': con_saldo.order_by('-diferencia')[:6],
        'con_saldo': con_saldo.count(),
        'observaciones_abiertas': observaciones.select_related(
            'recibo__asignacion__escuela', 'recibo__asignacion__bono',
        ).order_by('fecha_creacion')[:5],
        'total_observaciones_abiertas': observaciones.count(),
        'atencion': {
            'sobrepagadas': sobrepagadas.annotate(
                excedente=F('total_recibido') - F('valor'),
            ).order_by('diferencia')[:5],
            'total_sobrepagadas': sobrepagadas.count(),
            'escuelas_sin_encargado': escuelas_activas.exclude(encargado__estado=True).count(),
            'encargados_sin_telefono': Encargado.objects.filter(estado=True, telefonos__isnull=True).count(),
            'escuelas_sin_asignacion': escuelas_activas.exclude(
                pk__in=asignaciones.values('escuela'),
            ).count(),
        },
        'programaciones_hoy': Programacion.objects.filter(fecha_programada=hoy).select_related(
            'convocatoria', 'escuela',
        ).order_by(ORDEN_JORNADA, 'escuela__nombre'),
        'programaciones_semana': Programacion.objects.filter(
            fecha_programada__gt=hoy, fecha_programada__lte=hoy + timedelta(days=7), estado='pendiente',
        ).count(),
        'ausentes_hoy': Asistencia.objects.filter(fecha=hoy, estado__in=Asistencia.NO_TRABAJO).select_related('persona'),
        'convocatoria_vigente': convocatoria_vigente,
        'proxima_convocatoria': None if convocatoria_vigente else Convocatoria.objects.filter(
            fecha_inicio__gt=hoy,
        ).order_by('fecha_inicio').first(),
        'actividad': actividad_reciente(),
    }

    if convocatoria_vigente:
        duracion = (convocatoria_vigente.fecha_fin - convocatoria_vigente.fecha_inicio).days + 1
        transcurridos = (hoy - convocatoria_vigente.fecha_inicio).days + 1
        panel['convocatoria_avance'] = porcentaje(transcurridos, duracion)
        panel['convocatoria_dias_restantes'] = (convocatoria_vigente.fecha_fin - hoy).days

    return panel


# ---------------------------------------------------------------------------
# Auditoría: consulta de la bitácora que registra django-easy-audit.
# ---------------------------------------------------------------------------

ETIQUETAS_ACCION = {
    CRUDEvent.CREATE: 'Creación',
    CRUDEvent.UPDATE: 'Actualización',
    CRUDEvent.DELETE: 'Eliminación',
}
EVENTOS_ACCION = {
    'crear': [CRUDEvent.CREATE],
    'actualizar': [CRUDEvent.UPDATE],
    'eliminar': [CRUDEvent.DELETE],
    'relaciones': [tipo for tipo, _ in CRUDEvent.TYPES if tipo not in ETIQUETAS_ACCION],
}
ETIQUETAS_ACCESO = {
    LoginEvent.LOGIN: 'Inicio de sesión',
    LoginEvent.LOGOUT: 'Cierre de sesión',
    LoginEvent.FAILED: 'Intento fallido',
}
# easyaudit guarda el objeto completo, incluido el hash de la contraseña de los usuarios.
CAMPOS_SENSIBLES = {'password'}
TEXTO_OCULTO = '•••••••• (oculto)'


def _nombre_usuario(usuario, respaldo='Sistema'):
    if not usuario:
        return respaldo
    return usuario.get_full_name() or usuario.username


def _cargar_json(texto):
    if not texto:
        return None
    try:
        return json.loads(texto)
    except (TypeError, ValueError):
        return None


def _campo_modelo(modelo, nombre):
    if not modelo:
        return None
    try:
        return modelo._meta.get_field(nombre)
    except FieldDoesNotExist:
        return None


def _etiqueta_campo(modelo, nombre):
    campo = _campo_modelo(modelo, nombre)
    if campo is not None and hasattr(campo, 'verbose_name'):
        return capfirst(campo.verbose_name)
    return capfirst(nombre.replace('_', ' '))


def filtrar_auditoria(vista, filtros):
    """Eventos de la pestaña ('cambios', 'accesos' o 'solicitudes') filtrados. SIN paginar."""
    if vista == 'cambios':
        eventos = CRUDEvent.objects.select_related('content_type', 'user')
    elif vista == 'accesos':
        eventos = LoginEvent.objects.select_related('user')
    else:
        eventos = RequestEvent.objects.select_related('user')
    eventos = eventos.order_by('-datetime', '-id')

    if not filtros:
        return eventos

    q = (filtros.get('q') or '').strip()
    usuario = filtros.get('usuario')

    if usuario:
        if vista == 'accesos':
            # Los intentos fallidos no tienen usuario enlazado, solo el nombre escrito.
            eventos = eventos.filter(Q(user=usuario) | Q(username=usuario.username))
        else:
            eventos = eventos.filter(user=usuario)
    if filtros.get('desde'):
        eventos = eventos.filter(datetime__date__gte=filtros['desde'])
    if filtros.get('hasta'):
        eventos = eventos.filter(datetime__date__lte=filtros['hasta'])

    if vista == 'cambios':
        if q:
            eventos = eventos.filter(Q(object_repr__icontains=q) | Q(object_id=q))
        if filtros.get('modulo'):
            eventos = eventos.filter(content_type=filtros['modulo'])
        if filtros.get('accion'):
            eventos = eventos.filter(event_type__in=EVENTOS_ACCION[filtros['accion']])
    elif vista == 'accesos':
        if q:
            eventos = eventos.filter(Q(username__icontains=q) | Q(remote_ip__icontains=q))
        if filtros.get('tipo_acceso'):
            eventos = eventos.filter(login_type=int(filtros['tipo_acceso']))
    else:
        if q:
            eventos = eventos.filter(
                Q(url__icontains=q) | Q(query_string__icontains=q) | Q(remote_ip__icontains=q)
            )
        if filtros.get('metodo'):
            eventos = eventos.filter(method=filtros['metodo'])

    return eventos


def decorar_eventos(eventos, vista):
    """Agrega a cada evento los textos legibles que usan la tabla y el PDF."""
    for evento in eventos:
        if vista == 'cambios':
            modelo = evento.content_type.model_class()
            evento.usuario_nombre = _nombre_usuario(evento.user)
            evento.accion = ETIQUETAS_ACCION.get(evento.event_type, 'Cambio de relaciones')
            evento.app = NOMBRES_APPS.get(evento.content_type.app_label, evento.content_type.app_label.capitalize())
            evento.modulo = capfirst(modelo._meta.verbose_name) if modelo else evento.content_type.model
            cambios = _cargar_json(evento.changed_fields)
            evento.campos = [_etiqueta_campo(modelo, campo) for campo in cambios] if isinstance(cambios, dict) else []
        elif vista == 'accesos':
            evento.usuario_nombre = _nombre_usuario(evento.user, respaldo=evento.username or '—')
            evento.tipo = ETIQUETAS_ACCESO.get(evento.login_type, '—')
        else:
            evento.usuario_nombre = _nombre_usuario(evento.user, respaldo='Anónimo')
    return eventos


def indicadores_auditoria():
    hoy = timezone.localdate()
    solicitudes_hoy = RequestEvent.objects.filter(datetime__date=hoy)
    ultimo_acceso = LoginEvent.objects.filter(login_type=LoginEvent.LOGIN).select_related('user').order_by('-datetime').first()
    return {
        'cambios_hoy': CRUDEvent.objects.filter(datetime__date=hoy).count(),
        'cambios_semana': CRUDEvent.objects.filter(datetime__date__gte=hoy - timedelta(days=6)).count(),
        'accesos_hoy': LoginEvent.objects.filter(login_type=LoginEvent.LOGIN, datetime__date=hoy).count(),
        'ultimo_acceso': ultimo_acceso,
        'ultimo_acceso_usuario': _nombre_usuario(ultimo_acceso.user, ultimo_acceso.username) if ultimo_acceso else None,
        'fallidos_mes': LoginEvent.objects.filter(
            login_type=LoginEvent.FAILED, datetime__date__gte=hoy - timedelta(days=29),
        ).count(),
        'usuarios_activos_hoy': solicitudes_hoy.exclude(user=None).values('user').distinct().count(),
        'solicitudes_hoy': solicitudes_hoy.count(),
    }


def _formatear_fecha_hora(fecha):
    if timezone.is_naive(fecha):
        # Con USE_TZ las fechas se guardan en UTC; easyaudit a veces las serializa sin zona.
        fecha = timezone.make_aware(fecha, dt_timezone.utc)
    return timezone.localtime(fecha).strftime('%d/%m/%Y %I:%M %p')


def _valor_cambio(modelo, nombre, valor):
    """Valores de changed_fields: easyaudit los guarda como texto (str() del valor)."""
    if valor in (None, '', 'None'):
        return '—'
    if valor in ('True', 'False'):
        return 'Sí' if valor == 'True' else 'No'
    campo = _campo_modelo(modelo, nombre)
    if isinstance(campo, models.DateTimeField) and (fecha := parse_datetime(valor)):
        return _formatear_fecha_hora(fecha)
    if isinstance(campo, models.DateField) and (fecha := parse_date(valor[:10])):
        return fecha.strftime('%d/%m/%Y')
    if campo is not None and campo.choices:
        return dict(campo.flatchoices).get(valor, valor)
    return valor


def _valor_registro(modelo, nombre, valor):
    """Valores de object_json_repr (serialización de Django), mostrados de forma legible."""
    if nombre in CAMPOS_SENSIBLES:
        return TEXTO_OCULTO
    if valor in (None, ''):
        return '—'
    if isinstance(valor, bool):
        return 'Sí' if valor else 'No'

    campo = _campo_modelo(modelo, nombre)
    if campo is None:
        return ', '.join(map(str, valor)) if isinstance(valor, list) else valor
    if campo.many_to_many:
        relacionados = campo.related_model.objects.filter(pk__in=valor)
        return ', '.join(str(objeto) for objeto in relacionados) or '—'
    if campo.is_relation:
        objeto = campo.related_model.objects.filter(pk=valor).first()
        return str(objeto) if objeto else f'#{valor} (ya no existe)'
    if campo.choices:
        return dict(campo.flatchoices).get(valor, valor)
    if isinstance(campo, models.DateTimeField) and (fecha := parse_datetime(str(valor))):
        return _formatear_fecha_hora(fecha)
    if isinstance(campo, models.DateField) and (fecha := parse_date(str(valor))):
        return fecha.strftime('%d/%m/%Y')
    return valor


def detalle_cambio(evento):
    """Devuelve las filas a mostrar: el antes/después si hubo actualización, o la foto del registro."""
    modelo = evento.content_type.model_class()

    cambios = _cargar_json(evento.changed_fields)
    if isinstance(cambios, dict) and cambios:
        filas = []
        for nombre, valores in cambios.items():
            antes, despues = (list(valores) + [None, None])[:2] if isinstance(valores, list) else (None, valores)
            if nombre in CAMPOS_SENSIBLES:
                antes = despues = TEXTO_OCULTO
            filas.append({
                'campo': _etiqueta_campo(modelo, nombre),
                'antes': _valor_cambio(modelo, nombre, antes),
                'despues': _valor_cambio(modelo, nombre, despues),
            })
        return 'cambios', filas

    registro = _cargar_json(evento.object_json_repr)
    campos = registro[0].get('fields', {}) if isinstance(registro, list) and registro else {}
    filas = [
        {'campo': _etiqueta_campo(modelo, nombre), 'valor': _valor_registro(modelo, nombre, valor)}
        for nombre, valor in campos.items()
    ]
    return 'registro', filas


def historial_registro(evento):
    """Todos los cambios auditados del mismo registro que el evento, del más reciente al más antiguo."""
    return CRUDEvent.objects.filter(
        content_type=evento.content_type, object_id=evento.object_id,
    ).select_related('content_type', 'user').order_by('-datetime', '-id')
