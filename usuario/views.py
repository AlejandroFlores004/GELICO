from collections import defaultdict

from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.text import capfirst
from weasyprint import HTML

from main.forms import NOMBRES_APPS
from main.permisos import staff_requerido
from .forms import (
    ACCIONES_PERMISO, ContrasenaForm, FiltrarGruposForm, FiltrarUsuariosForm, GrupoForm, UsuarioForm,
    permisos_gestionables,
)

User = get_user_model()


def _usuario_editable(request, pk):
    usuario = get_object_or_404(User, pk=pk)
    # Un administrador que no es superusuario no puede tocar cuentas de superusuario.
    if usuario.is_superuser and not request.user.is_superuser:
        raise PermissionDenied
    return usuario


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------

def _usuarios_filtrados(request, paginar=True):
    filtro_form = FiltrarUsuariosForm(request.GET or None)
    usuarios = User.objects.prefetch_related(
        Prefetch('groups', queryset=Group.objects.order_by('name')),
    ).order_by('-is_active', 'username')

    if filtro_form.is_valid():
        q = filtro_form.cleaned_data['q'].strip()
        grupo = filtro_form.cleaned_data['grupo']
        rol = filtro_form.cleaned_data['rol']
        estado = filtro_form.cleaned_data['estado']
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

    if paginar:
        usuarios = Paginator(usuarios, 20).get_page(request.GET.get('page'))
    return filtro_form, usuarios


def _tabla_usuarios(request, plantilla, contexto=None):
    _, usuarios = _usuarios_filtrados(request)
    return render(request, plantilla, {'usuarios': usuarios, **(contexto or {})})


@staff_requerido
def usuariosHomeView(request):
    filtro_form, usuarios = _usuarios_filtrados(request)
    return render(request, 'usuario/usuariosHome.html', {
        'breadcrumbs': [
            {'name': 'Inicio', 'url': reverse('home')},
            {'name': 'Usuarios', 'url': reverse('home_usuarios')},
        ],
        'filtro_form': filtro_form,
        'form_media': filtro_form.media,
        'usuarios': usuarios,
    })


@staff_requerido
def buscar_usuarios(request):
    return _tabla_usuarios(request, 'partials/usuario/tabla.html')


@staff_requerido
def usuario_form(request, pk=None):
    instance = _usuario_editable(request, pk) if pk else None

    if request.method == 'POST':
        form = UsuarioForm(request.POST, instance=instance, editor=request.user)
        if form.is_valid():
            form.save()
            return _tabla_usuarios(request, 'partials/usuario/modal_form_success.html')
    else:
        form = UsuarioForm(instance=instance, editor=request.user)

    return render(request, 'partials/usuario/modal_form.html', {'form': form, 'instance': instance})


@staff_requerido
def usuario_contrasena(request, pk):
    instance = _usuario_editable(request, pk)

    if request.method == 'POST':
        form = ContrasenaForm(instance, request.POST)
        if form.is_valid():
            form.save()
            if instance.pk == request.user.pk:
                # Sin esto, cambiar la contraseña propia cierra la sesión actual.
                update_session_auth_hash(request, instance)
            return _tabla_usuarios(request, 'partials/usuario/modal_form_success.html')
    else:
        form = ContrasenaForm(instance)

    return render(request, 'partials/usuario/modal_contrasena.html', {'form': form, 'instance': instance})


@staff_requerido
def usuario_toggle_estado(request, pk):
    instance = _usuario_editable(request, pk)
    es_propio = instance.pk == request.user.pk

    if request.method == 'POST' and not es_propio:
        instance.is_active = not instance.is_active
        instance.save(update_fields=['is_active'])
        return _tabla_usuarios(request, 'partials/usuario/modal_form_success.html')

    return render(request, 'partials/usuario/modal_toggle.html', {'instance': instance, 'es_propio': es_propio})


