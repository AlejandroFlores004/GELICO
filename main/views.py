from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_not_required, login_required
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from easyaudit.models import CRUDEvent

from . import services
from .forms import FiltrarAuditoriaForm, ReportesForm
from .notificaciones import NIVELES, agrupar_por_categoria, notificaciones_de
from .pdf import datos_filtro, respuesta_pdf
from .permisos import staff_requerido


@login_required(login_url='login')
def home_view(request):
    hoy = timezone.localdate()
    anios = services.anios_disponibles()
    anio = services.elegir_anio(request.GET.get('anio'), anios)

    return render(request, 'home.html', {
        'breadcrumbs': [{'name': 'Inicio', 'url': reverse('home')}],
        'hoy': hoy,
        'anios': anios,
        'anio': anio,
        **services.panel_inicio(anio, hoy),
    })

# ---------------------------------------------------------------------------
# Notificaciones. Sin decorador de permisos: cualquier usuario con sesión las ve,
# y cada uno solo recibe las de los módulos que tiene permitidos.
# ---------------------------------------------------------------------------

LIMITE_CAMPANA = 6


def notificaciones_campana(request):
    """Campana del navbar con el conteo y las más urgentes."""
    notificaciones = notificaciones_de(request.user)
    return render(request, 'partials/notificaciones/_campana.html', {
        'notificaciones': notificaciones[:LIMITE_CAMPANA],
        'total': len(notificaciones),
        'urgentes': sum(notificacion.nivel == 'error' for notificacion in notificaciones),
    })


def notificacionesHomeView(request):
    notificaciones = notificaciones_de(request.user)
    return render(request, 'notificaciones/notificacionesHome.html', {
        'breadcrumbs': [
            {'name': 'Inicio', 'url': reverse('home')},
            {'name': 'Notificaciones'},
        ],
        'grupos': agrupar_por_categoria(notificaciones),
        'total': len(notificaciones),
        'por_nivel': {nivel: sum(n.nivel == nivel for n in notificaciones) for nivel in NIVELES},
    })


# ---------------------------------------------------------------------------
# Reportes: acceso directo a todos los "Imprimir" del sistema. Sin decorador de
# permisos: la página solo muestra los reportes de los módulos que el usuario
# tiene permitidos, y cada vista de impresión vuelve a validar su permiso.
# ---------------------------------------------------------------------------

# Reportes de un solo registro: campo del selector -> vista de impresión (recibe el pk)
REPORTES_INDIVIDUALES = {
    'ficha_escuela': ('escuela', 'escuela_imprimir_ficha'),
    'asignacion': ('asignacion', 'asignacion_imprimir'),
}


def reportesHomeView(request):
    form = ReportesForm()
    return render(request, 'reportes/reportesHome.html', {
        'breadcrumbs': [
            {'name': 'Inicio', 'url': reverse('home')},
            {'name': 'Reportes'},
        ],
        'form': form,
        'form_media': form.media,
        'vistas_auditoria': VISTAS_AUDITORIA,
    })


def reporte_individual(request, reporte):
    """Lleva del selector de la página de Reportes al PDF del registro elegido."""
    if reporte not in REPORTES_INDIVIDUALES:
        raise Http404
    campo, url_name = REPORTES_INDIVIDUALES[reporte]
    pk = request.GET.get(campo, '')
    if not pk.isdigit():
        messages.error(request, 'Elige un registro para imprimir el reporte.')
        return redirect('home_reportes')
    return redirect(url_name, pk=int(pk))


@login_not_required
def login_view(request):
    destino = request.POST.get('next') or request.GET.get('next', '')
    # Solo se vuelve a rutas de este mismo sitio (evita redirecciones abiertas).
    if not url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        destino = reverse('home')

    if request.user.is_authenticated:
        return redirect(destino)

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect(destino)
        else:
            messages.error(request, "Usuario o contraseña incorrectos.")

    return render(request, "registration/login.html", {'next': request.POST.get('next') or request.GET.get('next', '')})


@login_not_required
@require_POST
def logout_view(request):
    logout(request)
    messages.success(request, "Has cerrado sesión correctamente.")
    return redirect("login")


@login_not_required
def terminos_view(request):
    """Términos y condiciones de uso. Pública: se enlaza desde el login."""
    return render(request, "terminos.html")

# ---------------------------------------------------------------------------
# Auditoría: consulta de la bitácora que registra django-easy-audit.
# ---------------------------------------------------------------------------

