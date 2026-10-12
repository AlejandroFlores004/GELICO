from django import forms
from django_select2.forms import Select2Widget
from django.urls import reverse_lazy
from django.utils.dateparse import parse_date, parse_time

from escuela.models import Escuela
from .agenda import bloques, etiqueta_bloque, fin_de_bloque
from .models import Auxiliar, Ausencia, Convocatoria, Horario, Programacion


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
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['auxiliar'].disabled = True

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


class ProgramacionForm(forms.ModelForm):
    """Visita de un auxiliar a una escuela en un bloque de una hora dentro de una convocatoria."""

    # Se elige de una lista de bloques, pero se acepta cualquier hora válida (visitas anteriores a los bloques).
    hora_programada = forms.TimeField(
        label='Bloque de hora',
        widget=forms.Select(attrs={'class': 'select select-bordered w-full'}),
    )

    def __init__(self, *args, convocatoria_fija=None, **kwargs):
        super().__init__(*args, **kwargs)
        opciones = bloques()
        # Una visita guardada antes de los bloques (p. ej. 10:15) conserva su hora como opción.
        actual = self.instance.hora_programada if self.instance.pk else None
        if isinstance(actual, str):
            actual = parse_time(actual)
        if actual and actual not in opciones:
            opciones = sorted([*opciones, actual])
        self.fields['hora_programada'].widget.choices = [('', 'Selecciona un bloque')] + [
            (hora.strftime('%H:%M:%S'), etiqueta_bloque(hora)) for hora in opciones
        ]

        # Dentro de la agenda de una convocatoria, la visita siempre es de esa convocatoria.
        self.convocatoria_fija = convocatoria_fija
        if convocatoria_fija:
            self.fields['convocatoria'].widget = forms.HiddenInput()
            self.fields['convocatoria'].initial = convocatoria_fija.pk

    def clean(self):
        cleaned_data = super().clean()
        convocatoria = cleaned_data.get('convocatoria')
        auxiliar = cleaned_data.get('auxiliar')
        fecha = cleaned_data.get('fecha_programada')
        hora = cleaned_data.get('hora_programada')
        escuela = cleaned_data.get('escuela')

        if convocatoria and fecha and not convocatoria.fecha_inicio <= fecha <= convocatoria.fecha_fin:
            self.add_error(
                'fecha_programada',
                f'La fecha debe estar dentro del periodo de la convocatoria '
                f'({convocatoria.fecha_inicio:%d/%m/%Y} al {convocatoria.fecha_fin:%d/%m/%Y}).',
            )

        horario_sin_cambios = self.instance.pk and (
            auxiliar == self.instance.auxiliar
            and fecha == self.instance.fecha_programada
            and hora == self.instance.hora_programada
        )

        # Basta con que algún horario del auxiliar se cruce con el bloque.
        if auxiliar and fecha and hora and not horario_sin_cambios and not Horario.objects.filter(
            auxiliar=auxiliar,
            fecha=fecha,
            hora_inicio__lt=fin_de_bloque(hora),
            hora_fin__gt=hora,
        ).exists():
            self.add_error(
                None,
                'El auxiliar no tiene horario registrado en ese bloque de esa fecha.',
            )

        programaciones_mismo_bloque = Programacion.objects.filter(
            fecha_programada=fecha,
            hora_programada__hour=hora.hour if hora else None,
        )
        if self.instance.pk:
            programaciones_mismo_bloque = programaciones_mismo_bloque.exclude(pk=self.instance.pk)

        if auxiliar and hora and programaciones_mismo_bloque.filter(auxiliar=auxiliar).exists():
            self.add_error(
                None,
                'Este auxiliar ya tiene otra programación asignada en esa fecha y hora.',
            )
        if escuela and hora and programaciones_mismo_bloque.filter(escuela=escuela).exists():
            self.add_error(
                None,
                'Esta escuela ya tiene otra programación asignada en esa fecha y hora.',
            )

        return cleaned_data

    class Meta:
        model = Programacion
        fields = [
            'convocatoria',
            'auxiliar',
            'fecha_programada',
            'hora_programada',
            'escuela',
            'estado',
        ]
        widgets = {
            'convocatoria': Select2Widget(attrs={
                'data-placeholder': 'Seleccione una convocatoria',
                'style': 'width: 100%; display: none !important;',
                'class': 'select2-daisy',
                'hx-get': reverse_lazy('programacion_auxiliar_horario'),
                'hx-target': '#programacion-auxiliar-horarios',
                'hx-swap': 'outerHTML',
                'hx-trigger': 'convocatoria-seleccionada',
                'hx-include': 'closest form',
            }),
            'auxiliar': Select2Widget(attrs={
                'data-placeholder': 'Seleccione un auxiliar',
                'style': 'width: 100%; display: none !important;',
                'class': 'select2-daisy',
                'hx-get': reverse_lazy('programacion_auxiliar_horario'),
                'hx-target': '#programacion-auxiliar-horarios',
                'hx-swap': 'outerHTML',
                'hx-trigger': 'auxiliar-seleccionado',
                'hx-include': 'closest form',
            }),
            'fecha_programada': forms.DateInput(format='%Y-%m-%d', attrs={
                'class': 'input input-bordered w-full',
                'type': 'date',
            }),
            'escuela': Select2Widget(attrs={
                'data-placeholder': 'Seleccione una escuela',
                'style': 'width: 100%; display: none !important;',
                'class': 'select2-daisy',
            }),
            'estado': forms.Select(attrs={
                'class': 'select select-bordered w-full',
            }),
        }


class ProgramacionEstadoForm(forms.ModelForm):
    class Meta:
        model = Programacion
        fields = ['estado']
        widgets = {
            'estado': forms.Select(attrs={
                'class': 'select select-bordered w-full',
            }),
        }


class ProgramacionFiltroForm(forms.Form):
    q = forms.CharField(
        required=False,
        label='Convocatoria, auxiliar, escuela o estado',
        widget=forms.TextInput(attrs={
            'class': 'input input-bordered w-full',
            'placeholder': 'Escribe para buscar',
        }),
    )
    convocatoria = forms.ModelChoiceField(
        queryset=Convocatoria.objects.all().order_by('nombre'),
        required=False,
        label='Convocatoria',
        widget=Select2Widget(attrs={
            'data-placeholder': 'Todas las convocatorias',
            'style': 'width: 100%',
            'class': 'select2-daisy',
        }),
    )
    escuela = forms.ModelChoiceField(
        queryset=Escuela.objects.all().order_by('nombre_corto'),
        required=False,
        label='Escuela',
        widget=Select2Widget(attrs={
            'data-placeholder': 'Todas las escuelas',
            'style': 'width: 100%',
            'class': 'select2-daisy',
        }),
    )
    auxiliar = forms.ModelChoiceField(
        queryset=Auxiliar.objects.all().order_by('apellido', 'nombre'),
        required=False,
        label='Auxiliar',
        widget=Select2Widget(attrs={
            'data-placeholder': 'Todos los auxiliares',
            'style': 'width: 100%',
            'class': 'select2-daisy',
        }),
    )


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
            'fecha_inicio': forms.DateInput(format='%Y-%m-%d', attrs={
                'class': 'input input-bordered w-full',
                'type': 'date',
            }),
            'fecha_fin': forms.DateInput(format='%Y-%m-%d', attrs={
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