from django import forms
from django_select2.forms import Select2Widget
from escuela.models import Escuela

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