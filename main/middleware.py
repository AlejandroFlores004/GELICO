import json

from django.contrib import messages
from django.contrib.auth.middleware import LoginRequiredMiddleware
from django.contrib.auth.views import redirect_to_login
from django_htmx.http import HttpResponseClientRedirect

# Rutas de terceros que no deben pasar por el login (no se pueden decorar).
RUTAS_PUBLICAS = ('/__reload__/',)


class SesionRequeridaMiddleware(LoginRequiredMiddleware):
    """Exige sesión iniciada en todas las vistas, salvo las marcadas con @login_not_required.

    En peticiones htmx (ej: la sesión expiró y se abre un modal) un 302 normal
    metería la página de login dentro del modal, así que se redirige la página
    completa y, al volver, se regresa a la página donde estaba el usuario.
    """

    def process_view(self, request, view_func, view_args, view_kwargs):
        if request.path.startswith(RUTAS_PUBLICAS):
            return None
        return super().process_view(request, view_func, view_args, view_kwargs)

    def handle_no_permission(self, request, view_func):
        if request.htmx:
            destino = request.htmx.current_url_abs_path or request.get_full_path()
            respuesta = redirect_to_login(destino, self.get_login_url(view_func), self.get_redirect_field_name(view_func))
            return HttpResponseClientRedirect(respuesta.url)
        return super().handle_no_permission(request, view_func)


# Evento htmx que el contenedor de avisos escucha para mostrar cada mensaje.
EVENTO_AVISO = 'aviso'
# Evento que vuelve a cargar la campana de notificaciones (tras guardar algo pueden cambiar).
EVENTO_NOTIFICACIONES = 'notificaciones-actualizar'


def _leer_disparadores(valor):
    """El header HX-Trigger como dict: acepta JSON o una lista de eventos separados por coma."""
    if not valor:
        return {}
    if valor.lstrip().startswith('{'):
        return json.loads(valor)
    return {evento.strip(): None for evento in valor.split(',') if evento.strip()}


class MensajesHtmxMiddleware:
    """Manda los mensajes de django.contrib.messages como avisos en peticiones htmx.

    Las vistas solo hacen messages.success(request, '...'). En una petición htmx el
    mensaje viaja en el header HX-Trigger (evento "aviso") y base.html lo muestra arriba
    a la derecha. Si la respuesta recarga la página (HX-Redirect), el mensaje se queda
    guardado y se muestra al cargar la página nueva, como en una petición normal.

    Debe ir después de MessageMiddleware en MIDDLEWARE.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not getattr(request, 'htmx', False) or response.has_header('HX-Redirect') or response.status_code >= 300:
            return response

        avisos = [{'nivel': mensaje.level_tag, 'texto': str(mensaje)} for mensaje in messages.get_messages(request)]
        if avisos:
            disparadores = _leer_disparadores(response.get('HX-Trigger'))
            disparadores[EVENTO_AVISO] = {'avisos': avisos}
            disparadores[EVENTO_NOTIFICACIONES] = None
            response['HX-Trigger'] = json.dumps(disparadores)
        return response
