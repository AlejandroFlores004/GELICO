---
name: gelico-conventions
description: Stack técnico y buenas prácticas de backend/frontend del proyecto GELICO (Django + Docker + Tailwind v4 + daisyUI + HTMX + Select2 + WeasyPrint). Usar siempre que se trabaje en este repo — crear/editar vistas, forms, templates, settings, o conectar una app nueva. No cubre diseño de modelos/dominio: eso lo decide el usuario.
---

# GELICO — stack y buenas prácticas

GELICO (**Ge**stión de **Li**quidaciones y **Co**nvocatorias) es un proyecto
Django **solo** del usuario (Alejandro), no de equipo. Este skill documenta
**cómo** está construido (stack, herramientas, patrones de código) para que
lo que generes sea indistinguible de lo que él mismo escribiría — **no**
documenta **qué** modelar. Los modelos de dominio (campos, relaciones,
lógica de negocio) están en desarrollo activo y son decisión exclusiva del
usuario; no los diseñes, completes ni "corrijas" por iniciativa propia.

## Stack (de `requirements.txt` / `Dockerfile`)

- Python 3.13, Django 5.2.6.
- Base de datos: **SQLite en desarrollo**. `psycopg` (Postgres 3) ya está en
  requirements para cuando el usuario migre, pero hoy no hay nada
  configurado para Postgres — no lo asumas ni lo actives por tu cuenta.
  Como el destino final es Postgres, al escribir queries/modelos prioriza
  código portable: usa el ORM en vez de SQL crudo o funciones específicas de
  SQLite, `DecimalField` (no `FloatField`) para cualquier monto/dinero,
  `DateTimeField`/`DateField` con `USE_TZ=True` (ya está así) en vez de
  strings de fecha, y evita índices/constraints que SQLite no valide pero
  Postgres sí exija (o viceversa).
- Docker + Docker Compose (`Dockerfile`, `docker-compose.yml`, `start.sh`):
  todo comando de `manage.py` se corre con
  `docker compose run --rm web python manage.py <comando>`. El servicio
  `web` ya monta el repo como volumen y corre `start.sh` (Tailwind watcher +
  `runserver`). No asumas un entorno virtual local a menos que el usuario lo
  indique explícitamente.
- `django-tailwind` (app `theme`) + **Tailwind v4** + **daisyUI v5**, vía
  `theme/static_src` (Node/npm dentro del contenedor). Config **CSS-first**:
  no hay `tailwind.config.js`, todo vive en `theme/static_src/src/styles.css`
  (`@import "tailwindcss"`, `@plugin "daisyui"`, `@source "..."`). Si un
  cambio de clases no aparece, primero sospecha del watcher (`start.sh`
  corre `tailwind start` en background), no del build.
  Usa siempre clases daisyUI (`input input-bordered`, `btn btn-primary`,
  `card`, `modal`, `menu`, `badge`, etc.) — no introduzcas otro framework de
  CSS ni CSS a mano salvo casos que daisyUI no cubra.
- `django-htmx` para toda interacción dinámica (búsqueda, paginación,
  modales de crear/editar/eliminar). No escribas `fetch`/JS a mano para
  esto: si ya existe el patrón htmx en el módulo que estás tocando,
  replícalo (ver skill `gelico-crud-scaffold`).
- `django-select2` para cualquier campo `ModelChoiceField`/FK en un form,
  siempre con
  `Select2Widget(attrs={'class': 'select2-daisy', 'data-placeholder': ...})`.
- `weasyprint` (+ `pydyf`) para generar los PDFs de "Imprimir" (nunca otra
  librería de PDF). Los templates de reporte son HTML plano sin
  `base.html`: WeasyPrint no ejecuta JS ni htmx.
- `django-easy-audit` está activo (middleware + app), audita cambios de
  modelos automáticamente — no dupliques esa lógica con
  `created_at`/`updated_at`/logs manuales a menos que el usuario lo pida.
- `django-browser-reload` solo en `DEBUG`.
- `django-extensions` y `python-decouple` están instalados pero sin uso
  activo evidente en el código — no los actives ni les des lógica nueva sin
  que se pida.

## Backend — patrones de este proyecto

- **Solo function-based views.** No hay Class-Based Views ni DRF en ningún
  lado del proyecto. No introduzcas CBVs "porque son más limpias": rompe la
  consistencia con el resto del código.
- Patrón de listado establecido (ver `gelico-crud-scaffold` para la receta
  completa): una función `_feature_filtrados` que arma el queryset
  filtrado sin paginar (la reutilizan el listado y el "Imprimir"), y
  `_filtrar_feature` que la envuelve con `Paginator`. No apliques
  paginación dentro de la función que usa "Imprimir": corta el reporte.
- Validaciones cruzadas entre campos van en `clean()` del `ModelForm`
  (`self.add_error('campo', 'mensaje')`), no sueltas en la vista.
- Evita N+1: usa `select_related`/`prefetch_related` en querysets que
  recorren FKs en templates o PDFs.
- Idioma: **todo** en español visible al usuario — nombres de campos,
  labels, mensajes, `verbose_name`. Nombres de variables/funciones también
  en español, tal como está en el código existente
  (`_encargados_filtrados`, `home_convocatorias`, etc.).

