from django import forms

from .models import Auxiliar


class AuxiliarForm(forms.ModelForm):
    class Meta:
        model = Auxiliar
        fields = ['nombre', 'apellido', 'email', 'telefono', 'institucion']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'input input-bordered w-full', 'placeholder': 'Ej. María'}),
            'apellido': forms.TextInput(attrs={'class': 'input input-bordered w-full', 'placeholder': 'Ej. López'}),
            'email': forms.EmailInput(attrs={'class': 'input input-bordered w-full', 'placeholder': 'correo@ejemplo.com'}),
            'telefono': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': '0000-0000',
                'maxlength': '9',
                'inputmode': 'numeric',
            }),
            'institucion': forms.TextInput(attrs={'class': 'input input-bordered w-full', 'placeholder': 'Nombre de la institución'}),
        }