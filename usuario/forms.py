from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.text import capfirst
from django_select2.forms import Select2Widget

from main.forms import NOMBRES_APPS

User = get_user_model()

# Columnas de la matriz de permisos, en el orden en que se muestran.
ACCIONES_PERMISO = [
    ('view', 'Ver'),
    ('add', 'Agregar'),
    ('change', 'Modificar'),
    ('delete', 'Eliminar'),
]

ROLES = [
    ('', ''),
    ('superusuario', 'Superusuario'),
    ('administrador', 'Administrador'),
    ('usuario', 'Usuario'),
]

ESTADOS = [
    ('', ''),
    ('activo', 'Activo'),
    ('inactivo', 'Inactivo'),
]

CLASE_INPUT = 'input input-bordered w-full'


def permisos_gestionables():
    """Permisos que tiene sentido asignar desde GELICO: los de las apps del proyecto y los de usuarios/grupos."""
    content_types = ContentType.objects.filter(
        Q(app_label__in=['escuela', 'programacion', 'liquidacion'])
        | Q(app_label='auth', model__in=['user', 'group'])
    )
    # Se omiten los de modelos ya eliminados del código (quedan huérfanos en la BD).
    vigentes = [content_type.pk for content_type in content_types if content_type.model_class()]
    return Permission.objects.filter(content_type__in=vigentes).select_related('content_type')


def _select2(placeholder, buscar=True):
    attrs = {
        'data-placeholder': placeholder,
        'style': 'width: 100%',
        'class': 'select2-daisy',
        'data-allow-clear': 'true',
    }
    if not buscar:
        attrs['data-minimum-results-for-search'] = 'Infinity'
    return Select2Widget(attrs=attrs)


class UsuarioCheckboxField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, usuario):
        nombre = usuario.get_full_name()
        etiqueta = f'{nombre} ({usuario.username})' if nombre else usuario.username
        return etiqueta if usuario.is_active else f'{etiqueta} · inactivo'


class FiltrarUsuariosForm(forms.Form):
    q = forms.CharField(
        required=False,
        label='Usuario',
        widget=forms.TextInput(attrs={'class': CLASE_INPUT, 'placeholder': 'Usuario, nombre o correo'}),
    )
    grupo = forms.ModelChoiceField(
        queryset=Group.objects.order_by('name'),
        required=False,
        label='Grupo',
        widget=_select2('Todos los grupos'),
    )
    rol = forms.ChoiceField(
        choices=ROLES,
        required=False,
        label='Rol',
        widget=_select2('Todos los roles', buscar=False),
    )
    estado = forms.ChoiceField(
        choices=ESTADOS,
        required=False,
        label='Estado',
        widget=_select2('Todos', buscar=False),
    )


def validar_correo(email, excluir_pk=None):
    """El correo es obligatorio y único sin distinguir mayúsculas. El User de Django lo deja opcional y
    repetible; aquí (y con el índice único de la migración usuario.0001) se exige en todo el sistema."""
    email = (email or '').strip()
    if not email:
        raise ValidationError('El correo electrónico es obligatorio.')
    if User.objects.filter(email__iexact=email).exclude(pk=excluir_pk).exists():
        raise ValidationError('Ya existe otro usuario con este correo.')
    return email


