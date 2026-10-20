"""Lógica de negocio de liquidación: asignaciones, recibos, abonos, observaciones,
bonos y la carga de documentos Excel.

Las funciones de este módulo no reciben el request: trabajan con datos ya
validados (el cleaned_data de los formularios), con modelos y con archivos.
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import DecimalField, F, Prefetch, Q, Sum
from django.db.models.functions import Coalesce
from django.utils.text import slugify

from escuela.models import Encargado, Escuela
from .models import ESTADO_LIQUIDACION_CHOICES, Abono, Asignacion, Bono, Recibo
from .utils import a_decimal, a_entero, a_texto_codigo, extraer_anio, indice_columna, indices_columna, leer_filas_excel

CERO = Decimal('0')
EXTENSIONES_EXCEL = ('.xlsx', '.xls')
ERROR_FORMATO_EXCEL = 'Selecciona un archivo con formato .xlsx o .xls.'
ERROR_LECTURA_EXCEL = 'No se pudo leer el archivo. Verifica que no esté dañado.'


# ===================== Estado de liquidación =====================

def estado_liquidacion(recibos):
    """Calcula el estado de liquidación de una asignación según las observaciones de sus recibos."""
    observaciones = [obs for recibo in recibos for obs in recibo.observacion_set.all()]
    if not observaciones:
        return 'pendiente_revision'
    if all(obs.resuelta for obs in observaciones):
        return 'liquidado'
    return 'liquidado_con_observaciones'


def asignar_estado_liquidacion(asignaciones):
    for asignacion in asignaciones:
        asignacion.estado_liquidacion = estado_liquidacion(list(asignacion.recibo_set.all()))
    return asignaciones


# ===================== Asignaciones =====================

def filtrar_asignaciones(filtros):
    """Asignaciones filtradas con su total recibido y diferencia. SIN paginar.

    Si se filtra por estado se devuelve una lista (el estado no es un campo de BD).
    """
    asignaciones = Asignacion.objects.select_related('escuela', 'bono').prefetch_related(
        Prefetch(
            'escuela__encargado_set',
            queryset=Encargado.objects.filter(estado=True),
            to_attr='encargados_activos',
        ),
        'recibo_set__observacion_set',
    ).annotate(
        total_recibido=Coalesce(
            Sum('recibo__monto'), CERO,
            output_field=DecimalField(max_digits=10, decimal_places=2),
        )
    ).annotate(
        diferencia=F('valor') - F('total_recibido')
    ).order_by(
        'escuela__nombre_corto', 'bono__nombre'
    )

    distrito = filtros.get('distrito')
    escuela = filtros.get('escuela')
    bono = filtros.get('bono')
    anio = filtros.get('anio')
    estado = filtros.get('estado')

    if distrito:
        asignaciones = asignaciones.filter(escuela__distrito=distrito)
    if escuela:
        asignaciones = asignaciones.filter(escuela=escuela)
    if bono:
        asignaciones = asignaciones.filter(bono=bono)
    if anio:
        asignaciones = asignaciones.filter(bono__anio=anio)
    if estado:
        # El estado se calcula a partir de las observaciones (no es un campo de BD),
        # así que hay que evaluar el queryset y filtrar en Python.
        asignaciones = [
            asignacion for asignacion in asignaciones
            if estado_liquidacion(list(asignacion.recibo_set.all())) == estado
        ]

    return asignaciones


def asignaciones_con_encargados(con_telefonos=False):
    """Queryset de asignaciones con escuela, bono y encargados activos de la escuela."""
    encargados = Encargado.objects.filter(estado=True)
    if con_telefonos:
        encargados = encargados.order_by('apellido', 'nombre').prefetch_related('telefonos')
    return Asignacion.objects.select_related('escuela__distrito', 'bono').prefetch_related(
        Prefetch('escuela__encargado_set', queryset=encargados, to_attr='encargados_activos'),
    )


def _con_abonos(recibo):
    """Agrega al recibo sus abonos, lo abonado, la diferencia y sus observaciones."""
    abonos = list(recibo.abono_set.all())
    recibo.abonos_lista = abonos
    recibo.total_abonado = sum((abono.monto for abono in abonos), CERO)
    recibo.diferencia = recibo.monto - recibo.total_abonado
    recibo.observaciones_lista = list(recibo.observacion_set.all())
    return recibo


def recibos_con_abonos(asignacion):
    """Recibos de la asignación con sus abonos y observaciones (para el detalle)."""
    recibos = asignacion.recibo_set.order_by('id').prefetch_related('abono_set', 'observacion_set')
    return [_con_abonos(recibo) for recibo in recibos]


def gestion_asignacion(asignacion, recibo_seleccionado=None):
    """Recibos numerados con abonos, observaciones y estado; el recibo a mostrar y los totales."""
    recibos = recibos_con_abonos(asignacion)
    for numero, recibo in enumerate(recibos, start=1):
        recibo.posicion = numero
        recibo.estado_liquidacion = estado_liquidacion([recibo])
    total_recibido = sum((recibo.monto for recibo in recibos), CERO)

    # Solo se muestra un recibo a la vez: el pedido, o el primero
    recibo_actual = next(
        (r for r in recibos if str(r.pk) == str(recibo_seleccionado)),
        recibos[0] if recibos else None,
    )
    return {
        'recibos': recibos,
        'recibo_actual': recibo_actual,
        'total_recibido': total_recibido,
        'diferencia': asignacion.valor - total_recibido,
    }


def reporte_asignacion(asignacion):
    """Datos del PDF de liquidación de una asignación."""
    recibos = list(asignacion.recibo_set.order_by('id').prefetch_related('observacion_set'))

    etiquetas_estado = dict(ESTADO_LIQUIDACION_CHOICES)
    for recibo in recibos:
        recibo.observaciones_lista = list(recibo.observacion_set.all())
        recibo.estado_liquidacion = estado_liquidacion([recibo])
        recibo.estado_etiqueta = etiquetas_estado[recibo.estado_liquidacion]
    total_recibido = sum((recibo.monto for recibo in recibos), CERO)
    estado = estado_liquidacion(recibos)

    return {
        'instance': asignacion,
        'escuela': asignacion.escuela,
        'recibos': recibos,
        'total_recibido': total_recibido,
        'diferencia': asignacion.valor - total_recibido,
        'estado_liquidacion': estado,
        'estado_etiqueta': etiquetas_estado[estado],
        'nombre_reporte': f"{asignacion.escuela.codigo}_{slugify(asignacion.bono.nombre)}",
    }


def resumen_abonos(recibo):
    abonos = list(recibo.abono_set.order_by('id'))
    total_abonado = sum((abono.monto for abono in abonos), CERO)
    return {
        'abonos': abonos,
        'total_abonado': total_abonado,
        'diferencia': recibo.monto - total_abonado,
    }


def alternar_observacion(observacion):
    observacion.resuelta = not observacion.resuelta
    observacion.save()
    return observacion


# ===================== Bonos =====================

def filtrar_bonos(search='', anio=''):
    """Bonos filtrados por texto (nombre, descripción o id del sistema) y año. SIN paginar."""
    bonos = Bono.objects.all().order_by('-anio', 'nombre')
    if search:
        filtro = Q(nombre__icontains=search) | Q(descripcion__icontains=search)
        if search.isdigit():
            filtro |= Q(id_sistema=int(search))
        bonos = bonos.filter(filtro)
    if anio.isdigit():
        bonos = bonos.filter(anio=int(anio))
    return bonos


def anios_bonos():
    return Bono.objects.order_by('-anio').values_list('anio', flat=True).distinct()


# ===================== Carga de Excel =====================

def es_archivo_excel(archivo):
    return bool(archivo) and archivo.name.lower().endswith(EXTENSIONES_EXCEL)


def previsualizar_bonos(archivo):
    """Lee el Excel de bonos y devuelve {'bonos': [...]} con los que trae, o {'error': ...}."""
    if not es_archivo_excel(archivo):
        return {'error': ERROR_FORMATO_EXCEL}
    try:
        encabezados, filas = leer_filas_excel(archivo)
    except Exception:
        return {'error': ERROR_LECTURA_EXCEL}

    col_id = indice_columna(encabezados, 'id_bono')
    col_nombre = indice_columna(encabezados, 'nombre_bono')
    if col_id is None or col_nombre is None:
        return {'error': 'El archivo debe tener las columnas "id_bono" y "nombre_bono" en la primera fila.'}

    vistos = {}
    for fila in filas:
        if col_id >= len(fila) or col_nombre >= len(fila):
            continue

        id_bono = a_entero(fila[col_id])
        nombre_bono = fila[col_nombre]
        nombre_bono = str(nombre_bono).strip() if nombre_bono not in (None, '') else ''

        if id_bono is None or not nombre_bono:
            continue

        vistos.setdefault(id_bono, nombre_bono)

    nombres_existentes = set(Bono.objects.values_list('nombre', flat=True))
    ids_existentes = set(
        Bono.objects.exclude(id_sistema=None).values_list('id_sistema', flat=True)
    )

    return {'bonos': [
        {
            'id_bono': id_bono,
            'nombre_bono': nombre_bono,
            'anio': extraer_anio(nombre_bono),
            'ya_existe': id_bono in ids_existentes or nombre_bono in nombres_existentes,
        }
        for id_bono, nombre_bono in vistos.items()
    ]}


def importar_bonos(seleccionados):
    """Crea los bonos elegidos en la vista previa.

    seleccionados: pares (id_bono, nombre_bono) tal como vienen del formulario.
    Se ignoran los que no tienen id, nombre o año; se omiten los que ya existen.
    Devuelve (creados, omitidos).
    """
    creados = 0
    omitidos = 0
    for id_valor, nombre_valor in seleccionados:
        id_bono = a_entero(id_valor)
        nombre_bono = (nombre_valor or '').strip()
        anio = extraer_anio(nombre_bono)

        if id_bono is None or not nombre_bono or anio is None:
            continue

        if Bono.objects.filter(Q(nombre=nombre_bono) | Q(id_sistema=id_bono)).exists():
            omitidos += 1
            continue

        Bono.objects.create(nombre=nombre_bono, id_sistema=id_bono, anio=anio)
        creados += 1

    return creados, omitidos


def _columnas_reporte_recibos(encabezados):
    """Ubica las columnas del reporte transferido por recibo.

    "monto" aparece dos veces en el archivo: la primera es el monto del
    recibo y la última es el monto del abono de esa fila.
    """
    montos = indices_columna(encabezados, 'monto')
    indices = {
        'codigo_entidad': indice_columna(encabezados, 'codigo_entidad'),
        'id_bono': indice_columna(encabezados, 'id_bono'),
        'monto_asignado': indice_columna(encabezados, 'monto_asignado'),
        'no_requerimiento': indice_columna(encabezados, 'no_requerimiento'),
        'estado_trans': indice_columna(encabezados, 'estado_trans'),
        'id_planilla_parcial': indice_columna(encabezados, 'id_planilla_parcial'),
    }

    if any(valor is None for valor in indices.values()) or len(montos) < 2:
        return None

    indices['monto_recibo'] = montos[0]
    indices['monto_abono'] = montos[-1]
    return indices


@transaction.atomic
def procesar_reporte_recibos(archivo):
    """Importa el reporte de transferencias: crea asignaciones, recibos y abonos que falten.

    Devuelve {'contadores': {...}} con lo creado/omitido, o {'error': ...}.
    Todo ocurre en una transacción: si algo falla no queda una carga a medias.
    """
    if not es_archivo_excel(archivo):
        return {'error': ERROR_FORMATO_EXCEL}
    try:
        encabezados, filas = leer_filas_excel(archivo)
    except Exception:
        return {'error': ERROR_LECTURA_EXCEL}

    indices = _columnas_reporte_recibos(encabezados)
    if indices is None:
        return {
            'error': (
                'El archivo debe tener las columnas "codigo_entidad", "id_bono", '
                '"monto_asignado", "no_requerimiento", "estado_trans", '
                '"id_planilla_parcial" y dos columnas "monto" (una para el recibo '
                'y otra para el abono).'
            )
        }

    escuelas = {str(e.codigo).strip(): e for e in Escuela.objects.all()}
    bonos = {b.id_sistema: b for b in Bono.objects.exclude(id_sistema=None)}

    asignaciones_cache = {}
    recibos_cache = {}
    abonos_por_recibo = {}
    maximo_indice = max(indices.values())

    contadores = {
        'asignaciones_creadas': 0,
        'asignaciones_existentes': 0,
        'recibos_creados': 0,
        'recibos_existentes': 0,
        'abonos_creados': 0,
        'abonos_existentes': 0,
        'filas_omitidas_escuela': 0,
        'filas_omitidas_bono': 0,
        'filas_omitidas_datos': 0,
    }

    for fila in filas:
        if not fila or all(valor in (None, '') for valor in fila):
            continue
        if len(fila) <= maximo_indice:
            contadores['filas_omitidas_datos'] += 1
            continue

        escuela = escuelas.get(a_texto_codigo(fila[indices['codigo_entidad']]))
        if escuela is None:
            contadores['filas_omitidas_escuela'] += 1
            continue

        bono = bonos.get(a_entero(fila[indices['id_bono']]))
        if bono is None:
            contadores['filas_omitidas_bono'] += 1
            continue

        monto_recibo = a_decimal(fila[indices['monto_recibo']])
        monto_abono = a_decimal(fila[indices['monto_abono']])
        estado = a_entero(fila[indices['estado_trans']])
        requerimiento_val = fila[indices['no_requerimiento']]
        requerimiento = str(requerimiento_val).strip() if requerimiento_val not in (None, '') else ''
        id_planilla_parcial = a_entero(fila[indices['id_planilla_parcial']])

        if (
            monto_recibo is None
            or monto_abono is None
            or estado is None
            or not requerimiento
            or id_planilla_parcial is None
        ):
            contadores['filas_omitidas_datos'] += 1
            continue

        clave_asignacion = (escuela.id, bono.id)
        if clave_asignacion not in asignaciones_cache:
            asignacion = Asignacion.objects.filter(escuela=escuela, bono=bono).first()
            if asignacion is None:
                valor = a_decimal(fila[indices['monto_asignado']]) or CERO
                asignacion = Asignacion.objects.create(escuela=escuela, bono=bono, valor=valor)
                contadores['asignaciones_creadas'] += 1
            else:
                contadores['asignaciones_existentes'] += 1
            asignaciones_cache[clave_asignacion] = asignacion
        asignacion = asignaciones_cache[clave_asignacion]

        clave_recibo = (clave_asignacion, monto_recibo)
        if clave_recibo not in recibos_cache:
            recibo = Recibo.objects.filter(asignacion=asignacion, monto=monto_recibo).first()
            if recibo is None:
                recibo = Recibo.objects.create(asignacion=asignacion, monto=monto_recibo)
                contadores['recibos_creados'] += 1
            else:
                contadores['recibos_existentes'] += 1
            recibos_cache[clave_recibo] = recibo
        recibo = recibos_cache[clave_recibo]

        if recibo.id not in abonos_por_recibo:
            abonos_por_recibo[recibo.id] = set(
                Abono.objects.filter(recibo=recibo).values_list('id_planilla_parcial', flat=True)
            )

        if id_planilla_parcial in abonos_por_recibo[recibo.id]:
            contadores['abonos_existentes'] += 1
            continue

        Abono.objects.create(
            recibo=recibo,
            monto=monto_abono,
            requerimiento=requerimiento,
            estado=estado,
            id_planilla_parcial=id_planilla_parcial,
        )
        abonos_por_recibo[recibo.id].add(id_planilla_parcial)
        contadores['abonos_creados'] += 1

    return {'contadores': contadores}
