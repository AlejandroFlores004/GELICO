from django import forms
from django_select2.forms import Select2Widget
from django.utils.dateparse import parse_date

from .models import Auxiliar, Ausencia, Convocatoria, Horario


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


class AusenciaForm(forms.ModelForm):
    def __init__(self, *args, auxiliar=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not auxiliar and self.instance and self.instance.pk:
            auxiliar = self.instance.auxiliar
        if auxiliar:
            fechas = Horario.objects.filter(
                auxiliar=auxiliar,
            ).order_by('-fecha').values_list('fecha', flat=True).distinct()
            self.fields['fecha'] = forms.TypedChoiceField(
                choices=[
                    ('', 'Seleccionar'),
                    *[
                        (fecha.isoformat(), fecha.strftime('%d/%m/%Y'))
                        for fecha in fechas
                    ],
                ],
                coerce=parse_date,
                widget=forms.Select(attrs={
                    'class': 'select select-bordered w-full',
                }),
                empty_value=None,
            )

    class Meta:
        model = Ausencia
        fields = ['auxiliar', 'fecha', 'motivo']
        widgets = {
            'auxiliar': Select2Widget(attrs={
                'data-placeholder': 'Seleccione un auxiliar',
                'style': 'width: 100%; display: none !important;',
                'class': 'select2-daisy',
            }),
            'fecha': forms.DateInput(format='%Y-%m-%d', attrs={
                'class': 'input input-bordered w-full',
                'type': 'date',
            }),
            'motivo': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'placeholder': 'Motivo de la ausencia',
                'rows': 4,
            }),
        }


class HorarioForm(forms.ModelForm):
    class Meta:
        model = Horario
        fields = ['auxiliar', 'fecha', 'hora_inicio', 'hora_fin']
        widgets = {
            'auxiliar': Select2Widget(attrs={
                'data-placeholder': 'Seleccione un auxiliar',
                'style': 'width: 100%; display: none !important;',
                'class': 'select2-daisy',
            }),
            'fecha': forms.DateInput(format='%Y-%m-%d', attrs={
                'class': 'input input-bordered w-full',
                'type': 'date',
            }),
            'hora_inicio': forms.TimeInput(format='%H:%M', attrs={
                'class': 'input input-bordered w-full',
                'type': 'time',
            }),
            'hora_fin': forms.TimeInput(format='%H:%M', attrs={
                'class': 'input input-bordered w-full',
                'type': 'time',
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        hora_inicio = cleaned_data.get('hora_inicio')
        hora_fin = cleaned_data.get('hora_fin')
        if hora_inicio and hora_fin and hora_fin <= hora_inicio:
            self.add_error('hora_fin', 'La hora fin debe ser posterior a la hora inicio.')
        return cleaned_data


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