class UsuarioForm(forms.ModelForm):
    password1 = forms.CharField(
        label='Contraseña',
        strip=False,
        required=False,
        widget=forms.PasswordInput(attrs={'class': CLASE_INPUT, 'autocomplete': 'new-password'}),
        help_text='Mínimo 8 caracteres, que no sea solo números ni una contraseña común.',
    )
    password2 = forms.CharField(
        label='Confirmar contraseña',
        strip=False,
        required=False,
        widget=forms.PasswordInput(attrs={'class': CLASE_INPUT, 'autocomplete': 'new-password'}),
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'groups', 'is_active', 'is_staff', 'is_superuser']
        labels = {
            'username': 'Nombre de usuario',
            'first_name': 'Nombres',
            'last_name': 'Apellidos',
            'email': 'Correo electrónico',
            'groups': 'Grupos',
            'is_active': 'Cuenta activa',
            'is_staff': 'Administrador',
            'is_superuser': 'Superusuario',
        }
        help_texts = {
            'username': 'Con el que inicia sesión. Solo letras, números y @ . + - _',
            'groups': 'El usuario recibe los permisos de todos los grupos marcados.',
            'is_active': 'Si se desactiva, no podrá iniciar sesión pero se conserva su historial.',
            'is_staff': 'Puede gestionar usuarios y grupos, y entrar al sitio de desarrollo.',
            'is_superuser': 'Tiene todos los permisos sin necesidad de asignárselos.',
        }
        widgets = {
            'username': forms.TextInput(attrs={'class': CLASE_INPUT, 'autocomplete': 'off'}),
            'first_name': forms.TextInput(attrs={'class': CLASE_INPUT}),
            'last_name': forms.TextInput(attrs={'class': CLASE_INPUT}),
            'email': forms.EmailInput(attrs={'class': CLASE_INPUT, 'placeholder': 'nombre@ejemplo.com'}),
            'groups': forms.CheckboxSelectMultiple(attrs={'class': 'checkbox checkbox-sm checkbox-primary'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'toggle toggle-success'}),
            'is_staff': forms.CheckboxInput(attrs={'class': 'toggle toggle-primary'}),
            'is_superuser': forms.CheckboxInput(attrs={'class': 'toggle toggle-warning'}),
        }

    def __init__(self, *args, editor, **kwargs):
        super().__init__(*args, **kwargs)
        self.editor = editor
        self.fields['groups'].queryset = Group.objects.order_by('name')
        self.fields['groups'].required = False
        self.fields['email'].required = True
        self.fields['email'].error_messages['required'] = 'El correo electrónico es obligatorio.'

        if self.instance.pk:
            # La contraseña de un usuario existente se cambia desde su propio modal.
            del self.fields['password1']
            del self.fields['password2']
        else:
            self.fields['password1'].required = True
            self.fields['password2'].required = True
            self.initial.setdefault('is_active', True)

        # Solo un superusuario puede crear o quitar superusuarios.
        if not editor.is_superuser:
            del self.fields['is_superuser']

    def clean_email(self):
        return validar_correo(self.cleaned_data.get('email'), self.instance.pk)

    def clean(self):
        cleaned_data = super().clean()

        if 'password1' in self.fields:
            password1 = cleaned_data.get('password1')
            password2 = cleaned_data.get('password2')
            if password1 and password2 and password1 != password2:
                self.add_error('password2', 'Las contraseñas no coinciden.')
            elif password1:
                # Se valida contra los datos escritos (p. ej. que no se parezca al nombre de usuario).
                temporal = User(
                    username=cleaned_data.get('username', ''),
                    first_name=cleaned_data.get('first_name', ''),
                    last_name=cleaned_data.get('last_name', ''),
                    email=cleaned_data.get('email', ''),
                )
                try:
                    password_validation.validate_password(password1, temporal)
                except ValidationError as error:
                    self.add_error('password1', error)

        # Evita que alguien se quede sin acceso por editar su propia cuenta.
        if self.instance.pk and self.instance.pk == self.editor.pk:
            if not cleaned_data.get('is_active'):
                self.add_error('is_active', 'No puedes desactivar tu propia cuenta.')
            if not cleaned_data.get('is_staff'):
                self.add_error('is_staff', 'No puedes quitarte el rol de administrador a ti mismo.')
            if 'is_superuser' in self.fields and self.instance.is_superuser and not cleaned_data.get('is_superuser'):
                self.add_error('is_superuser', 'No puedes quitarte el rol de superusuario a ti mismo.')

        return cleaned_data

    def save(self, commit=True):
        usuario = super().save(commit=False)
        if self.cleaned_data.get('password1'):
            usuario.set_password(self.cleaned_data['password1'])
        if commit:
            usuario.save()
            self.save_m2m()
        return usuario


class ContrasenaForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['new_password1'].label = 'Contraseña nueva'
        self.fields['new_password2'].label = 'Confirmar contraseña nueva'
        self.fields['new_password1'].help_text = 'Mínimo 8 caracteres, que no sea solo números ni una contraseña común.'
        for campo in self.fields.values():
            campo.widget.attrs.update({'class': CLASE_INPUT, 'autocomplete': 'new-password'})


class FiltrarGruposForm(forms.Form):
    q = forms.CharField(
        required=False,
        label='Grupo',
        widget=forms.TextInput(attrs={'class': CLASE_INPUT, 'placeholder': 'Nombre del grupo'}),
    )
    usuario = forms.ModelChoiceField(
        queryset=User.objects.order_by('username'),
        required=False,
        label='Usuario',
        widget=_select2('Todos los usuarios'),
    )


class GrupoForm(forms.ModelForm):
    usuarios = UsuarioCheckboxField(
        queryset=User.objects.order_by('-is_active', 'username'),
        required=False,
        label='Usuarios del grupo',
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'checkbox checkbox-sm checkbox-primary'}),
    )

    class Meta:
        model = Group
        fields = ['name', 'permissions']
        labels = {'name': 'Nombre del grupo', 'permissions': 'Permisos'}
        widgets = {
            'name': forms.TextInput(attrs={'class': CLASE_INPUT, 'placeholder': 'Ej.: Técnicos de liquidación'}),
            'permissions': forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['permissions'].queryset = permisos_gestionables()
        self.fields['permissions'].required = False
        # Permisos asignados por otros medios (p. ej. el admin) que esta pantalla no muestra: se conservan.
        self.permisos_externos = []
        if self.instance.pk:
            self.fields['usuarios'].initial = self.instance.user_set.all()
            self.permisos_externos = list(
                self.instance.permissions.exclude(pk__in=self.fields['permissions'].queryset)
            )

    def matriz_permisos(self):
        """Permisos agrupados por app y modelo, con una columna por acción (ver/agregar/modificar/eliminar)."""
        seleccionados = {str(valor) for valor in (self['permissions'].value() or [])}
        acciones = dict(ACCIONES_PERMISO)
        filas = {}

        permisos = self.fields['permissions'].queryset.order_by(
            'content_type__app_label', 'content_type__model', 'codename',
        )
        for permiso in permisos:
            content_type = permiso.content_type
            if content_type.pk not in filas:
                modelo = content_type.model_class()
                filas[content_type.pk] = {
                    'app': NOMBRES_APPS.get(content_type.app_label, content_type.app_label.capitalize()),
                    'modelo': capfirst(modelo._meta.verbose_name_plural) if modelo else content_type.model,
                    'celdas': {},
                    'otros': [],
                }
            fila = filas[content_type.pk]
            dato = {'id': permiso.pk, 'nombre': permiso.name, 'marcado': str(permiso.pk) in seleccionados}
            accion = permiso.codename.split('_', 1)[0]
            if accion in acciones and permiso.codename == f'{accion}_{content_type.model}':
                fila['celdas'][accion] = dato
            else:
                fila['otros'].append(dato)

        apps = {}
        for fila in filas.values():
            fila['celdas'] = [
                {**fila['celdas'][accion], 'accion': accion} if accion in fila['celdas'] else None
                for accion, _ in ACCIONES_PERMISO
            ]
            apps.setdefault(fila['app'], []).append(fila)
        return [{'app': app, 'filas': sorted(filas_app, key=lambda f: f['modelo'])} for app, filas_app in apps.items()]

    def save(self, commit=True):
        grupo = super().save(commit=commit)
        if commit:
            grupo.permissions.add(*self.permisos_externos)
            grupo.user_set.set(self.cleaned_data['usuarios'])
        return grupo
