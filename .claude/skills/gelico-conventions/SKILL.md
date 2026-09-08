---
name: gelico-conventions
description: Arquitectura, stack y reglas de higiene del proyecto GELICO (Django + HTMX + daisyUI + Select2 + WeasyPrint). Usar siempre que se trabaje en este repo: crear/editar modelos, vistas, urls, templates, settings, o conectar una app nueva.
---

# GELICO — convenciones del proyecto

GELICO (**Ge**stión de **Li**quidaciones y **Co**nvocatorias) administra, para
un sistema educativo departamental en El Salvador, las convocatorias y
auxiliares que se programan en las escuelas, los encargados/CDE de cada
escuela, y (módulo en reconstrucción) las liquidaciones de fondos que el
Ministerio transfiere a los Consejos Directivos Escolares. Es un proyecto
**solo** del usuario (Alejandro), no de equipo — las convenciones abajo son
las que él mismo ya sentó en el código; el objetivo es seguirlas al pie de la
letra para que el código que generes sea indistinguible del suyo.

## Stack

- Python 3.13, Django 5.2.6, SQLite en desarrollo (Postgres vía `psycopg` ya
  en requirements pero no configurado — no asumir que ya se usa).
- Docker + Docker Compose: todo comando de manage.py se corre con
  `docker compose run --rm web python manage.py <comando>`. No asumas un
  entorno virtual local a menos que el usuario indique lo contrario.
- `django-tailwind` + `daisyUI` para estilos (clases `input input-bordered`,
  `btn btn-primary`, `card`, `modal`, `menu`, etc.). No introducir otro
  framework de CSS.
- `django-htmx` para todas las interacciones dinámicas (búsqueda, paginación,
  modales de crear/editar/eliminar). No usar fetch/JS a mano para esto: si ya
  existe el patrón htmx, replicarlo (ver skill `gelico-crud-scaffold`).
- `django-select2` para cualquier campo `ModelChoiceField`/FK en un form,
  siempre con `Select2Widget(attrs={'class': 'select2-daisy', 'data-placeholder': ...})`.
- `weasyprint` para generar los PDFs de "Imprimir" (nunca otra librería de PDF).
- `django-easy-audit` está activo (middleware + apps), audita cambios en
  modelos automáticamente — no dupliques esa lógica con `created_at`/logs manuales.
- `django-browser-reload` solo en DEBUG.
- Idioma: **todo** en español — nombres de campos, labels, mensajes de UI,
  verbose_name, docstrings si las hay. Los nombres de variables/funciones en
  español también (`_encargados_filtrados`, `home_convocatorias`, etc.), tal
  como está en el código existente.
- No hay Class-Based Views ni DRF en ningún lado del proyecto. Todo es
  **function-based views**. No introduzcas CBVs "porque son más limpias":
  rompe la consistencia con el resto del código.

## Mapa de apps

| App           | Modelos                                                        | Estado |
|---------------|------------------------------------------------------------------|--------|
| `main`        | (sin modelos) home + login/logout, `base.html`, sidebar, breadcrumbs | Wired |
| `escuela`     | `Distrito`, `Escuela`, `CDE`, `Encargado`                        | Wired (`/escuela/...`) |
| `programacion`| `Convocatoria`, `Auxiliar`, `Programacion`, `Horario`, `Ausencia` | Wired (`/programacion/...`) |
| `catalogo`    | `Bono`                                                            | **NO** está en `gelico/urls.py` todavía, aunque sí en `INSTALLED_APPS` |
| `liquidacion` | (vacío — modelos/vistas/forms/urls sin implementar)               | **NO** está en `gelico/urls.py`. Se está reconstruyendo desde cero (branch `wb-liquidaciones-brand-new`). Ver skill `gelico-liquidacion-domain` antes de diseñar su esquema. |
| `usuario`     | (vacío, placeholder)                                              | **NO** está en `gelico/urls.py` |
| `theme`       | app de `django-tailwind`, no tocar salvo temas/CSS                | — |

Antes de agregar código a `catalogo`, `liquidacion` o `usuario`, confirma si
ya deben conectarse a `gelico/urls.py` — hoy no lo están y probablemente ese
sea justo el trabajo pendiente.

## Checklist al dar de alta o conectar una app

1. `INSTALLED_APPS` en `gelico/settings.py` (ya están las apps propias del
   proyecto listadas; una app nueva sí se agrega aquí).
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

## Preservar filtros: `{% querystring %}`

Todo enlace de paginación, editar, eliminar, imprimir o "limpiar" que deba
respetar los filtros activos usa el tag `{% querystring %}` (Django 5.1+),
opcionalmente con overrides: `{% querystring page=numero %}`. No reconstruyas
el query string a mano.

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
explícitamente preparando un despliegue a producción (ya está `python-decouple`
en requirements para cuando llegue ese momento).
