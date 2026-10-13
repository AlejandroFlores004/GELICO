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
