---
name: gelico-crud-scaffold
description: Receta parametrizada para construir un módulo CRUD completo en GELICO (modelo, form, vistas con filtro+paginación, urls, templates htmx+daisyUI, PDF, admin, sidebar), replicando exactamente el patrón ya establecido en programacion/convocatoria y escuela/encargado. Usar cuando se pida agregar, crear o gestionar una nueva entidad/listado/catálogo ("gestión de X", "listado de X con búsqueda", "crear/editar/eliminar/imprimir X").
---

# GELICO — scaffold de un módulo CRUD

Antes de usar esto, carga también `gelico-conventions` (stack, namespacing de
templates, checklist de apps). Este skill es puramente mecánico: dado un
modelo **que el usuario ya definió o aprobó**, produce el mismo esqueleto de
archivos que ya existe para `Auxiliar`/`Convocatoria` (programacion) y
`Encargado` (escuela) — el patrón más limpio y actual de los dos es el de
`convocatorias`; síguelo a él, no al de `auxiliar` (que dejó los partials sin
namespacear). No uses este skill para decidir qué campos debe tener el
modelo — eso es dominio, no scaffold; si el modelo aún no existe o no está
claro, pregúntale al usuario primero.

## Parámetros a fijar antes de escribir código

Determínalos por contexto o pregúntalos si no son obvios:

- `app`: app Django donde vive (existente o nueva).
- `feature`: slug en minúsculas y singular para urls/templates (`convocatoria`, `bono`, `recibo`).
- `Feature` / `Features`: label en español, singular y plural, para títulos y breadcrumbs ("Convocatoria" / "Convocatorias").
- `model`: nombre del modelo (`Convocatoria`).
- `fields`: campos del form (excluye FKs calculadas, timestamps, etc.).
- `filtros`: qué campos son filtrables — texto libre (icontains OR-combinado) vs. FK/choice (select exacto).
- `list_columns`: columnas de la tabla de listado.
- `needs_toggle_estado`: ¿el modelo tiene un campo `estado` booleano con semántica de "solo uno activo por relación" (como `Encargado`)? Si sí, agrega las vistas `_toggle`/`_cambiar` descritas al final. Si es un CRUD simple sin ese estado, usa solo `_eliminar`.

## 1. Modelo (si es nuevo)

Sigue el estilo ya usado: `CharField`/`TextField`/`DateField` simples, FK con
`on_delete=models.CASCADE` salvo que se indique lo contrario, `__str__`
descriptivo, y `class Meta` con `verbose_name`/`verbose_name_plural` en
español singular/plural.

## 2. `admin.py`

```python
@admin.register(Feature)
class FeatureAdmin(admin.ModelAdmin):
    list_display = (...)
    list_filter = (...)      # FKs y booleans que tenga
    search_fields = (...)    # campos de texto
    ordering = (...)
    fieldsets = (
        ('Información Básica', {'fields': (...)}),
        ('Relaciones', {'fields': (...)}),   # si hay FKs
        ('Estado', {'fields': ('estado',)}), # si aplica
    )
```

## 3. `forms.py`

`FeatureForm(forms.ModelForm)` con `Meta.fields` explícitos y `widgets`
daisyUI para cada campo:

- texto → `forms.TextInput(attrs={'class': 'input input-bordered w-full', 'placeholder': '...'})`
- textarea → `forms.Textarea(attrs={'class': 'textarea textarea-bordered w-full', 'rows': 4})`
- fecha → `forms.DateInput(attrs={'class': 'input input-bordered w-full', 'type': 'date'})`
- FK → `Select2Widget(attrs={'data-placeholder': 'Seleccione...', 'style': 'width: 100%', 'class': 'select2-daisy'})`
- choice fijo → `forms.Select(attrs={'class': 'select select-bordered w-full'})`

Validaciones cruzadas (ej. fecha_fin >= fecha_inicio) van en `clean()` del
form, con `self.add_error('campo', 'mensaje')` — no en la vista.

Si hay filtros por FK/estado, agrega también `FiltrarFeatureForm(forms.Form)`
con esos campos `required=False` (ver ejemplo `FiltrarEncargadosForm` en
`escuela/forms.py`).

## 4. `views.py`

Nombres de función **exactos** (así están en todo el proyecto):

