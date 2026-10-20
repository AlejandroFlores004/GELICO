from urllib.parse import urlparse

from django.core.paginator import Paginator
from django.shortcuts import render, get_object_or_404
from django.urls import Resolver404, resolve, reverse
from django_htmx.http import HttpResponseClientRedirect
from main.pdf import datos_filtro, respuesta_pdf
from main.permisos import permiso_formulario, permiso_requerido
from . import forms, services
from .models import Encargado, CDE, Escuela


def _escuela_en_gestion(request):
    """Si la petición htmx viene de la página "Gestionar" de una escuela,
    devuelve esa escuela. Así los modales de encargado y CDE saben que deben
    usar esa escuela y recargar esa página al guardar."""
    url_actual = request.htmx.current_url if request.htmx else None
    if not url_actual:
        return None
    try:
        coincidencia = resolve(urlparse(url_actual).path)
    except Resolver404:
        return None
    if coincidencia.url_name != 'escuela_gestionar':
        return None
    return Escuela.objects.filter(pk=coincidencia.kwargs['pk']).first()


def _recargar_gestion(escuela):
    """Cierra el modal y recarga la página "Gestionar" de la escuela."""
    return HttpResponseClientRedirect(reverse('escuela_gestionar', args=[escuela.pk]))


# ===================== Encargados =====================

def _encargados_filtrados(request):
    """Formulario de filtros y encargados filtrados, SIN paginar (lo reutiliza el imprimir)."""
    filtro_form = forms.FiltrarEncargadosForm(request.GET or None)
    return filtro_form, services.filtrar_encargados(datos_filtro(filtro_form))


def _filtrar_encargados(request):
    filtro_form, encargados_list = _encargados_filtrados(request)
    encargados = Paginator(encargados_list, 20).get_page(request.GET.get('page'))
    return filtro_form, encargados


def _respuesta_encargado_guardado(request):
    """Tras guardar: recarga "Gestionar escuela" o refresca el listado de encargados."""
    escuela_gestion = _escuela_en_gestion(request)
    if escuela_gestion:
        return _recargar_gestion(escuela_gestion)
    _, encargados = _filtrar_encargados(request)
    return render(
        request,
        'partials/encargado/_encargado_form_success.html',
        {'encargados': encargados}
    )


@permiso_requerido('escuela.view_encargado')
def encargado_imprimir(request):
    _, encargados = _encargados_filtrados(request)
    return respuesta_pdf(
        request, 'partials/encargado/_encargado_reporte_pdf.html',
        {'encargados': encargados}, 'Encargados.pdf'
    )


@permiso_requerido('escuela.view_encargado')
def home_encargados(request):
    breadcrumbs = [
        {'name': 'Inicio', 'url': reverse('home')},
        {'name': 'Encargados', 'url': reverse('home_encargados')},
    ]

    filtro_form, encargados = _filtrar_encargados(request)

    return render(
        request, 'encargado/encargadoHome.html',
        {
            'breadcrumbs': breadcrumbs,
            'encargados': encargados,
            'filtro_form': filtro_form,
            'form_media': filtro_form.media, ##JS,CSS que usa el Select2
        }
    )

#Se utiliza cuando se oprime buscar

@permiso_requerido('escuela.view_encargado')
def buscar_encargados(request):
    _, encargados = _filtrar_encargados(request)

    return render(
        request,
        'partials/encargado/_listado_encargados.html',
        {'encargados': encargados}
    )


#Sirve para crear y Editar
@permiso_formulario('escuela.encargado')
def encargado_form(request, pk=None):
    #Si pk es None, se crea un nuevo encargado, si no, se edita el encargado
    # con ese pk.
    instance = get_object_or_404(Encargado, pk=pk) if pk else None
    escuela_gestion = _escuela_en_gestion(request)
    # Desde "Gestionar escuela" el encargado nuevo ya va con esa escuela fija
    initial = {'escuela': escuela_gestion.pk} if escuela_gestion and not instance else None
    datos = request.POST if request.method == 'POST' else None

    form = forms.EncargadoForm(datos, instance=instance, prefix='encargado', initial=initial)
    if escuela_gestion:
        form.fields['escuela'].disabled = True
    formset = forms.TelefonoFormSet(datos, instance=instance, prefix='telefonos')

    if request.method == 'POST' and form.is_valid() and formset.is_valid():
        services.guardar_encargado(form, formset)
        return _respuesta_encargado_guardado(request)

    return render(
        request,
        'partials/encargado/_encargado_form_modal.html',
        {'form': form, 'formset': formset, 'instance': instance, 'escuela_gestion': escuela_gestion}
    )

