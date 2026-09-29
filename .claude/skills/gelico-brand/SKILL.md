---
name: gelico-brand
description: Identidad visual de GELICO — paleta de colores y radios del tema daisyUI "gelico", tipografía, y uso correcto del isotipo/wordmark/favicon. Usar siempre que se toque styles.css, se agregue una clase de color nueva, se use el logo en un template, o un colaborador pregunte "qué color uso para X" / "cómo pongo el logo".
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
| `primary` | `#4F46E5` (indigo) | Acción principal: botones primarios, enlaces, ítem activo del sidebar, foco de formularios. Es el color del isotipo — no lo cambies sin actualizar también el logo. |
| `secondary` | `#0D9488` (teal) | Acciones alternas que no deben competir con la primaria (p. ej. un segundo botón junto a "Guardar"), estados "en curso". |
| `accent` | `#F59E0B` (ámbar) | Uso puntual y escaso: destacar un dato, badges tipo "Pronto"/"Nuevo". **Nunca** como color de botón por defecto — satura la vista si se repite. |
| `neutral` | `#374151` | Superficies oscuras puntuales (footer, tooltips oscuros). Poco uso en esta app. |
| `info` / `success` / `warning` / `error` | azul / verde / ámbar oscuro / rojo | **Solo** para estado semántico real (alertas, validación, badges de estado). No los uses como decoración. |
| `base-100/200/300` | blancos y grises con tinte azulado | Fondos: `base-100` contenido/cards, `base-200` fondo de página/sidebar, `base-300` bordes/dividers. Se eligió un blanco no puro (`#FFFFFF`/`#F3F4F8`) para que el panel no "brille" en sesiones largas. |
| `base-content` | `#1E2233` | Texto por defecto. Es gris muy oscuro, no negro puro — mismo motivo: menos fatiga visual con alto contraste sostenido. |

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

## Logo — assets y cuándo usar cada uno

Todo vive en `main/static/brand/` (fuente única) + `main/static/favicon.*`:

| Archivo | Qué es | Cuándo usarlo |
|---|---|---|
| `brand/gelico-mark.svg` | Isotipo (cruz + libro + "G") en `fill="currentColor"`, `viewBox="0 0 780 780"` | Embebido **inline** (`{% include %}` o pegado directo en el HTML) cuando necesitas que el color del logo herede del contexto (p. ej. dentro de un botón, o un contenedor con `text-primary`/`text-white`). |
| `brand/gelico-mark-primary.svg` | Mismo isotipo, color de marca fijo (`#4F46E5`) | Vía `<img src="...">` en cualquier lugar donde no puedas controlar `currentColor` (así está usado hoy en el sidebar, `partials/base/_sidebar.html`). |
| `brand/gelico-wordmark.svg` | Isotipo + texto "GELICO", color de marca fijo | Pantallas con espacio de sobra y fondo claro: login (`registration/login.html`), portadas, splash. No lo achiques debajo de ~28px de alto — el texto deja de leerse. |
| `favicon.svg` | Isotipo en blanco sobre cuadro `#4F46E5` redondeado, `viewBox 0 0 64 64` | `<link rel="icon">`. Ya wireado en `base.html`/`login.html`. |
| `favicon.ico` | Igual, rasterizado en 16/32/48px | Fallback para navegadores que no soportan favicon SVG (`<link rel="alternate icon">`, ya wireado). |
| `brand/apple-touch-icon.png` | Igual, 180×180 | `<link rel="apple-touch-icon">` (ya wireado en `base.html`). |
| `brand/gelico-icon-512.png` | Isotipo en blanco sobre `#4F46E5`, 512×512 | Fuente para generar cualquier ícono nuevo (PWA manifest, redes, etc.) sin volver a exportar desde el SVG. |

### Reglas de uso del logo

- **No** lo re-colorees fuera de la paleta de marca (`#4F46E5` o
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
