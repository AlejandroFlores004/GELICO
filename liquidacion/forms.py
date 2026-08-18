from django import forms
from django_select2.forms import Select2Widget
from escuela.models import Escuela
from catalogo.models import Bono
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
        }),
        label='Fecha',
    )
