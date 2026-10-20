"""Lógica de gestión de usuarios y grupos.

Las funciones de este módulo no reciben el request: trabajan con datos ya
validados (el cleaned_data de los formularios) y con modelos.
"""
from collections import defaultdict

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models import Count, Prefetch, Q
from django.utils.text import capfirst

from main.forms import NOMBRES_APPS
from .forms import ACCIONES_PERMISO, permisos_gestionables

User = get_user_model()


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------

def puede_gestionar(editor, usuario):
    """Un administrador que no es superusuario no puede tocar cuentas de superusuario."""
    return editor.is_superuser or not usuario.is_superuser


def filtrar_usuarios(filtros):
    usuarios = User.objects.prefetch_related(
        Prefetch('groups', queryset=Group.objects.order_by('name')),
    ).order_by('-is_active', 'username')

    q = (filtros.get('q') or '').strip()
    grupo = filtros.get('grupo')
    rol = filtros.get('rol')
    estado = filtros.get('estado')

    if q:
        usuarios = usuarios.filter(
            Q(username__icontains=q) | Q(first_name__icontains=q)
            | Q(last_name__icontains=q) | Q(email__icontains=q)
        )
    if grupo:
        usuarios = usuarios.filter(groups=grupo)
    if rol == 'superusuario':
        usuarios = usuarios.filter(is_superuser=True)
    elif rol == 'administrador':
        usuarios = usuarios.filter(is_staff=True, is_superuser=False)
    elif rol == 'usuario':
        usuarios = usuarios.filter(is_staff=False, is_superuser=False)
    if estado:
        usuarios = usuarios.filter(is_active=estado == 'activo')
    return usuarios


def alternar_estado_usuario(usuario):
    usuario.is_active = not usuario.is_active
    usuario.save(update_fields=['is_active'])
    return usuario


# ---------------------------------------------------------------------------
# Grupos
# ---------------------------------------------------------------------------

def grupos_con_conteos():
    return Group.objects.annotate(
        total_usuarios=Count('user', distinct=True),
        total_permisos=Count('permissions', distinct=True),
    )


def filtrar_grupos(filtros):
    grupos = grupos_con_conteos().prefetch_related(
        Prefetch('user_set', queryset=User.objects.order_by('username'), to_attr='usuarios'),
    ).order_by('name')

    q = (filtros.get('q') or '').strip()
    usuario = filtros.get('usuario')
    if q:
        grupos = grupos.filter(name__icontains=q)
    if usuario:
        grupos = grupos.filter(pk__in=usuario.groups.values('pk'))
    return grupos


def resumen_permisos(grupos):
    """Para cada grupo, sus permisos por módulo: [('Escuelas · Escuelas', 'Ver, Agregar'), ...]."""
    acciones = dict(ACCIONES_PERMISO)
    permisos = permisos_gestionables().filter(group__in=grupos).values_list(
        'group', 'codename', 'content_type__app_label', 'content_type__model', 'name',
    ).order_by('content_type__app_label', 'content_type__model')

    por_grupo = defaultdict(lambda: defaultdict(list))
    for grupo_id, codename, app_label, modelo, nombre in permisos:
        accion = codename.split('_', 1)[0]
        clase = User._meta.apps.get_model(app_label, modelo)
        modulo = f'{NOMBRES_APPS.get(app_label, app_label)} · {capfirst(clase._meta.verbose_name_plural)}'
        por_grupo[grupo_id][modulo].append(acciones.get(accion, nombre) if codename == f'{accion}_{modelo}' else nombre)

    for grupo in grupos:
        grupo.resumen_permisos = [(modulo, ', '.join(lista)) for modulo, lista in por_grupo[grupo.pk].items()]
    return grupos
