from django import forms
from django.urls import reverse_lazy
from django_select2.forms import Select2Widget
from escuela.models import Escuela, Distrito
from catalogo.models import Bono
from .models import Asignacion, Transferencia

class SeleccionarEscuelaForm(forms.Form):
    escuela = forms.ModelChoiceField(
        queryset=Escuela.objects.all(),
        widget=Select2Widget(attrs={
            'data-placeholder': 'Seleccione una escuela',
            'style': 'width: 100%',
            'class': 'select2-daisy',
        }),
        label='Escuela',
        required=True
    )

class SeleccionarBonoForm(forms.Form):
    bono = forms.ModelChoiceField(
        queryset=Bono.objects.none(),
        widget=Select2Widget(attrs={
            'data-placeholder': 'Seleccione un bono',
            'style': 'width: 100%',
            'class': 'select2-daisy',
        }),
        label='Bono',
        required=True
    )

    def __init__(self, *args, escuela=None, **kwargs):
        super().__init__(*args, **kwargs)
        if escuela is not None:
            self.fields['bono'].queryset = Bono.objects.filter(asignacion__escuela=escuela).distinct()


class FiltrarAsignacionesForm(forms.Form):
    distrito = forms.ModelChoiceField(
        queryset=Distrito.objects.all(),
        widget=Select2Widget(attrs={
            'data-placeholder': 'Todos los distritos',
            'style': 'width: 100%',
            'class': 'select2-daisy',
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
        }),
        label='Bono',
        required=False,
    )
    fecha = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'input input-bordered w-full',
        }, format='%Y-%m-%d'),
        label='Fecha',
    )


class AsignacionForm(forms.ModelForm):
    class Meta:
        model = Asignacion
        fields = ['escuela', 'bono', 'valor', 'fecha']
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
            'fecha': forms.DateInput(attrs={
                'type': 'date',
                'class': 'input input-bordered w-full',
            }, format='%Y-%m-%d'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['escuela'].disabled = True


class FiltrarTransferenciasForm(forms.Form):
    distrito = forms.ModelChoiceField(
        queryset=Distrito.objects.all(),
        widget=Select2Widget(attrs={
            'data-placeholder': 'Todos los distritos',
            'style': 'width: 100%',
            'class': 'select2-daisy',
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
        }),
        label='Bono',
        required=False,
    )
    fecha = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'input input-bordered w-full',
        }, format='%Y-%m-%d'),
        label='Fecha',
    )


class TransferenciaForm(forms.ModelForm):
    field_order = ['escuela', 'asignacion', 'monto', 'fecha']

    escuela = forms.ModelChoiceField(
        queryset=Escuela.objects.all(),
        widget=Select2Widget(attrs={
            'data-placeholder': 'Seleccione una escuela',
            'style': 'width: 100%',
            'class': 'select2-daisy',
            'hx-get': reverse_lazy('transferencia_asignaciones_por_escuela'),
            'hx-target': '#transferencia-asignacion-select-wrapper',
            'hx-swap': 'outerHTML',
            'hx-trigger': 'change',
        }),
        label='Escuela',
    )

    class Meta:
        model = Transferencia
        fields = ['asignacion', 'monto', 'fecha']
        widgets = {
            'asignacion': Select2Widget(attrs={
                'data-placeholder': 'Primero seleccione una escuela',
                'style': 'width: 100%',
                'class': 'select2-daisy',
            }),
            'monto': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'step': '0.01',
                'min': '0',
            }),
            'fecha': forms.DateInput(attrs={
                'type': 'date',
                'class': 'input input-bordered w-full',
            }, format='%Y-%m-%d'),
        }

    def __init__(self, *args, escuela=None, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            escuela = self.instance.asignacion.escuela
            self.initial['escuela'] = escuela.pk
            self.fields['escuela'].disabled = True
            self.fields['asignacion'].disabled = True
        elif escuela is None and self.data:
            escuela_id = self.data.get(self.add_prefix('escuela'))
            if escuela_id:
                escuela = Escuela.objects.filter(pk=escuela_id).first()

        if escuela is not None:
            self.fields['asignacion'].queryset = Asignacion.objects.filter(escuela=escuela).select_related('bono')
        else:
            self.fields['asignacion'].queryset = Asignacion.objects.none()