```python
def _feature_filtrados(request):
    """Queryset filtrado, SIN paginar. Lo reutiliza tanto el listado como el imprimir."""
    search = request.GET.get('q', '').strip()          # o un form de filtro si hay FKs/estado
    features = Feature.objects.all().order_by(...)
    if search:
        features = features.filter(Q(campo1__icontains=search) | Q(campo2__icontains=search))
    # ... resto de filtros
    return search, features

def _filtrar_feature(request):
    search, features_list = _feature_filtrados(request)
    paginator = Paginator(features_list, 20)
    features = paginator.get_page(request.GET.get('page'))
    return search, features

def featureHomeView(request):
    breadcrumbs = [
        {'name': 'Inicio', 'url': reverse('home')},
        {'name': 'Features', 'url': reverse('home_feature')},
    ]
    search, features = _filtrar_feature(request)
    return render(request, 'feature/featureHome.html', {
        'breadcrumbs': breadcrumbs, 'features': features, 'search': search,
    })

def buscar_feature(request):
    _, features = _filtrar_feature(request)
    return render(request, 'partials/feature/tabla.html', {'features': features})

def feature_form(request, pk=None):
    instance = get_object_or_404(Feature, pk=pk) if pk else None
    if request.method == 'POST':
        form = FeatureForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            _, features = _filtrar_feature(request)
            return render(request, 'partials/feature/modal_form_success.html', {'features': features})
    else:
        form = FeatureForm(instance=instance)
    return render(request, 'partials/feature/modal_form.html', {'form': form, 'instance': instance})

def feature_eliminar(request, pk):
    instance = get_object_or_404(Feature, pk=pk)
    if request.method == 'POST':
        instance.delete()
        _, features = _filtrar_feature(request)
        return render(request, 'partials/feature/modal_form_success.html', {'features': features})
    return render(request, 'partials/feature/modal_delete.html', {'instance': instance})

def feature_imprimir(request):
    _, features = _feature_filtrados(request)   # SIN paginar
    html_string = render_to_string('partials/feature/reporte_pdf.html', {
        'features': features, 'fecha_generacion': timezone.localdate(),
    })
    pdf = HTML(string=html_string, base_url=request.build_absolute_uri('/')).write_pdf()
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="features.pdf"'
    return response
```

Si `needs_toggle_estado`, agrega (calcado de `escuela/views.py`):

```python
def feature_toggle_estado(request, pk):
    instance = get_object_or_404(Feature, pk=pk)
    if request.method == 'POST':
        instance.estado = not instance.estado
        instance.save()
        if instance.estado:
            # apaga cualquier otro registro activo de la misma relación
            Feature.objects.filter(relacion=instance.relacion, estado=True).exclude(pk=instance.pk).update(estado=False)
        _, features = _filtrar_feature(request)
        return render(request, 'partials/feature/modal_form_success.html', {'features': features})
    return render(request, 'partials/feature/modal_toggle_confirm.html', {'instance': instance})
```

## 5. `urls.py`

Nomenclatura canónica (la de `programacion`, más consistente que la vieja de
`escuela`):

```python
path('feature/', views.featureHomeView, name='home_feature'),
path('feature/buscar/', views.buscar_feature, name='buscar_feature'),
path('feature/imprimir/', views.feature_imprimir, name='feature_imprimir'),
path('feature/nuevo/', views.feature_form, name='feature_nuevo'),
path('feature/<int:pk>/editar/', views.feature_form, name='feature_editar'),
path('feature/<int:pk>/eliminar/', views.feature_eliminar, name='feature_eliminar'),
# si needs_toggle_estado:
path('feature/<int:pk>/toggle/', views.feature_toggle_estado, name='feature_toggle'),
```

Si `app` es nueva, súmala a `gelico/urls.py` con
`path('<prefijo>/', include('<app>.urls'))` — recuerda que esto se olvida.

## 6. Templates — **siempre namespaceados** bajo `partials/feature/`

```
<app>/templates/feature/featureHome.html
<app>/templates/partials/feature/toolbar.html
<app>/templates/partials/feature/buscador.html
<app>/templates/partials/feature/tabla.html
<app>/templates/partials/feature/modal_form.html
<app>/templates/partials/feature/modal_delete.html
<app>/templates/partials/feature/modal_form_success.html
<app>/templates/partials/feature/reporte_pdf.html
```

