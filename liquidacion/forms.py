from django import forms
from django_select2.forms import Select2Widget

from catalogo.models import Bono
from escuela.models import Distrito, Escuela
from .models import ESTADO_LIQUIDACION_CHOICES, Abono, Asignacion, Observacion, Recibo


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

    estado = forms.ChoiceField(
        choices=[('', 'Todos los estados')] + ESTADO_LIQUIDACION_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'select select-bordered w-full'}),
        label='Estado',
    )


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