@staff_requerido
def usuario_eliminar(request, pk):
    instance = _usuario_editable(request, pk)
    es_propio = instance.pk == request.user.pk

    if request.method == 'POST' and not es_propio:
        instance.delete()
        return _tabla_usuarios(request, 'partials/usuario/modal_form_success.html')

    return render(request, 'partials/usuario/modal_delete.html', {'instance': instance, 'es_propio': es_propio})


@staff_requerido
def usuario_imprimir(request):
    _, usuarios = _usuarios_filtrados(request, paginar=False)
    html_string = render_to_string('partials/usuario/reporte_pdf.html', {
        'usuarios': usuarios,
        'fecha_impresion': timezone.localtime(),
    })
    pdf = HTML(string=html_string, base_url=request.build_absolute_uri('/')).write_pdf()

    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="usuarios.pdf"'
    return response


# ---------------------------------------------------------------------------
# Grupos
# ---------------------------------------------------------------------------

def _grupos_filtrados(request, paginar=True):
    filtro_form = FiltrarGruposForm(request.GET or None)
    grupos = Group.objects.annotate(
        total_usuarios=Count('user', distinct=True),
        total_permisos=Count('permissions', distinct=True),
    ).prefetch_related(
        Prefetch('user_set', queryset=User.objects.order_by('username'), to_attr='usuarios'),
    ).order_by('name')

    if filtro_form.is_valid():
        q = filtro_form.cleaned_data['q'].strip()
        usuario = filtro_form.cleaned_data['usuario']
        if q:
            grupos = grupos.filter(name__icontains=q)
        if usuario:
            grupos = grupos.filter(pk__in=usuario.groups.values('pk'))

    if paginar:
        grupos = Paginator(grupos, 20).get_page(request.GET.get('page'))
    return filtro_form, grupos


def _tabla_grupos(request, plantilla):
    _, grupos = _grupos_filtrados(request)
    return render(request, plantilla, {'grupos': grupos})


def _resumen_permisos(grupos):
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


@staff_requerido
def gruposHomeView(request):
    filtro_form, grupos = _grupos_filtrados(request)
    return render(request, 'grupo/gruposHome.html', {
        'breadcrumbs': [
            {'name': 'Inicio', 'url': reverse('home')},
            {'name': 'Grupos', 'url': reverse('home_grupos')},
        ],
        'filtro_form': filtro_form,
        'form_media': filtro_form.media,
        'grupos': grupos,
    })


@staff_requerido
def buscar_grupos(request):
    return _tabla_grupos(request, 'partials/grupo/tabla.html')


@staff_requerido
def grupo_form(request, pk=None):
    instance = get_object_or_404(Group, pk=pk) if pk else None

    if request.method == 'POST':
        form = GrupoForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            return _tabla_grupos(request, 'partials/grupo/modal_form_success.html')
    else:
        form = GrupoForm(instance=instance)

    return render(request, 'partials/grupo/modal_form.html', {
        'form': form,
        'instance': instance,
        'acciones_permiso': ACCIONES_PERMISO,
    })


@staff_requerido
def grupo_eliminar(request, pk):
    instance = get_object_or_404(
        Group.objects.annotate(total_usuarios=Count('user', distinct=True), total_permisos=Count('permissions', distinct=True)),
        pk=pk,
    )

    if request.method == 'POST':
        instance.delete()
        return _tabla_grupos(request, 'partials/grupo/modal_form_success.html')

    return render(request, 'partials/grupo/modal_delete.html', {'instance': instance})


@staff_requerido
def grupo_imprimir(request):
    _, grupos = _grupos_filtrados(request, paginar=False)
    html_string = render_to_string('partials/grupo/reporte_pdf.html', {
        'grupos': _resumen_permisos(list(grupos)),
        'fecha_impresion': timezone.localtime(),
    })
    pdf = HTML(string=html_string, base_url=request.build_absolute_uri('/')).write_pdf()

    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="grupos.pdf"'
    return response
