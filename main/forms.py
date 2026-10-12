from django import forms
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django_select2.forms import Select2Widget
from easyaudit.models import CRUDEvent, LoginEvent

# Los verbose_name de las apps no llevan tildes; para la bitácora se muestran estos.
NOMBRES_APPS = {
    'escuela': 'Escuelas',
    'programacion': 'Programación',
    'liquidacion': 'Liquidaciones',
    'auth': 'Usuarios',
}

ACCIONES_FILTRO = [
    ('', ''),
    ('crear', 'Creación'),
    ('actualizar', 'Actualización'),
    ('eliminar', 'Eliminación'),
    ('relaciones', 'Cambio de relaciones'),
]

TIPOS_ACCESO = [
    ('', ''),
    (str(LoginEvent.LOGIN), 'Inicio de sesión'),
    (str(LoginEvent.LOGOUT), 'Cierre de sesión'),
    (str(LoginEvent.FAILED), 'Intento fallido'),
]

METODOS_HTTP = [
    ('', ''),
    ('GET', 'GET (consulta)'),
    ('POST', 'POST (envío de datos)'),
    ('PUT', 'PUT'),
    ('PATCH', 'PATCH'),
    ('DELETE', 'DELETE'),
]


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


class UsuarioChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, usuario):
        nombre = usuario.get_full_name()
        return f'{nombre} ({usuario.username})' if nombre else usuario.username


class ModuloChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, content_type):
        modelo = content_type.model_class()
        app = NOMBRES_APPS.get(content_type.app_label, content_type.app_label.capitalize())
        nombre = modelo._meta.verbose_name.capitalize() if modelo else content_type.model
        return f'{app} · {nombre}'


class FiltrarAuditoriaForm(forms.Form):
    """Filtros de la bitácora de auditoría. Cada pestaña usa solo los campos que le aplican."""

    q = forms.CharField(
        required=False,
        label='Buscar',
        widget=forms.TextInput(attrs={'class': 'input input-bordered w-full'}),
    )
    usuario = UsuarioChoiceField(
        queryset=get_user_model().objects.order_by('username'),
        required=False,
        label='Usuario',
        widget=_select2('Todos los usuarios'),
    )
    modulo = ModuloChoiceField(
        queryset=ContentType.objects.none(),
        required=False,
        label='Módulo',
        widget=_select2('Todos los módulos'),
    )
    accion = forms.ChoiceField(
        choices=ACCIONES_FILTRO,
        required=False,
        label='Acción',
        widget=_select2('Todas las acciones', buscar=False),
    )
    tipo_acceso = forms.ChoiceField(
        choices=TIPOS_ACCESO,
        required=False,
        label='Tipo de evento',
        widget=_select2('Todos los eventos', buscar=False),
    )
    metodo = forms.ChoiceField(
        choices=METODOS_HTTP,
        required=False,
        label='Método',
        widget=_select2('Todos los métodos', buscar=False),
    )
    desde = forms.DateField(
        required=False,
        label='Desde',
        widget=forms.DateInput(attrs={'class': 'input input-bordered w-full', 'type': 'date'}),
    )
    hasta = forms.DateField(
        required=False,
        label='Hasta',
        widget=forms.DateInput(attrs={'class': 'input input-bordered w-full', 'type': 'date'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Solo los modelos que realmente tienen cambios registrados.
        self.fields['modulo'].queryset = ContentType.objects.filter(
            pk__in=CRUDEvent.objects.values('content_type').distinct(),
        ).order_by('app_label', 'model')

    def clean(self):
        cleaned_data = super().clean()
        desde = cleaned_data.get('desde')
        hasta = cleaned_data.get('hasta')
        if desde and hasta and hasta < desde:
            self.add_error('hasta', 'La fecha final debe ser igual o posterior a la inicial.')
        return cleaned_data
