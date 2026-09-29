---
name: gelico-brand
description: Identidad visual de GELICO — paleta de colores y radios del tema daisyUI "gelico", tipografía, uso correcto del isotipo/wordmark/favicon de GELICO, y del sello del Ministerio de Educación en reportes PDF. Usar siempre que se toque styles.css, se agregue una clase de color nueva, se use un logo en un template, se trabaje en el encabezado de un reporte/PDF, o un colaborador pregunte "qué color uso para X" / "cómo pongo el logo".
---

# GELICO — identidad visual

Carga también `gelico-conventions` para el stack general. Este skill cubre
**solo** apariencia: colores, tipografía y logo. No cubre estructura de
templates ni patrones de vistas (eso es `gelico-conventions` /
`gelico-crud-scaffold`).

## Principio rector

Toda la identidad vive en **un solo lugar**:
`theme/static_src/src/styles.css`, dentro del bloque
`@plugin "daisyui/theme" { name: "gelico"; ... }`. Nunca hardcodees un color
hex, un `border-radius` en px, o una fuente distinta directamente en un
`.html`. Si daisyUI no tiene una clase semántica para lo que necesitas,
la excepción está más abajo ("Cuándo SÍ hardcodear").

## Paleta — qué representa cada color y cuándo usarlo

| Token daisyUI | Hex | Uso |
|---|---|---|
| `primary` | `#111E60` (navy institucional) | Color de marca fijo — es el color del logo, elegido explícitamente por el usuario. Acción principal: botones primarios, enlaces, ítem activo del sidebar, foco de formularios. No lo cambies sin que te lo pidan; si cambia, actualiza también el logo (ver más abajo). |
| `secondary` | `#35437A` | Mismo matiz que `primary`, más claro. Acciones alternas que no deben competir con la primaria (p. ej. un segundo botón junto a "Guardar"). Se eligió del mismo azul a propósito — un color de otra familia (teal, verde) generaba choque visual junto al navy. |
| `accent` | `#8A6D3B` (dorado envejecido) | El complemento clásico del azul marino en identidades institucionales/académicas. Uso puntual y escaso: destacar un dato, badges tipo "Pronto"/"Nuevo". Es un dorado apagado, no ámbar brillante — con un dorado saturado el contraste entre colores se sentía "demasiado". **Nunca** como color de botón por defecto. |
| `neutral` | `#232A42` | Superficies oscuras puntuales (footer, tooltips oscuros), mismo matiz navy oscurecido. Poco uso en esta app. |
| `info` / `success` / `warning` / `error` | azul / verde / naranja quemado / rojo ladrillo, todos apagados (no saturados) | **Solo** para estado semántico real (alertas, validación, badges de estado). Se desaturaron a propósito para que convivan con el navy y el dorado sin verse "de otro sistema". No los uses como decoración. |
| `base-100/200/300` | `#FFFFFF` / `#EEF0F6` / `#D6DAE6` | Fondos: `base-100` contenido/cards, `base-200` fondo de página/sidebar, `base-300` bordes/dividers. `base-300` se separó deliberadamente más de `base-200` — con menos diferencia los bordes de las cards quedaban invisibles ("blanco sobre blanco"). Si en algún componente nuevo el borde se ve invisible otra vez, es señal de que se está usando `base-200` en vez de `base-300` para el borde. |
| `base-content` | `#161B2C` | Texto por defecto. Gris-navy muy oscuro, no negro puro — menos fatiga visual con alto contraste sostenido, y mismo matiz que el resto de la paleta. |

Estos colores están relacionados a propósito (variaciones del mismo azul +
un solo acento cálido + semánticos desaturados) para lograr contraste
suficiente entre superficie y contenido sin que los colores "choquen" entre
sí. Si agregas un color nuevo, deriva del navy o mantenlo igual de apagado
que el resto — no metas un tono saturado/brillante suelto.

Usa siempre las clases semánticas de daisyUI/Tailwind que ya se usan en el
proyecto: `btn btn-primary`, `btn btn-secondary`, `badge badge-accent`,
`badge badge-ghost`, `alert alert-error`, `bg-base-200`, `text-base-content/70`
(la opacidad `/70` etc. es el patrón estándar del proyecto para texto
secundario, no un color nuevo).

### Cuándo SÍ hardcodear un color