VISTAS_AUDITORIA = {
    'cambios': {
        'titulo': 'Cambios en registros',
        'descripcion': 'Creaciones, modificaciones y eliminaciones de datos.',
        'campos': ['q', 'usuario', 'modulo', 'accion', 'desde', 'hasta'],
        'placeholder': 'Nombre del registro o ID',
    },
    'accesos': {
        'titulo': 'Accesos al sistema',
        'descripcion': 'Inicios y cierres de sesión, e intentos fallidos.',
        'campos': ['q', 'usuario', 'tipo_acceso', 'desde', 'hasta'],
        'placeholder': 'Usuario o dirección IP',
    },
    'solicitudes': {
        'titulo': 'Páginas visitadas',
        'descripcion': 'Cada página o acción solicitada por los usuarios.',
        'campos': ['q', 'usuario', 'metodo', 'desde', 'hasta'],
        'placeholder': 'Ruta, parámetros o dirección IP',
    },
}
LIMITE_REPORTE_AUDITORIA = 500


def _vista_auditoria(request):
    vista = request.GET.get('vista')
    return vista if vista in VISTAS_AUDITORIA else 'cambios'


def _auditoria_filtrada(request, vista):
    """Formulario y eventos filtrados de la pestaña activa, SIN paginar (lo reutilizan el listado y el imprimir)."""
    filtro_form = FiltrarAuditoriaForm(request.GET or None)
    filtro_form.fields['q'].widget.attrs['placeholder'] = VISTAS_AUDITORIA[vista]['placeholder']
    return filtro_form, services.filtrar_auditoria(vista, datos_filtro(filtro_form))


def _paginar_auditoria(request, eventos, vista):
    eventos = Paginator(eventos, 25).get_page(request.GET.get('page'))
    eventos.paginas = list(eventos.paginator.get_elided_page_range(eventos.number, on_each_side=2, on_ends=1))
    services.decorar_eventos(eventos, vista)
    return eventos


def _resumen_filtros(filtro_form, vista):
    """Lista (etiqueta, valor) de los filtros aplicados, para el encabezado del PDF."""
    if not filtro_form.is_valid():
        return []
    resumen = []
    for nombre in VISTAS_AUDITORIA[vista]['campos']:
        valor = filtro_form.cleaned_data.get(nombre)
        if valor in (None, ''):
            continue
        campo = filtro_form.fields[nombre]
        if hasattr(campo, 'label_from_instance'):
            texto = campo.label_from_instance(valor)
        elif hasattr(valor, 'strftime'):
            texto = valor.strftime('%d/%m/%Y')
        elif hasattr(campo, 'choices'):
            texto = dict(campo.choices).get(valor, valor)
        else:
            texto = valor
        resumen.append((campo.label, texto))
    return resumen


@staff_requerido
def auditoriaHomeView(request):
    vista = _vista_auditoria(request)
    filtro_form, eventos = _auditoria_filtrada(request, vista)
    return render(request, 'auditoria/auditoriaHome.html', {
        'breadcrumbs': [
            {'name': 'Inicio', 'url': reverse('home')},
            {'name': 'Auditoría', 'url': reverse('home_auditoria')},
        ],
        'vista': vista,
        'vista_actual': VISTAS_AUDITORIA[vista],
        'vistas': VISTAS_AUDITORIA,
        'filtro_form': filtro_form,
        'campos_filtro': [filtro_form[nombre] for nombre in VISTAS_AUDITORIA[vista]['campos']],
        'form_media': filtro_form.media,
        'eventos': _paginar_auditoria(request, eventos, vista),
        'indicadores': services.indicadores_auditoria(),
    })


@staff_requerido
def buscar_auditoria(request):
    vista = _vista_auditoria(request)
    filtro_form, eventos = _auditoria_filtrada(request, vista)
    return render(request, 'partials/auditoria/_tabla.html', {
        'vista': vista,
        'vista_actual': VISTAS_AUDITORIA[vista],
        'filtro_form': filtro_form,
        'eventos': _paginar_auditoria(request, eventos, vista),
    })


@staff_requerido
def auditoria_detalle(request, pk):
    evento = get_object_or_404(CRUDEvent.objects.select_related('content_type', 'user'), pk=pk)
    services.decorar_eventos([evento], 'cambios')
    tipo_detalle, filas = services.detalle_cambio(evento)
    historial = services.historial_registro(evento)

    return render(request, 'partials/auditoria/_modal_detalle.html', {
        'evento': evento,
        'tipo_detalle': tipo_detalle,
        'filas': filas,
        'historial': services.decorar_eventos(list(historial[:10]), 'cambios'),
        'total_historial': historial.count(),
    })


@staff_requerido
def auditoria_imprimir(request):
    vista = _vista_auditoria(request)
    filtro_form, eventos = _auditoria_filtrada(request, vista)
    return respuesta_pdf(request, 'partials/auditoria/_reporte_pdf.html', {
        'vista': vista,
        'titulo': VISTAS_AUDITORIA[vista]['titulo'],
        'eventos': services.decorar_eventos(list(eventos[:LIMITE_REPORTE_AUDITORIA]), vista),
        'total': eventos.count(),
        'limite': LIMITE_REPORTE_AUDITORIA,
        'filtros': _resumen_filtros(filtro_form, vista),
    }, f'auditoria-{vista}.pdf')
