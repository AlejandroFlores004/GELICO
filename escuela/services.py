"""Lógica de negocio de escuelas, encargados y CDE.

Las funciones de este módulo no reciben el request: trabajan con datos ya
validados (el cleaned_data de los formularios) y con modelos.
"""
from datetime import timedelta

from django.db import transaction
from django.db.models import Case, CharField, Count, IntegerField, Prefetch, Q, Value, When
from django.utils import timezone

from .models import CDE, Encargado, Escuela


# ===================== Encargados =====================

def filtrar_encargados(filtros):
    encargados = Encargado.objects.select_related(
        'escuela', 'escuela__distrito'
    ).prefetch_related('telefonos').order_by('escuela__nombre_corto', '-estado', 'apellido')

    distrito = filtros.get('distrito')
    escuela = filtros.get('escuela')
    estado = filtros.get('estado')
    texto = filtros.get('texto')

    if distrito:
        encargados = encargados.filter(escuela__distrito=distrito)
    if escuela:
        encargados = encargados.filter(escuela=escuela)
    if estado:
        encargados = encargados.filter(estado=(estado == '1'))
    if texto:
        encargados = encargados.filter(
            Q(nombre__icontains=texto) |
            Q(apellido__icontains=texto) |
            Q(email__icontains=texto)
        )
    return encargados


def _desactivar_otros_encargados(encargado):
    """Una escuela tiene un solo encargado activo: desactiva a los demás."""
    Encargado.objects.filter(
        escuela=encargado.escuela, estado=True
    ).exclude(pk=encargado.pk).update(estado=False)


@transaction.atomic
def guardar_encargado(form, formset):
    """Guarda el encargado con sus teléfonos. Si es nuevo y queda activo,
    pasa a ser el único encargado activo de su escuela."""
    es_nuevo = form.instance.pk is None
    encargado = form.save()
    formset.instance = encargado  # Necesario en la creación
    formset.save()
    if es_nuevo and encargado.estado:
        _desactivar_otros_encargados(encargado)
    return encargado


@transaction.atomic
def cambiar_encargado(activo, form, formset):
    """Registra al nuevo encargado de la escuela y deja inactivo al anterior."""
    encargado = form.save()
    formset.instance = encargado
    formset.save()
    activo.estado = False
    activo.save()
    return encargado


@transaction.atomic
def alternar_estado_encargado(encargado):
    encargado.estado = not encargado.estado
    encargado.save()
    if encargado.estado:
        _desactivar_otros_encargados(encargado)
    return encargado


def encargados_de_escuelas(escuelas, con_anteriores=False):
    """Encargados de las escuelas dadas (solo los activos, salvo con_anteriores)."""
    encargados = Encargado.objects.filter(
        escuela__in=escuelas
    ).select_related('escuela', 'escuela__distrito').prefetch_related(
        'telefonos'
    ).order_by('escuela__codigo', '-estado', 'apellido')
    if not con_anteriores:
        encargados = encargados.filter(estado=True)
    return encargados


# ===================== CDE =====================

# Un periodo "por vencer" es uno vigente al que le quedan estos días o menos
DIAS_POR_VENCER = 60
VIGENCIAS_EN_CURSO = ('vigente', 'por_vencer')

# Criterios de orden del listado de CDE: clave -> (etiqueta, campos order_by)
ORDENES_CDE = {
    'vigencia': ('Vigencia', ['orden_vigencia', 'FechaFin', 'escuela__codigo']),
    'codigo': ('Código de escuela', ['escuela__codigo', 'FechaInicio']),
    'escuela': ('Nombre de escuela', ['escuela__nombre_corto', 'FechaInicio']),
    'distrito': ('Distrito', ['escuela__distrito__nombre', 'escuela__codigo', 'FechaInicio']),
    'inicio': ('Fecha de inicio', ['FechaInicio', 'escuela__codigo']),
    'fin': ('Fecha de fin', ['FechaFin', 'escuela__codigo']),
}
ORDEN_CDE_DEFECTO = 'vigencia'


def anotar_vigencia(cdes):
    """Agrega a cada CDE su vigencia calculada con la fecha de hoy:
    vencido, por_vencer, vigente o proximo (todavía no inicia)."""
    hoy = timezone.localdate()
    limite = hoy + timedelta(days=DIAS_POR_VENCER)
    return cdes.annotate(
        vigencia=Case(
            When(FechaFin__lt=hoy, then=Value('vencido')),
            When(FechaInicio__gt=hoy, then=Value('proximo')),
            When(FechaFin__lte=limite, then=Value('por_vencer')),
            default=Value('vigente'),
            output_field=CharField(),
        ),
        # Para ordenar por urgencia: primero lo vencido, al final lo que aún no inicia
        orden_vigencia=Case(
            When(FechaFin__lt=hoy, then=Value(0)),
            When(FechaInicio__gt=hoy, then=Value(3)),
            When(FechaFin__lte=limite, then=Value(1)),
            default=Value(2),
            output_field=IntegerField(),
        ),
    )


def _cdes_en_curso():
    return anotar_vigencia(CDE.objects.all()).filter(vigencia__in=VIGENCIAS_EN_CURSO)


def leer_orden_cdes(orden):
    """Interpreta el parámetro de orden (ej. 'fin' o '-fin'). Devuelve (clave, descendente)."""
    orden = orden or ''
    descendente = orden.startswith('-')
    clave = orden.lstrip('-')
    if clave not in ORDENES_CDE:
        return ORDEN_CDE_DEFECTO, False
    return clave, descendente