Los templates de **reporte PDF** (`partials/*/reporte_pdf.html`,
`_reporte_pdf.html`) son HTML plano sin `base.html`: WeasyPrint no carga
`{% tailwind_css %}` ni el tema daisyUI, así que ahí los colores van
inline en `<style>` como ya está (grises neutros, sin marca). No hace falta
ni conviene forzar la paleta de marca en PDFs — mantén el estilo sobrio ya
usado (`#1f2937`, `#6b7280`, etc.) salvo que el usuario pida explícitamente
llevar la identidad a los PDFs.

## Tipografía

Fuente: **Inter** (Google Fonts, cargada en `base.html` y
`registration/login.html` vía `<link>`, con fallback a
`ui-sans-serif, system-ui`). Está aplicada globalmente a `body` en
`styles.css` (`@theme { --font-sans: ... }` + regla en `@layer base`) — no
hace falta poner `font-sans` a mano en cada template. Si agregas un HTML
nuevo que no extiende `base.html` (como los PDFs), no asumas que Inter está
disponible — usa la fuente del sistema que ya usa ese template.

## Radios y forma

`--radius-box: 0.75rem` (cards, modales, alerts), `--radius-field: 0.5rem`
(inputs, botones, selects), `--radius-selector: 0.5rem` (checkboxes, badges,
toggles). Estos ya están seteados por daisyUI a través de sus propias clases
(`card`, `btn`, `input-bordered`, `badge`, etc.) — no agregues `rounded-*` de
Tailwind encima salvo un caso muy puntual que daisyUI no cubra.

## Sidebar

El menú lateral (`partials/base/_sidebar.html`) tiene su propio sistema de
componentes en `styles.css`. No repliques nada de esto con utilidades
sueltas en un `<li>` nuevo — copia la estructura de un ítem existente.

**Estructura de un ítem de menú** (la sigue todo `<li>` del `<ul class="menu
gelico-sidebar ...">`):

```html
<li>
  <a href="{% url '...' %}" class="{% if url_name == '...' %}menu-active{% endif %}" title="Texto">
    <span class="gelico-sidebar-icon">
      <svg ...>...</svg>
    </span>
    <span class="gelico-sidebar-label">Texto</span>
    <span class="gelico-sidebar-label badge badge-accent badge-soft badge-sm ml-auto">Pronto</span> <!-- solo si aplica -->
  </a>
</li>
```

- `.gelico-sidebar-icon` es el "chip": un cuadro de 2rem con fondo propio
  detrás del ícono — es lo que le da presencia (antes el ícono flotaba
  suelto sobre blanco). No pongas el `<svg>` directo dentro del `<a>` sin
  este wrapper.
- `.gelico-sidebar-label` marca **todo texto/badge que debe desaparecer
  cuando el sidebar está colapsado** (ver más abajo): el label del ítem, el
  badge "Pronto", el texto de `menu-title`. Si agregas un ítem nuevo y
  olvidas esta clase en el texto, ese texto se queda visible atropellando
  el riel de íconos al colapsar.
- `.menu-active` ya no es solo texto de color — pinta toda la fila como una
  píldora navy sólida (`background-color: var(--color-primary)`) con el
  chip de ícono en un tono más claro encima. Es automático, no hay que
  agregar nada más que la clase.
- `menu-title` (los separadores "ESCUELAS", "PROGRAMACIÓN", etc.) también
  envuelve su texto en `<span class="gelico-sidebar-label">` por el mismo
  motivo — el `<li>` en sí se queda (da el borde superior que separa
  secciones), solo el texto se oculta.

**Sidebar colapsable (desktop).** Hay un botón (`#sidebar-collapse-toggle`,
en el header del sidebar) que alterna la clase `sidebar-collapsed` en
`<html>` y la persiste en `localStorage` (`gelico-sidebar-collapsed`) — hace
falta JS porque esto es multi-página con recarga completa, no una SPA; el
`<script>` inline en `base.html` (antes de que cargue el CSS) aplica la
clase en el próximo `<head>` para que no haya parpadeo del sidebar
expandido. Todo el comportamiento de "qué se oculta/encoge al colapsar"
vive en un bloque `@media (min-width: 1024px) { html.sidebar-collapsed ... }`
en `styles.css`, **fuera de `@layer components` a propósito**: Tailwind v4
resuelve conflictos entre capas por orden de capa antes que por
especificidad, así que una regla de `components` nunca le gana a un
`.badge` de daisyUI (que cae en una capa posterior) aunque el selector sea
más específico — por eso ese bloque está sin capa (el CSS sin `@layer`
siempre gana). Si necesitas ocultar/ajustar algo más al colapsar, agrégalo
ahí, no dentro de `@layer components`, o simplemente no se aplicará.
Solo aplica en `lg:` (1024px+): en mobile el sidebar sigue siendo el drawer
overlay completo de daisyUI, colapsarlo ahí no tiene sentido.