# Cambiar Encargado: Crea un nuevo encargado y desactiva el anterior.

@permiso_requerido('escuela.add_encargado', 'escuela.change_encargado')
def encargado_cambiar(request, pk):
    activo = get_object_or_404(Encargado, pk=pk)
    nuevo_instance = Encargado(escuela=activo.escuela)
    datos = request.POST if request.method == 'POST' else None

    form = forms.EncargadoForm(datos, instance=nuevo_instance, prefix='encargado')
    #Siempre se bloquea la escuela
    form.fields['escuela'].disabled = True
    formset = forms.TelefonoFormSet(datos, instance=nuevo_instance, prefix='telefonos')

    if request.method == 'POST' and form.is_valid() and formset.is_valid():
        services.cambiar_encargado(activo, form, formset)
        return _respuesta_encargado_guardado(request)

    return render(
        request,
        'partials/encargado/_encargado_form_modal.html',
        {'form': form, 'formset': formset, 'instance': None, 'cambiar': True, 'activo': activo}
    )

# Cambiar estado de un encargado, activo/inactivo
@permiso_requerido('escuela.change_encargado')
def encargado_toggle_estado(request, pk):
    encargado = get_object_or_404(Encargado, pk=pk)

    if request.method == 'POST':
        services.alternar_estado_encargado(encargado)
        return _respuesta_encargado_guardado(request)

    #Modal de confirmación para cambiar el estado de un encargado
    return render(
        request,
        'partials/encargado/_encargado_toggle_confirm.html',
        {'encargado': encargado}
    )


# ===================== CDE =====================

# Columnas de la tabla que se pueden ordenar con clic, en el orden en que se muestran
COLUMNAS_CDE = [
    ('escuela', 'Escuela'),
    ('distrito', 'Distrito'),
    ('inicio', 'Inicio'),
    ('fin', 'Fin'),
    ('vigencia', 'Vigencia'),
]


def _cdes_filtrados(request):
    """Devuelve (filtro_form, cdes_sin_filtro_de_vigencia, cdes_finales)."""
    filtro_form = forms.CDEFilterForm(request.GET or None)
    clave, descendente = services.leer_orden_cdes(request.GET.get('orden'))
    sin_vigencia, cdes = services.filtrar_cdes(datos_filtro(filtro_form), clave, descendente)
    return filtro_form, sin_vigencia, cdes


def _contexto_cdes(request):
    """Todo lo que necesita el listado de CDE: tabla, resumen y orden."""
    filtro_form, sin_vigencia, cdes_list = _cdes_filtrados(request)
    cdes = Paginator(cdes_list, 20).get_page(request.GET.get('page'))
    services.con_dias(cdes)

    clave, descendente = services.leer_orden_cdes(request.GET.get('orden'))
    columnas = [
        {
            'clave': c,
            'etiqueta': etiqueta,
            'activa': c == clave,
            'descendente': c == clave and descendente,
            # Clic en la columna activa invierte el sentido; en otra, ordena ascendente
            'siguiente': f'-{c}' if c == clave and not descendente else c,
        }
        for c, etiqueta in COLUMNAS_CDE
    ]

    return {
        'filtro_form': filtro_form,
        'cdes': cdes,
        'resumen': services.resumen_cdes(datos_filtro(filtro_form), sin_vigencia),
        'ordenes': [(c, datos[0]) for c, datos in services.ORDENES_CDE.items()],
        'orden_clave': clave,
        'orden_descendente': descendente,
        'orden_invertido': clave if descendente else f'-{clave}',
        'columnas': columnas,
    }


def _respuesta_cde_guardado(request):
    escuela_gestion = _escuela_en_gestion(request)
    if escuela_gestion:
        return _recargar_gestion(escuela_gestion)
    return render(request, 'partials/cde/modal_form_success.html', _contexto_cdes(request))


