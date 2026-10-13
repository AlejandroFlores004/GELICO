"""Decoradores de acceso para las vistas de GELICO.

La sesión la exige SesionRequeridaMiddleware en todo el sitio; estos decoradores
agregan el control por permiso. Si el usuario no cumple se lanza PermissionDenied,
que Django responde con la página 403.html (o con un aviso, si la petición es htmx).
"""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def _exigir(prueba):
    def decorador(vista):
        @wraps(vista)
        @login_required(login_url='login')
        def envoltura(request, *args, **kwargs):
            if not prueba(request, kwargs):
                raise PermissionDenied
            return vista(request, *args, **kwargs)
        return envoltura
    return decorador


def permiso_requerido(*permisos, cualquiera=False):
    """Exige todos los permisos indicados ('app.accion_modelo'), o al menos uno con cualquiera=True."""
    if cualquiera:
        return _exigir(lambda request, kwargs: any(request.user.has_perm(p) for p in permisos))
    return _exigir(lambda request, kwargs: request.user.has_perms(permisos))


def permiso_formulario(modelo):
    """Para las vistas que crean y editan con la misma función (pk opcional):
    exige 'app.add_modelo' al crear y 'app.change_modelo' al editar."""
    app, nombre = modelo.split('.')

    def prueba(request, kwargs):
        accion = 'change' if kwargs.get('pk') is not None else 'add'
        return request.user.has_perm(f'{app}.{accion}_{nombre}')
    return _exigir(prueba)


def staff_requerido(vista):
    """Gestionar usuarios, grupos y consultar la auditoría queda reservado a administradores (is_staff)."""
    return _exigir(lambda request, kwargs: request.user.is_staff)(vista)
