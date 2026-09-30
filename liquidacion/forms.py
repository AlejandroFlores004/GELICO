from django import forms
from django.utils import timezone
from django_select2.forms import Select2Widget

from escuela.models import Distrito, Escuela
from .models import ESTADO_LIQUIDACION_CHOICES, Abono, Asignacion, Bono, Observacion, Recibo
from .models import ESTADO_LIQUIDACION_CHOICES, Abono, Asignacion, Bono, Observacion, Recibo


class FiltrarAsignacionesForm(forms.Form):
    distrito = forms.ModelChoiceField(
        queryset=Distrito.objects.all(),
        widget=Select2Widget(attrs={
            'data-placeholder': 'Todos los distritos',
            'style': 'width: 100%',
            'class': 'select2-daisy',
            'data-allow-clear': 'false',
        }),
        label='Distrito',
        required=False,
    )

    escuela = forms.ModelChoiceField(
        queryset=Escuela.objects.all(),
        widget=Select2Widget(attrs={
            'data-placeholder': 'Todas las escuelas',
            'style': 'width: 100%',
            'class': 'select2-daisy',
            'data-allow-clear': 'false',
        }),
        label='Escuela',
        required=False,
    )

    bono = forms.ModelChoiceField(
        queryset=Bono.objects.all(),
        widget=Select2Widget(attrs={
            'data-placeholder': 'Todos los bonos',
            'style': 'width: 100%',
            'class': 'select2-daisy',
            'data-allow-clear': 'false',
        }),
        label='Bono',
        required=False,
    )

    anio = forms.TypedChoiceField(
        coerce=int,
        empty_value=None,
        required=False,
        widget=Select2Widget(attrs={
            'data-placeholder': 'Todos los años',
            'style': 'width: 100%',
            'class': 'select2-daisy',
            'data-allow-clear': 'false',
            'data-minimum-results-for-search': 'Infinity',
        }),
        label='Año',
    )

    estado = forms.ChoiceField(
        choices=[('', '')] + ESTADO_LIQUIDACION_CHOICES,
        required=False,
        widget=Select2Widget(attrs={
            'data-placeholder': 'Todos los estados',
            'style': 'width: 100%',
            'class': 'select2-daisy',
            'data-allow-clear': 'false',
            'data-minimum-results-for-search': 'Infinity',
        }),
        label='Estado',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        anios = Bono.objects.order_by('-anio').values_list('anio', flat=True).distinct()
        self.fields['anio'].choices = [('', '')] + [(anio, anio) for anio in anios]


class AsignacionForm(forms.ModelForm):
    class Meta:
        model = Asignacion
        fields = ['escuela', 'bono', 'valor']
        widgets = {
            'escuela': Select2Widget(attrs={
                'data-placeholder': 'Seleccione una escuela',
                'style': 'width: 100%',
                'class': 'select2-daisy',
            }),
            'bono': Select2Widget(attrs={
                'data-placeholder': 'Seleccione un bono',
                'style': 'width: 100%',
                'class': 'select2-daisy',
            }),
            'valor': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'step': '0.01',
                'min': '0',
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        escuela = cleaned_data.get('escuela')
        bono = cleaned_data.get('bono')

        if escuela and bono:
            duplicado = Asignacion.objects.filter(escuela=escuela, bono=bono)
            if self.instance.pk:
                duplicado = duplicado.exclude(pk=self.instance.pk)
            if duplicado.exists():
                self.add_error('bono', 'Ya existe una asignación para esta escuela y este bono.')

        return cleaned_data


class AsignacionValorForm(forms.ModelForm):
    class Meta:
        model = Asignacion
        fields = ['valor']
        widgets = {
            'valor': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'step': '0.01',
                'min': '0',
            }),
        }


class ReciboForm(forms.ModelForm):
    class Meta:
        model = Recibo
        fields = ['monto']
        widgets = {
            'monto': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'step': '0.01',
                'min': '0',
            }),
        }


class AbonoForm(forms.ModelForm):
    class Meta:
        model = Abono
        fields = ['monto', 'requerimiento', 'estado', 'id_planilla_parcial']
        widgets = {
            'monto': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'step': '0.01',
                'min': '0',
            }),
            'requerimiento': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
            }),
            'estado': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
            }),
            'id_planilla_parcial': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
            }),
        }


class ObservacionForm(forms.ModelForm):
    class Meta:
        model = Observacion
        fields = ['descripcion', 'resuelta']
        widgets = {
            'descripcion': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 3,
            }),
            'resuelta': forms.CheckboxInput(attrs={
                'class': 'checkbox',
            }),
        }


class BonoForm(forms.ModelForm):
    class Meta:
        model = Bono
        fields = ['nombre', 'anio', 'id_sistema', 'descripcion']
        labels = {
            'nombre': 'Nombre',
            'anio': 'Año',
            'id_sistema': 'ID en el sistema',
            'descripcion': 'Descripción',
        }
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Nombre del bono',
            }),
            'anio': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Ej. 2026',
                'min': '2000',
                'max': '2100',
            }),
            'id_sistema': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Opcional',
                'min': '0',
            }),
            'descripcion': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 4,
                'placeholder': 'Opcional',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Los bonos que vienen de la carga de Excel no traen descripción.
        self.fields['descripcion'].required = False
        if not self.instance.pk:
            self.initial.setdefault('anio', timezone.localdate().year)