@permiso_requerido('escuela.view_cde')
def cdeHomeView(request):
    breadcrumbs = [
        {'name': 'Inicio', 'url': reverse('home')},
        {'name': 'CDE'},
    ]
    contexto = _contexto_cdes(request)

    return render(
        request,
        'cde/cdeHome.html',
        {
            'breadcrumbs': breadcrumbs,
            'form_media': contexto['filtro_form'].media,
            **contexto,
        },
    )


@permiso_requerido('escuela.view_cde')
def buscar_cdes(request):
    return render(request, 'partials/cde/tabla.html', _contexto_cdes(request))


@permiso_formulario('escuela.cde')
def cde_form(request, pk=None):
    instance = get_object_or_404(CDE, pk=pk) if pk else None
    escuela_gestion = _escuela_en_gestion(request)
    # Desde "Gestionar escuela" el CDE nuevo ya va con esa escuela fija
    initial = {'escuela': escuela_gestion.pk} if escuela_gestion and not instance else None
    datos = request.POST if request.method == 'POST' else None

    form = forms.CDEForm(datos, instance=instance, initial=initial)
    if escuela_gestion:
        form.fields['escuela'].disabled = True

    if request.method == 'POST' and form.is_valid():
        form.save()
        return _respuesta_cde_guardado(request)

    return render(
        request,
        'partials/cde/modal_form.html',
        {'form': form, 'instance': instance, 'escuela_gestion': escuela_gestion},
    )


@permiso_requerido('escuela.delete_cde')
def cde_eliminar(request, pk):
    instance = get_object_or_404(CDE, pk=pk)

    if request.method == 'POST':
        instance.delete()
        return _respuesta_cde_guardado(request)

    return render(
        request,
        'partials/cde/modal_delete.html',
        {'instance': instance},
    )


@permiso_requerido('escuela.view_cde')
def cde_imprimir(request):
    _, _, cdes = _cdes_filtrados(request)
    return respuesta_pdf(
        request, 'partials/cde/reporte_pdf.html',
        {'cdes': services.con_dias(list(cdes))}, 'CDE.pdf'
    )


# ===================== Escuelas =====================

def _escuelas_filtradas(request):
    filtro_form = forms.FiltrarEscuelasForm(request.GET or None)
    return filtro_form, services.filtrar_escuelas(datos_filtro(filtro_form))


def _filtrar_escuelas(request):
    filtro_form, escuelas_list = _escuelas_filtradas(request)

    # Sin filtros no se lista nada: la página arranca solo con el buscador.
    if not any(datos_filtro(filtro_form).values()):
        return filtro_form, None

    paginator = Paginator(services.con_encargado_y_cde(escuelas_list), 20)
    escuelas = paginator.get_page(request.GET.get('page'))

    return filtro_form, escuelas


def _respuesta_escuela_guardada(request):
    escuela_gestion = _escuela_en_gestion(request)
    if escuela_gestion:
        return _recargar_gestion(escuela_gestion)
    _, escuelas = _filtrar_escuelas(request)
    return render(
        request,
        'partials/escuela/_escuela_form_success.html',
        {'escuelas': escuelas}
    )


# --- Imprimir: reportes individuales, con los filtros del buscador ---

@permiso_requerido('escuela.view_escuela')
def escuela_imprimir(request):
    _, escuelas = _escuelas_filtradas(request)
    return respuesta_pdf(
        request, 'partials/escuela/_escuela_reporte_pdf.html',
        {'escuelas': escuelas}, 'Escuelas.pdf'
    )


@permiso_requerido('escuela.view_escuela', 'escuela.view_encargado')
def escuela_imprimir_encargados(request):
    _, escuelas = _escuelas_filtradas(request)
    # ?anteriores=1 agrega los encargados inactivos (debajo del activo de cada escuela)
    con_anteriores = request.GET.get('anteriores') == '1'

    return respuesta_pdf(
        request, 'partials/encargado/_encargado_reporte_pdf.html',
        {'encargados': services.encargados_de_escuelas(escuelas, con_anteriores)},
        'Encargados_con_anteriores.pdf' if con_anteriores else 'Encargados.pdf'
    )