**`featureHome.html`** — extiende `base.html`, header con icono+título+
descripción (estilo de `auxiliarHome.html`), luego:

```django
{% include "partials/feature/toolbar.html" %}
{% include "partials/feature/buscador.html" %}
<div id="feature-modal-wrapper"></div>
{% include "partials/feature/tabla.html" %}
```

**`toolbar.html`** — botón "Agregar Feature":

```django
<button hx-get="{% url 'feature_nuevo' %}" hx-target="#feature-modal-wrapper" hx-swap="outerHTML" class="btn btn-primary gap-2">
  Agregar Feature
</button>
```

**`buscador.html`** — card con el form de filtros, `hx-get` a `buscar_feature`
apuntando a `#listado-feature` con `outerHTML`, botón "Limpiar" a
`home_feature` sin querystring.

**`tabla.html`** — `<div id="listado-feature"{% if oob %} hx-swap-oob="true"{% endif %} class="card ...">`:
header con contador (`{{ features.paginator.count }} registros`), link
"Imprimir" a `feature_imprimir` con `{% querystring %}` y `target="_blank"`,
tabla con botones editar/eliminar por fila (`hx-get` a `feature_editar`/
`feature_eliminar`, target `#feature-modal-wrapper`, `outerHTML`), fila
`{% empty %}` "No existen registros.", y paginación con doble enlace (`href`
normal + `hx-get` a `buscar_feature`) usando `{% querystring page=N %}`.

**`modal_form.html`** — `<dialog id="feature-modal" class="modal">` dentro de
`#feature-modal-wrapper`, form con `hx-post` a `feature_editar`/`feature_nuevo`
(`{% querystring %}` incluido), `hx-target="#feature-modal-wrapper"
hx-swap="outerHTML"`, botones Cancelar/Guardar, y el script inline que hace
`dialog.showModal()` al insertarse y limpia el wrapper (`wrapper.innerHTML = ''`)
al cerrar — cópialo tal cual de `modal_form.html` de auxiliar.

**`modal_delete.html`** — mismo patrón de dialog, resumen del registro a
borrar, botón `btn-error` "Borrar", `hx-post` a `feature_eliminar`.

**`modal_form_success.html`** — el "cierra modal + refresca tabla" en un solo
swap:

```django
<div id="feature-modal-wrapper"></div>

{% include "partials/feature/tabla.html" with oob=True %}
```

**`reporte_pdf.html`** — HTML plano (sin `base.html`, WeasyPrint no ejecuta
JS/htmx) con tabla de `features` y `fecha_generacion`.

## 7. Sidebar

Agrega el `<li>` dentro del grupo correcto (o crea un `menu-title` nuevo si
es un dominio distinto) en
`main/templates/partials/base/_sidebar.html`:

```django
<li>
  <a href="{% url 'home_feature' %}" class="{% if request.resolver_match.url_name == 'home_feature' %}menu-active{% endif %}">
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" stroke-linejoin="round" stroke-linecap="round"
        stroke-width="2" fill="none" stroke="currentColor" class="inline-block size-4">
      <!-- icono outline consistente con los demás, mismos atributos -->
    </svg>
    <span>Features</span>
  </a>
</li>
```

Si el feature aún no tiene vista lista pero ya se planeó el link, usa el
patrón "Pronto": `<a href="#" class="pointer-events-none opacity-50">...
<span class="badge badge-ghost badge-xs ml-auto">Pronto</span></a>`.

## Checklist final

- [ ] `makemigrations` + `migrate` si hubo modelo nuevo/cambiado.
- [ ] Todos los templates namespaceados bajo `partials/feature/` (nunca sueltos).
- [ ] `urls.py` de la app incluido en `gelico/urls.py` (si es app nueva o recién conectada).
- [ ] Modelo registrado en `admin.py`.
- [ ] Entrada en el sidebar, con `menu-active` funcionando.
- [ ] Botón "Imprimir" reutiliza `_feature_filtrados` (no paginado) para no cortar el reporte a 20 filas.
- [ ] Si el modelo tiene relación "uno activo por grupo" (`needs_toggle_estado`), el toggle apaga a los demás activos.
- [ ] ¿La vista necesita `@login_required`? Pregúntalo si no es obvio (ver `gelico-conventions`).