## Frontend — Tailwind v4 + daisyUI + HTMX

- Cualquier clase Tailwind/daisyUI nueva que uses en un `.html`/`.py`/`.js`
  ya es detectada por el `@source` glob de `styles.css`; no hace falta
  tocar config para que se genere.
- Modales: `<dialog class="modal">` controlado con htmx
  (`hx-get`/`hx-post` + `hx-target` + `hx-swap="outerHTML"`), no con JS de
  Alpine/Bootstrap ni modales manuales.
- Preserva filtros activos en enlaces de paginación/editar/eliminar/
  imprimir/limpiar con el tag `{% querystring %}` (Django 5.1+),
  opcionalmente con overrides (`{% querystring page=numero %}`). No
  reconstruyas el query string a mano.

## Mapa de apps (estado de wiring, no de dominio)

| App           | Estado |
|---------------|--------|
| `main`        | Wired — home + login/logout, `base.html`, sidebar, breadcrumbs |
| `escuela`     | Wired (`/escuela/...`) |
| `programacion`| Wired (`/programacion/...`) |
| `catalogo`    | **NO** está en `gelico/urls.py` todavía, aunque sí en `INSTALLED_APPS` |
| `liquidacion` | Vacía — se está reconstruyendo desde cero (branch `wb-liquidaciones-brand-new`). **No** está en `gelico/urls.py`. El esquema de modelos es 100% decisión del usuario; no lo propongas por tu cuenta, pregúntale antes de escribir `models.py` |
| `usuario`     | Vacía, placeholder — **NO** está en `gelico/urls.py` |
| `theme`       | App de `django-tailwind`, no tocar salvo temas/CSS |

Antes de agregar código a `catalogo`, `liquidacion` o `usuario`, confirma si
ya deben conectarse a `gelico/urls.py`.

## Checklist al dar de alta o conectar una app

1. `INSTALLED_APPS` en `gelico/settings.py`.
2. `path('<prefijo>/', include('<app>.urls'))` en `gelico/urls.py` — **esto
   se olvida fácil**, revisa siempre que exista.
3. Registrar los modelos en `admin.py` con `@admin.register(Model)` +
   `ModelAdmin` (`list_display`, `list_filter`, `search_fields`, `ordering`,
   `fieldsets` agrupados en español: "Información Básica", "Relaciones",
   "Estado", "Contacto"... sigue el patrón de `escuela/admin.py`).
4. Agregar la entrada correspondiente en el sidebar
   (`main/templates/partials/base/_sidebar.html`) — ver skill
   `gelico-crud-scaffold`.

## Regla crítica: namespacing de templates parciales

`TEMPLATES[0]['APP_DIRS'] = True` con **varias apps**, cada una con su propia
carpeta `templates/`. Django fusiona todas esas carpetas en un único espacio
de nombres de búsqueda: si dos apps (o dos features de la misma app) definen
`templates/partials/tabla.html`, la que Django resuelve depende del orden de
`INSTALLED_APPS` — un choque **silencioso**, sin error, solo el template
equivocado renderizando.

Esto ya ocurre en el repo: `programacion/templates/partials/tabla.html`,
`buscador.html`, `toolbar.html`, `modal_agregar.html` son genéricos (los usa
`auxiliar`), mientras que `convocatorias` en la misma app sí namespacea bajo
`partials/convocatorias/...`. Es una inconsistencia heredada, no la
repliques.

**Regla a seguir de aquí en adelante para todo template nuevo:** siempre
namespacear bajo `partials/<feature_slug>/...`, igual que hace `escuela`
(`partials/encargado/_encargado_*.html`) y `convocatorias`. Nunca crear
`partials/tabla.html`, `partials/toolbar.html`, etc. a secas.

## Autenticación — hueco conocido, no lo arregles sin que te lo pidan

Solo `main.home_view` está protegida con `@login_required(login_url='login')`.
Ninguna vista CRUD de `escuela` ni `programacion` lo está todavía. Si vas a
tocar vistas existentes, **no** agregues `@login_required` en bloque por tu
cuenta — es una decisión de alcance del usuario. Si es relevante para lo que
te están pidiendo, pregúntale primero si quiere que la nueva vista quede
protegida.

## Settings de desarrollo — no "arreglar" sin que se pida

`SECRET_KEY` hardcodeada y `DEBUG = True` en `gelico/settings.py` son
configuración de desarrollo intencional en este punto del proyecto. No las
muevas a variables de entorno ni las endurezcas a menos que el usuario esté
explícitamente preparando un despliegue a producción (ya está
`python-decouple` en requirements para cuando llegue ese momento).

## Qué NO hacer

Este skill (y `gelico-crud-scaffold`) cubren **mecánica de código**: stack,
patrones de vistas/templates, higiene del repo. Ninguno de los dos debe
dictar el **dominio**: nombres de campos, esquema de modelos, reglas de
negocio de liquidaciones/convocatorias/bonos/montos, etc. Esas decisiones
son del usuario y están activamente en desarrollo — si una tarea requiere
diseñar un modelo nuevo o cambiar uno existente de forma no trivial,
pregúntale antes de fijar el esquema en vez de inferirlo.
