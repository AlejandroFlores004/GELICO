from django import forms

from .models import Auxiliar, Convocatoria


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


class ConvocatoriaForm(forms.ModelForm):
    class Meta:
        model = Convocatoria
        fields = ['nombre', 'descripcion', 'fecha_inicio', 'fecha_fin']
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Nombre de la convocatoria',
            }),
            'descripcion': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'placeholder': 'Descripción de la convocatoria',
                'rows': 4,
            }),
            'fecha_inicio': forms.DateInput(attrs={
                'class': 'input input-bordered w-full',
                'type': 'date',
            }),
            'fecha_fin': forms.DateInput(attrs={
                'class': 'input input-bordered w-full',
                'type': 'date',
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        fecha_inicio = cleaned_data.get('fecha_inicio')
        fecha_fin = cleaned_data.get('fecha_fin')
        if fecha_inicio and fecha_fin and fecha_fin < fecha_inicio:
            self.add_error('fecha_fin', 'La fecha fin debe ser posterior o igual a la fecha inicio.')
        return cleaned_data