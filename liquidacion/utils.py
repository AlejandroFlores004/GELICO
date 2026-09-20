from decimal import Decimal, InvalidOperation

import openpyxl
import xlrd


def leer_filas_excel(archivo):
    """Lee un archivo subido (.xlsx o .xls) y devuelve (encabezados, filas).

    encabezados: lista de strings, tomados de la primera fila.
    filas: lista de listas con el resto de las filas (una lista por fila).
    """
    nombre = archivo.name.lower()

    if nombre.endswith(".xlsx"):
        libro = openpyxl.load_workbook(archivo, data_only=True, read_only=True)
        hoja = libro.active
        filas_iter = hoja.iter_rows(values_only=True)
        encabezados = list(next(filas_iter, ()))
        filas = [list(fila) for fila in filas_iter]
    elif nombre.endswith(".xls"):
        libro = xlrd.open_workbook(file_contents=archivo.read())
        hoja = libro.sheet_by_index(0)
        encabezados = hoja.row_values(0) if hoja.nrows else []
        filas = [hoja.row_values(i) for i in range(1, hoja.nrows)]
    else:
        raise ValueError("Formato de archivo no soportado. Usa .xlsx o .xls")

    encabezados = [str(e).strip() if e is not None else "" for e in encabezados]
    return encabezados, filas


def normalizar_encabezado(texto):
    return str(texto).strip().lower().replace(" ", "_")


def indice_columna(encabezados, nombre_buscado):
    for i, encabezado in enumerate(encabezados):
        if normalizar_encabezado(encabezado) == nombre_buscado:
            return i
    return None


def indices_columna(encabezados, nombre_buscado):
    return [
        i for i, encabezado in enumerate(encabezados)
        if normalizar_encabezado(encabezado) == nombre_buscado
    ]


def a_entero(valor):
    try:
        return int(float(valor))
    except (TypeError, ValueError):
        return None


def a_decimal(valor):
    if valor in (None, ""):
        return None
    try:
        return Decimal(str(valor)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def a_texto_codigo(valor):
    """Normaliza un código (ej. codigo_entidad) que Excel puede entregar como
    número (90046.0) o texto ("90046"), para poder compararlo de forma consistente."""
    entero = a_entero(valor)
    if entero is not None:
        return str(entero)
    return str(valor).strip() if valor not in (None, "") else ""
