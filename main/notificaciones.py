"""Notificaciones: pendientes que el sistema detecta a partir de los datos.

No se guardan en la base de datos: se calculan cada vez, así que desaparecen solas
cuando se resuelve lo que las provoca (ej: al registrar el CDE nuevo de la escuela).

Cada fuente es una función que recibe la fecha de hoy y devuelve una lista de
Notificacion. Para agregar una nueva (ej: asistencia de auxiliares sin registrar),
se escribe la función y se agrega a FUENTES con el permiso que exige.
"""
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlencode

from django.db.models import Count, Max
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format

from escuela.models import CDE, Escuela
from escuela.services import DIAS_POR_VENCER, anotar_vigencia
from programacion.models import Programacion

# Orden de importancia: lo urgente primero.
NIVELES = ('error', 'warning', 'info')
# Días hacia atrás en que se avisa de cada día con visitas sin resultado; lo anterior se agrupa.
DIAS_VISITAS_RECIENTES = 30
FORMATO_FECHA = 'j \\d\\e F \\d\\e Y'
FORMATO_DIA = 'j \\d\\e F'


@dataclass
class Notificacion:
    categoria: str
    nivel: str          # 'error' (urgente), 'warning' (atención) o 'info'
    titulo: str
    detalle: str
    url: str
    urgencia: int = 0   # A mayor número, más arriba dentro de su nivel


def _fecha(valor):
    return date_format(valor, FORMATO_FECHA)


def _plural(cantidad, singular, plural):
    return f'{cantidad} {singular if cantidad == 1 else plural}'


# ---------------------------------------------------------------------------
# Fuentes
# ---------------------------------------------------------------------------

def cde_por_vencer_y_vencidos(hoy):
    """Escuelas activas cuyo CDE está por vencer o ya venció y que aún no tienen el siguiente."""
    cdes = anotar_vigencia(CDE.objects.filter(escuela__estado=True)).select_related('escuela')
    # Una escuela con un periodo vigente o por empezar ya renovó su CDE.
    renovadas = set(cdes.filter(vigencia__in=('vigente', 'proximo')).values_list('escuela', flat=True))
    notificaciones = []

    for cde in cdes.filter(vigencia='por_vencer').exclude(escuela__in=renovadas).order_by('FechaFin'):
        dias = (cde.FechaFin - hoy).days
        notificaciones.append(Notificacion(
            categoria='CDE',
            nivel='warning',
            titulo=f'El CDE de {cde.escuela.nombre_corto} está por vencer',
            detalle=f"Vence {'hoy' if dias == 0 else 'en ' + _plural(dias, 'día', 'días')}, el {_fecha(cde.FechaFin)}.",
            url=reverse('escuela_gestionar', args=[cde.escuela_id]),
            urgencia=DIAS_POR_VENCER - dias,
        ))

    con_cde_en_curso = renovadas | set(cdes.filter(vigencia='por_vencer').values_list('escuela', flat=True))
    vencidos = cdes.filter(vigencia='vencido').exclude(escuela__in=con_cde_en_curso).values('escuela').annotate(fin=Max('FechaFin'))
    escuelas = Escuela.objects.in_bulk([fila['escuela'] for fila in vencidos])
    for fila in sorted(vencidos, key=lambda fila: fila['fin'], reverse=True):
        escuela = escuelas[fila['escuela']]
        dias = (hoy - fila['fin']).days
        notificaciones.append(Notificacion(
            categoria='CDE',
            nivel='error',
            titulo=f'El CDE de {escuela.nombre_corto} está vencido',
            detalle=f"Venció el {_fecha(fila['fin'])} (hace {_plural(dias, 'día', 'días')}) y no tiene uno nuevo registrado.",
            url=reverse('escuela_gestionar', args=[escuela.pk]),
            # Lo que acaba de vencer va primero: es lo que más probablemente se olvidó.
            urgencia=-dias,
        ))
    return notificaciones