## Usuario en sesión — dropdown en el navbar, no en el sidebar

La identidad de sesión (avatar + nombre + "Cerrar sesión") vive **solo** en
el navbar (`base.html`), arriba a la derecha, como un `dropdown
dropdown-end` de daisyUI: un botón con avatar/nombre/chevron que al hacer
foco despliega una tarjeta (`dropdown-content`) con nombre, email y el
botón de logout — que dispara el mismo `modal_logout` de siempre
(`partials/base/_logout.html`), no cierra sesión directo desde el dropdown.
Es 100% CSS de daisyUI (`:focus`/`:focus-within`), sin JS propio.

El sidebar **no** tiene ni debe tener un bloque de usuario — ya se probó
esa ubicación y se decidió que el navbar se ve mejor y es más convencional
(patrón estándar de dashboard: identidad de sesión arriba a la derecha). Si
en el futuro alguien pide "mover el usuario al sidebar" de nuevo, confirma
primero — ya se revirtió una vez.

## Logo — assets y cuándo usar cada uno

Todo vive en `main/static/brand/` (fuente única) + `main/static/favicon.*`:

| Archivo | Qué es | Cuándo usarlo |
|---|---|---|
| `brand/gelico-mark.svg` | Isotipo (cruz + libro + "G") en `fill="currentColor"`, `viewBox="0 0 780 780"` | Embebido **inline** (`{% include %}` o pegado directo en el HTML) cuando necesitas que el color del logo herede del contexto (p. ej. dentro de un botón, o un contenedor con `text-primary`/`text-white`). |
| `brand/gelico-mark-primary.svg` | Mismo isotipo, color de marca fijo (`#111E60`) | Vía `<img src="...">` en cualquier lugar donde no puedas controlar `currentColor` (así está usado hoy en el sidebar, `partials/base/_sidebar.html`, y en el navbar móvil de `base.html`). |
| `brand/gelico-wordmark.svg` | Isotipo (`#111E60`) + texto "GELICO" (`#161B2C`) | Pantallas con espacio de sobra y fondo claro: login (`registration/login.html`), portadas, splash. No lo achiques debajo de ~28px de alto — el texto deja de leerse. |
| `favicon.svg` | Isotipo en blanco sobre cuadro `#111E60` redondeado, `viewBox 0 0 64 64` | `<link rel="icon">`. Ya wireado en `base.html`/`login.html`. |
| `favicon.ico` | Igual, rasterizado en 16/32/48px | Fallback para navegadores que no soportan favicon SVG (`<link rel="alternate icon">`, ya wireado). |
| `brand/apple-touch-icon.png` | Igual, 180×180 | `<link rel="apple-touch-icon">` (ya wireado en `base.html`). |
| `brand/gelico-icon-512.png` | Isotipo en blanco sobre `#111E60`, 512×512 | Fuente para generar cualquier ícono nuevo (PWA manifest, redes, etc.) sin volver a exportar desde el SVG. |

### Reglas de uso del logo

- **No** lo re-colorees fuera de la paleta de marca (`#111E60` o
  `currentColor`) ni lo pongas en degradado/con sombra — el isotipo ya tiene
  suficiente detalle (cruz, libro, arco) y pierde legibilidad con efectos
  encima.
- **No** lo estires: siempre mantiene proporción 1:1 (`gelico-mark*.svg`,
  `favicon.svg`) o el aspect ratio nativo del wordmark (560:140). Si necesitas
  otro tamaño, escala con `class="size-N"`/`h-N w-auto`, nunca `w-N h-M` con
  proporciones distintas.