@permiso_requerido('escuela.view_escuela', 'escuela.view_cde')
def escuela_imprimir_cde(request):
    _, escuelas = _escuelas_filtradas(request)
    return respuesta_pdf(
        request, 'partials/cde/reporte_pdf.html',
        {'cdes': services.cdes_de_escuelas(escuelas)}, 'CDE.pdf'
    )


# --- Imprimir: reporte general (escuela + encargado + CDE en una sola hoja) ---

@permiso_requerido('escuela.view_escuela')
def escuela_imprimir_general(request):
    _, escuelas = _escuelas_filtradas(request)
    return respuesta_pdf(
        request, 'partials/escuela/_escuela_reporte_general_pdf.html',
        {'escuelas': services.con_encargado_y_cde(escuelas)}, 'Reporte_general_escuelas.pdf'
    )


# --- Imprimir: ficha de una sola escuela ---

@permiso_requerido('escuela.view_escuela')
def escuela_imprimir_ficha(request, pk):
    escuela = get_object_or_404(Escuela.objects.select_related('distrito'), pk=pk)
    return respuesta_pdf(
        request, 'partials/escuela/_escuela_ficha_pdf.html',
        {'escuela': escuela, **services.ficha_escuela(escuela)},
        f'Ficha_{escuela.codigo}.pdf'
    )


@permiso_requerido('escuela.view_escuela')
def home_escuelas(request):
    breadcrumbs = [
        {'name': 'Inicio', 'url': reverse('home')},
        {'name': 'Escuelas'},
    ]

    filtro_form, escuelas = _filtrar_escuelas(request)

    return render(
        request, 'escuela/escuelaHome.html',
        {
            'breadcrumbs': breadcrumbs,
            'escuelas': escuelas,
            'filtro_form': filtro_form,
            'form_media': filtro_form.media,
        }
    )


@permiso_requerido('escuela.view_escuela')
def buscar_escuelas(request):
    _, escuelas = _filtrar_escuelas(request)

    return render(
        request,
        'partials/escuela/_listado_escuelas.html',
        {'escuelas': escuelas}
    )


# Página completa de una escuela: datos, encargado (y anteriores) y CDE
@permiso_requerido('escuela.view_escuela')
def escuela_gestionar(request, pk):
    escuela = get_object_or_404(Escuela.objects.select_related('distrito'), pk=pk)

    breadcrumbs = [
        {'name': 'Inicio', 'url': reverse('home')},
        {'name': 'Escuelas', 'url': reverse('home_escuelas')},
        {'name': f"{escuela.codigo} · {escuela.nombre_corto}"},
    ]

    return render(
        request,
        'escuela/escuelaGestionar.html',
        {
            'breadcrumbs': breadcrumbs,
            'escuela': escuela,
            **services.ficha_escuela(escuela),
            # JS/CSS de select2 que usan los modales de escuela y encargado
            'form_media': forms.EscuelaForm().media,
        }
    )


#Sirve para crear y Editar
@permiso_formulario('escuela.escuela')
def escuela_form(request, pk=None):
    instance = get_object_or_404(Escuela, pk=pk) if pk else None
    if request.method == 'POST':
        form = forms.EscuelaForm(request.POST, instance=instance, prefix='escuela')
        if form.is_valid():
            escuela = form.save()
            # Escuela nueva: se abre su página para agregarle encargado y CDE
            if instance is None:
                return _recargar_gestion(escuela)
            return _respuesta_escuela_guardada(request)
    else:
        form = forms.EscuelaForm(instance=instance, prefix='escuela')

    return render(
        request,
        'partials/escuela/_escuela_form_modal.html',
        {'form': form, 'instance': instance}
    )


@permiso_requerido('escuela.change_escuela')
def escuela_toggle_estado(request, pk):
    escuela = get_object_or_404(Escuela, pk=pk)

    if request.method == 'POST':
        services.alternar_estado_escuela(escuela)
        return _respuesta_escuela_guardada(request)

    #Modal de confirmación para cambiar el estado de una escuela
    return render(
        request,
        'partials/escuela/_escuela_toggle_confirm.html',
        {'escuela': escuela}
    )