def filtrar_cdes(filtros, clave_orden=ORDEN_CDE_DEFECTO, descendente=False):
    """Devuelve (cdes_sin_filtro_de_vigencia, cdes_finales).
    El primero sirve para el resumen; el segundo, ya ordenado, para listar e imprimir."""
    cdes = anotar_vigencia(CDE.objects.select_related('escuela', 'escuela__distrito'))

    distrito = filtros.get('distrito')
    escuela = filtros.get('escuela')
    search = (filtros.get('q') or '').strip()
    fecha_inicio = filtros.get('fecha_inicio')
    fecha_fin = filtros.get('fecha_fin')
    vigencia = filtros.get('vigencia')

    if distrito:
        cdes = cdes.filter(escuela__distrito=distrito)
    if escuela:
        cdes = cdes.filter(escuela=escuela)
    if search:
        cdes = cdes.filter(
            Q(escuela__nombre__icontains=search) |
            Q(escuela__codigo__icontains=search) |
            Q(escuela__nombre_corto__icontains=search) |
            Q(escuela__distrito__nombre__icontains=search)
        )
    if fecha_inicio:
        cdes = cdes.filter(FechaInicio__gte=fecha_inicio)
    if fecha_fin:
        cdes = cdes.filter(FechaFin__lte=fecha_fin)

    sin_vigencia = cdes
    if vigencia:
        cdes = cdes.filter(vigencia=vigencia)

    campos = ORDENES_CDE[clave_orden][1]
    if descendente:
        campos = [c[1:] if c.startswith('-') else f'-{c}' for c in campos]

    return sin_vigencia, cdes.order_by(*campos)


def resumen_cdes(filtros, cdes):
    """Conteo por vigencia (respetando los demás filtros) y escuelas activas
    que hoy no tienen un CDE en curso."""
    conteo = dict(
        cdes.order_by().values_list('vigencia').annotate(total=Count('pk'))
    )

    escuelas = Escuela.objects.filter(estado=True).select_related('distrito')
    if filtros.get('distrito'):
        escuelas = escuelas.filter(distrito=filtros['distrito'])
    if filtros.get('escuela'):
        escuelas = escuelas.filter(pk=filtros['escuela'].pk)

    return {
        'vigente': conteo.get('vigente', 0),
        'por_vencer': conteo.get('por_vencer', 0),
        'vencido': conteo.get('vencido', 0),
        'proximo': conteo.get('proximo', 0),
        'escuelas_sin_cde': list(escuelas.exclude(pk__in=_cdes_en_curso().values('escuela')).order_by('codigo')),
        'dias_por_vencer': DIAS_POR_VENCER,
    }


def con_dias(cdes):
    """Agrega a cada CDE los días que le faltan y el % transcurrido del periodo."""
    hoy = timezone.localdate()
    for cde in cdes:
        cde.dias_para_fin = (cde.FechaFin - hoy).days
        cde.dias_vencido = (hoy - cde.FechaFin).days
        cde.dias_para_inicio = (cde.FechaInicio - hoy).days
        total = max((cde.FechaFin - cde.FechaInicio).days, 1)
        transcurrido = (hoy - cde.FechaInicio).days
        cde.avance = min(max(round(transcurrido * 100 / total), 0), 100)
    return cdes


def cdes_de_escuelas(escuelas):
    """CDE (con vigencia y días) de varias escuelas, para el reporte."""
    cdes = anotar_vigencia(CDE.objects.filter(
        escuela__in=escuelas
    )).select_related('escuela', 'escuela__distrito').order_by('escuela__codigo', '-FechaInicio')
    return con_dias(list(cdes))


# ===================== Escuelas =====================

def filtrar_escuelas(filtros):
    escuelas = Escuela.objects.select_related('distrito').order_by('codigo')

    escuela = filtros.get('escuela')
    distrito = filtros.get('distrito')
    estado = filtros.get('estado')

    if escuela:
        escuelas = escuelas.filter(pk=escuela.pk)
    if distrito:
        escuelas = escuelas.filter(distrito=distrito)
    if estado:
        escuelas = escuelas.filter(estado=(estado == '1'))
    return escuelas


def con_encargado_y_cde(escuelas):
    """Encargado activo (con sus teléfonos) y CDE en curso de cada escuela, sin N+1."""
    return escuelas.prefetch_related(
        Prefetch(
            'encargado_set',
            queryset=Encargado.objects.filter(estado=True).prefetch_related('telefonos'),
            to_attr='encargados_activos',
        ),
        Prefetch(
            'cde_set',
            queryset=_cdes_en_curso().order_by('-FechaInicio'),
            to_attr='cdes_activos',
        ),
    )


def ficha_escuela(escuela):
    """Encargado activo, anteriores y periodos de CDE de una escuela.
    Lo usan la página "Gestionar" y la ficha en PDF."""
    encargados = list(
        escuela.encargado_set.prefetch_related('telefonos').order_by('-estado', '-pk')
    )
    # Del más reciente al más antiguo, con su vigencia y días calculados
    cdes = con_dias(list(
        anotar_vigencia(escuela.cde_set.all()).order_by('-FechaInicio')
    ))
    return {
        'encargado_activo': next((e for e in encargados if e.estado), None),
        'encargados_anteriores': [e for e in encargados if not e.estado],
        'cdes': cdes,
        # El CDE en curso (vigente o por vencer); el resto queda en el historial
        'cde_actual': next((c for c in cdes if c.vigencia in VIGENCIAS_EN_CURSO), None),
    }


def alternar_estado_escuela(escuela):
    escuela.estado = not escuela.estado
    escuela.save()
    return escuela
