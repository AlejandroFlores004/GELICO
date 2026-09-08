---
name: gelico-liquidacion-domain
description: Vocabulario y estructura de datos reales de las transferencias de fondos del Ministerio de Educación hacia los Consejos Directivos Escolares (CDE), extraídos de los reportes fuente en "GELICO información/SISTEMA/". Usar al diseñar o modificar modelos, forms o vistas de las apps liquidacion y catalogo (recibos, planillas, bonos, montos, transferencias), porque ese módulo se está reconstruyendo desde cero.
---

# GELICO — dominio de liquidaciones

## Contexto

La app `liquidacion` está vacía a propósito ahora mismo: `models.py`,
`views.py`, `forms.py` y `urls.py` no tienen nada implementado, en la rama
`wb-liquidaciones-brand-new`. El historial de git muestra que antes existió
una versión con "recibo", "transferencia" y "saldo" que fue removida
(`Remove transferencias related templates...`) para rehacerse. Cuando se
pida trabajar en `liquidacion` (o en `catalogo.Bono`, que ya existe y se
relaciona con esto), trata el esquema como abierto — no asumas que ya hay
una forma "correcta", pero sí aprovecha el vocabulario real de abajo en vez
de inventar nombres de campos nuevos.

## Fuente de verdad externa

En `University/horas-sociales/GELICO información/SISTEMA/` hay reportes
reales exportados del sistema del Ministerio de Educación (no forman parte
del repo git, son insumos de referencia):

- `REPORTE TRANSFERIDO POR RECIBO.xlsx` / `.XLS`
- `REPORTE TRANSFERIDO POR RECIBO - completo.xlsx` / `.XLS` (~1267 filas × 23 columnas)
- `DIRECTORIO TELEFONICO CLUSTERS ACTUALIZADOS SAN VICENTE 2026.xlsx`

Son reportes de **transferencias de fondos a CDE** (Consejos Directivos
Escolares) — el tipo de dato que la app `liquidacion` debe terminar
modelando y, probablemente, poder importar o cotejar contra estos archivos.

## Campos reales observados en "REPORTE TRANSFERIDO POR RECIBO"

Extraídos directamente de las celdas del reporte:

| Campo (nombre real en el reporte) | Lectura probable |
|---|---|
| `codigo_entidad` | código de la escuela/entidad receptora — coteja contra `escuela.Escuela.codigo` |
| `codigo_departamento` | código de departamento (ej. `10`) |
| `codigo_municipio` | código de municipio (ej. `06`) |
| `nombre` | nombre de la escuela (aparece como `CENTRO ESCOLAR "..."`) o del municipio, según la fila |
| `codigo_modalidad_admin` | modalidad administrativa de la escuela |
| `id_bono` | referencia al tipo de bono/subsidio — coteja contra `catalogo.Bono` |
| `id_fuente` | fuente de financiamiento |
| `codigo_requerimiento` / `no_requerimiento` | número de requerimiento (la solicitud de fondos que origina la transferencia) |
| `codigo_planilla` | código de planilla asociada |
| `id_planilla_parcial` | identificador de planilla parcial (pagos fraccionados) |
| `id_pre_carga` | identificador de una carga previa del dato en el sistema origen |
| `id_transferencia` | identificador único de la transferencia (candidato a ser el PK lógico de "Recibo"/"Transferencia") |
| `anio` | año fiscal de la transferencia |
| `estado_trans` | estado de la transferencia (visto: `01`... — son códigos, no texto; hace falta el catálogo de equivalencias si el Ministerio lo publica) |
| `monto_asignado` | monto asignado/presupuestado |
| `monto` | monto efectivamente transferido |

Formato de código de recibo/planilla observado: `B10-01787-26` (patrón
`B<depto>-<consecutivo>-<año corto>`).

## Cómo usar esto al diseñar el módulo

1. Si el usuario pide crear el modelo de `liquidacion` (Recibo, Transferencia,
   Planilla, Requerimiento...), propone campos que **mapeen 1:1 a estos
   nombres reales** (`monto_asignado`, `monto`, `anio`, `no_requerimiento`,
   `codigo_planilla`, `estado_trans`, etc.) en vez de inventar sinónimos —
   así, si más adelante se necesita importar estos `.xlsx`/`.XLS`, la
   correspondencia es directa.
2. Relaciona con lo que ya existe: `id_bono` → FK a `catalogo.Bono`;
   `codigo_entidad`/`nombre` de escuela → FK a `escuela.Escuela` (que ya
   tiene `codigo` único); departamento/municipio podrían mapear a
   `escuela.Distrito` si el usuario confirma que ese es el mismo concepto
   (verificar, no asumir — `Distrito` en el modelo actual no tiene código
   numérico, solo `nombre`).
3. **No fijes el esquema final sin preguntar** si estos reportes son la
   fuente de un importador real (CSV/XLS upload) o solo referencia para
   nombrar campos con criterio. Es una decisión de producto del usuario, no
   algo que se deba inferir.
4. Para las vistas/forms/templates de `liquidacion` una vez el modelo esté
   claro, sigue el patrón del skill `gelico-crud-scaffold` (filtro+paginación,
   modales htmx+daisyUI, imprimir con WeasyPrint) — la mecánica de UI es la
   misma que en el resto del proyecto, lo único específico de este dominio
   son los nombres de campo.
