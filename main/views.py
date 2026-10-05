from datetime import timedelta
from decimal import Decimal

from django.shortcuts import render
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Count, DecimalField, F, Q, Sum
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone
from easyaudit.models import CRUDEvent
from escuela.models import Encargado, Escuela
from liquidacion.models import ESTADO_LIQUIDACION_CHOICES, Asignacion, Bono, Observacion, Recibo
from programacion.models import Ausencia, Convocatoria, Programacion
from django.contrib import messages

CERO = Decimal('0')
# SQLite opera los decimales como flotantes: una asignación saldada puede quedar en -1E-12.
MEDIO_CENTAVO = Decimal('0.005')
APPS_AUDITADAS = ['escuela', 'liquidacion', 'programacion']
ACCIONES_AUDITORIA = {
    CRUDEvent.CREATE: 'creó',
    CRUDEvent.UPDATE: 'actualizó',
    CRUDEvent.DELETE: 'eliminó',
}


def _porcentaje(parte, total):
    if not total:
        return 0
    return round(float(parte) / float(total) * 100, 1)


def _resumen_liquidacion(asignaciones, recibos):
    """Totales de monto asignado/recibido y conteo de asignaciones por estado."""
    asignado = asignaciones.aggregate(total=Sum('valor'))['total'] or CERO
    recibido = recibos.aggregate(total=Sum('monto'))['total'] or CERO

    # Mismo criterio que liquidacion.views._estado_liquidacion, pero agregado en BD.
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
            'porcentaje': _porcentaje(por_estado[clave], total_asignaciones),
        }
        for clave, nombre in ESTADO_LIQUIDACION_CHOICES
    ]

    return {
        'asignado': asignado,
        'recibido': recibido,
        'pendiente': asignado - recibido,
        'porcentaje_recibido': _porcentaje(recibido, asignado),
        'total_asignaciones': total_asignaciones,
        'total_escuelas': asignaciones.values('escuela').distinct().count(),
        'estados': estados,
    }


def _avance_por(asignaciones, recibos, campo_id, campo_nombre):
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
        fila['porcentaje'] = _porcentaje(fila['recibido'], fila['asignado'])

    return sorted(filas.values(), key=lambda fila: fila['asignado'], reverse=True)


def _actividad_reciente(limite=8, ventana=timedelta(minutes=5)):
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


@login_required(login_url='login')
def home_view(request):
    hoy = timezone.localdate()

    # Filtro de año: por defecto el año de bonos más reciente; "todos" quita el filtro.
    anios = list(Bono.objects.order_by('-anio').values_list('anio', flat=True).distinct())
    anio_param = request.GET.get('anio')
    if anio_param == 'todos':
        anio = None
    elif anio_param and anio_param.isdigit() and int(anio_param) in anios:
        anio = int(anio_param)
    else:
        anio = anios[0] if anios else None

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

    escuelas_activas = Escuela.objects.filter(estado=True)
    convocatoria_vigente = Convocatoria.objects.filter(
        fecha_inicio__lte=hoy, fecha_fin__gte=hoy,
    ).order_by('fecha_fin').first()

    contexto = {
        'breadcrumbs': [{'name': 'Inicio', 'url': reverse('home')}],
        'hoy': hoy,
        'anios': anios,
        'anio': anio,
        'resumen': _resumen_liquidacion(asignaciones, recibos),
        'avance_bonos': _avance_por(asignaciones, recibos, 'bono_id', 'bono__nombre'),
        'avance_distritos': _avance_por(
            asignaciones, recibos, 'escuela__distrito_id', 'escuela__distrito__nombre',
        ),
        'mayores_saldos': asignaciones_con_saldo.filter(diferencia__gt=MEDIO_CENTAVO).order_by('-diferencia')[:6],
        'con_saldo': asignaciones_con_saldo.filter(diferencia__gt=MEDIO_CENTAVO).count(),
        'observaciones_abiertas': observaciones.select_related(
            'recibo__asignacion__escuela', 'recibo__asignacion__bono',
        ).order_by('fecha_creacion')[:5],
        'total_observaciones_abiertas': observaciones.count(),
        'atencion': {
            'sobrepagadas': asignaciones_con_saldo.filter(diferencia__lt=-MEDIO_CENTAVO).annotate(
                excedente=F('total_recibido') - F('valor'),
            ).order_by('diferencia')[:5],
            'total_sobrepagadas': asignaciones_con_saldo.filter(diferencia__lt=-MEDIO_CENTAVO).count(),
            'escuelas_sin_encargado': escuelas_activas.exclude(encargado__estado=True).count(),
            'encargados_sin_telefono': Encargado.objects.filter(estado=True, telefonos__isnull=True).count(),
            'escuelas_sin_asignacion': escuelas_activas.exclude(
                pk__in=asignaciones.values('escuela'),
            ).count(),
        },
        'programaciones_hoy': Programacion.objects.filter(fecha_programada=hoy).select_related(
            'auxiliar', 'escuela',
        ).order_by('hora_programada'),
        'programaciones_semana': Programacion.objects.filter(
            fecha_programada__gt=hoy, fecha_programada__lte=hoy + timedelta(days=7), estado='pendiente',
        ).count(),
        'ausencias_hoy': Ausencia.objects.filter(fecha=hoy).select_related('auxiliar'),
        'convocatoria_vigente': convocatoria_vigente,
        'proxima_convocatoria': None if convocatoria_vigente else Convocatoria.objects.filter(
            fecha_inicio__gt=hoy,
        ).order_by('fecha_inicio').first(),
        'actividad': _actividad_reciente(),
    }

    if convocatoria_vigente:
        duracion = (convocatoria_vigente.fecha_fin - convocatoria_vigente.fecha_inicio).days + 1
        transcurridos = (hoy - convocatoria_vigente.fecha_inicio).days + 1
        contexto['convocatoria_avance'] = _porcentaje(transcurridos, duracion)
        contexto['convocatoria_dias_restantes'] = (convocatoria_vigente.fecha_fin - hoy).days

    return render(request, 'home.html', contexto)

def login_view(request):
    if request.user.is_authenticated:
        return redirect("home")  # change to your home url name

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect("home")  # change to your home url name
        else:
            messages.error(request, "Invalid username or password.")

    return render(request, "registration/login.html")


def logout_view(request):
    logout(request)
    messages.success(request, "Has cerrado sesión correctamente.")
    return redirect("login")