- **No** lo uses por debajo de ~20px de lado — el trazo (cruz + libro) se
  vuelve una mancha. Para espacios muy pequeños (favicon de navegador) ya
  existe `favicon.svg`, que es una versión simplificada a color sólido
  pensada para esos tamaños; no generes otra.
- Si necesitas el isotipo sobre un fondo oscuro y no es el sidebar/favicon
  (casos ya resueltos), usa `gelico-mark.svg` con `class="text-white"` (o el
  color que corresponda) en vez de crear un archivo nuevo — es exactamente
  para eso que existe en `currentColor`.

## Logo del Ministerio de Educación (sello institucional externo)

GELICO opera para el Ministerio de Educación, y sus reportes impresos llevan
el sello oficial. Esto **no** es un asset de marca de GELICO — es un símbolo
de una institución externa (el Escudo de El Salvador usado por el
Ministerio), así que sus reglas de uso son distintas a las del isotipo
propio:

| Archivo | Qué es | Cuándo usarlo |
|---|---|---|
| `main/static/instituciones/ministerio-educacion-sello.png` | Solo el escudo circular (sin el texto "MINISTERIO DE EDUCACIÓN"), recortado a cuadrado, fondo transparente | Espacios pequeños/cuadrados en encabezados de reporte — es el que ya está en uso en `liquidacion/templates/partials/asignacion/_reporte_pdf.html`, dentro del `<div class="logo">`. |
| `main/static/instituciones/ministerio-educacion.png` | Logo completo tal como lo entregó el usuario (escudo + línea + "MINISTERIO DE EDUCACIÓN"), fondo transparente, proporción ancha (~2.47:1) | Encabezados con espacio horizontal de sobra (portadas, pies de página anchos). No lo fuerces dentro de una caja cuadrada — se ve aplastado; para eso está la versión recortada. |

### Reglas de uso — distintas a las del logo de GELICO

- **No lo recolorees, no le cambies el trazo ni lo "limpies"** — a diferencia
  del isotipo de GELICO, este es un símbolo oficial de una institución
  externa; su forma y color (`#111E60` aprox., ya es prácticamente el mismo
  navy que `--color-primary` — coincidencia útil, no la fuerces si cambia) no
  son una decisión de diseño de este proyecto.
- Solo existen estas dos variantes (completo y sello recortado). Si un
  reporte nuevo necesita otro recorte/tamaño, pide el archivo original al
  usuario (`~/Downloads/logo_ministerio_educación.png` en su momento) en vez
  de regenerarlo a partir de estos dos — recortar sobre un recorte pierde
  calidad.
- Es exclusivo de **reportes/documentos impresos** (PDF vía WeasyPrint) por
  ahora. No lo agregues a la UI en pantalla (sidebar, navbar, login) salvo
  que el usuario lo pida explícitamente — ahí el logo que corresponde es el
  de GELICO.
- Para usarlo en un reporte PDF nuevo: el template necesita
  `{% load static %}` (los reportes no extienden `base.html`, así que no lo
  heredan) y luego `<img src="{% static 'instituciones/ministerio-educacion-sello.png' %}" alt="Ministerio de Educación">`
  dentro de un contenedor con tamaño fijo (ver `.logo`/`.logo img` en
  `_reporte_pdf.html` de `liquidacion` como referencia). La vista que arma el
  PDF debe pasar `base_url=request.build_absolute_uri('/')` a `HTML(...)`
  (ya es el patrón establecido, ver `gelico-crud-scaffold`) para que
  WeasyPrint pueda resolver la ruta `/static/...`.

## Si necesitas cambiar la identidad

Todo cambio de paleta/radio empieza y termina en el bloque
`@plugin "daisyui/theme"` de `theme/static_src/src/styles.css`. Si cambias
`--color-primary`, actualiza también `gelico-mark-primary.svg`, `favicon.svg`
y `gelico-wordmark.svg` (tienen el hex de marca fijo, no leen la variable CSS
porque son archivos SVG servidos fuera del pipeline de Tailwind) — y
regenera `favicon.ico` / `apple-touch-icon.png` / `gelico-icon-512.png` a
partir del nuevo `favicon.svg` con `rsvg-convert` + `magick` (ver historial
de este skill o pide el procedimiento si no está documentado). No cambies la
paleta por tu cuenta si no te lo piden explícitamente: es una decisión de
diseño del usuario, igual que el dominio de datos.
