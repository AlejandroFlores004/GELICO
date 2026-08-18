from django import forms
from django_select2.forms import Select2Widget
from escuela.models import Escuela, Distrito
from catalogo.models import Bono
from .models import Asignacion
from .models import Asignacion

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