def escuelas_sin_cde(hoy):
    """Escuelas activas que nunca han tenido un CDE registrado (un solo aviso agrupado)."""
    total = Escuela.objects.filter(estado=True, cde__isnull=True).count()
    if not total:
        return []
    return [Notificacion(
        categoria='CDE',
        nivel='info',
        titulo=f"{_plural(total, 'escuela activa no tiene', 'escuelas activas no tienen')} CDE registrado",
        detalle='Aparecen en el resumen del listado de CDE, en "Escuelas sin CDE en curso".',
        url=reverse('home_cde'),
    )]


def escuelas_sin_encargado(hoy):
    """Escuelas activas sin encargado activo (un solo aviso agrupado)."""
    total = Escuela.objects.filter(estado=True).exclude(encargado__estado=True).count()
    if not total:
        return []
    return [Notificacion(
        categoria='Escuelas',
        nivel='info',
        titulo=f"{_plural(total, 'escuela activa no tiene', 'escuelas activas no tienen')} encargado activo",
        detalle='Asígnales un encargado desde la página de cada escuela.',
        url=f"{reverse('home_escuelas')}?{urlencode({'estado': '1'})}",
    )]


def visitas_sin_resultado(hoy):
    """Visitas de días pasados que siguen "pendientes": no se registró si se completaron."""
    pendientes = Programacion.objects.filter(estado='pendiente', fecha_programada__lt=hoy)
    limite = hoy - timedelta(days=DIAS_VISITAS_RECIENTES)
    notificaciones = []

    por_dia = pendientes.filter(fecha_programada__gte=limite).values(
        'convocatoria', 'convocatoria__nombre', 'fecha_programada',
    ).annotate(total=Count('id')).order_by('-fecha_programada')
    for fila in por_dia:
        fecha = fila['fecha_programada']
        notificaciones.append(Notificacion(
            categoria='Programación',
            nivel='warning',
            titulo=f"{_plural(fila['total'], 'visita sin resultado', 'visitas sin resultado')} del {date_format(fecha, FORMATO_DIA)}",
            detalle=f"{fila['convocatoria__nombre']}: marca si cada visita se completó o no.",
            url=f"{reverse('home_programacion')}?{urlencode({'convocatoria': fila['convocatoria'], 'modo': 'dia', 'fecha': fecha.isoformat()})}",
            urgencia=-(hoy - fecha).days,
        ))

    antiguas = pendientes.filter(fecha_programada__lt=limite).count()
    if antiguas:
        notificaciones.append(Notificacion(
            categoria='Programación',
            nivel='info',
            titulo=f"{_plural(antiguas, 'visita antigua sigue', 'visitas antiguas siguen')} pendiente{'' if antiguas == 1 else 's'}",
            detalle=f'Son de hace más de {DIAS_VISITAS_RECIENTES} días y no tienen su resultado registrado.',
            url=f"{reverse('home_programacion')}?{urlencode({'seccion': 'programaciones', 'q': 'pendiente'})}",
        ))
    return notificaciones


# (permiso que exige, fuente). Cada usuario solo ve las de los módulos que puede ver.
FUENTES = [
    ('escuela.view_cde', cde_por_vencer_y_vencidos),
    ('escuela.view_cde', escuelas_sin_cde),
    ('escuela.view_escuela', escuelas_sin_encargado),
    ('programacion.view_programacion', visitas_sin_resultado),
]


def notificaciones_de(usuario, hoy=None):
    """Notificaciones que le corresponden al usuario, de la más urgente a la menos."""
    hoy = hoy or timezone.localdate()
    notificaciones = [
        notificacion
        for permiso, fuente in FUENTES if usuario.has_perm(permiso)
        for notificacion in fuente(hoy)
    ]
    return sorted(notificaciones, key=lambda n: (NIVELES.index(n.nivel), -n.urgencia))


def agrupar_por_categoria(notificaciones):
    """[(categoria, [notificaciones...]), ...] respetando el orden de urgencia."""
    grupos = {}
    for notificacion in notificaciones:
        grupos.setdefault(notificacion.categoria, []).append(notificacion)
    return list(grupos.items())
