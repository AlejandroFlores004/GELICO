from django import forms
from django_select2.forms import Select2Widget
from django.urls import reverse_lazy
from django.utils.dateparse import parse_time

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
        self.auxiliar = auxiliar or (self.instance.auxiliar if self.instance.pk else None)

    def clean(self):
        cleaned_data = super().clean()
        auxiliar = cleaned_data.get('auxiliar') or self.auxiliar
        fecha = cleaned_data.get('fecha')
        # Solo se registra ausencia en un día en que el auxiliar trabaja según su horario semanal.
        if auxiliar and fecha and not Horario.objects.filter(auxiliar=auxiliar).del_dia(fecha).exists():
            self.add_error('fecha', 'El auxiliar no tiene horario ese día.')
        return cleaned_data

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
    """Al crear se pueden marcar varios días con el mismo horario (se guarda un Horario por día);
    al editar se cambia un solo día."""

    dias = forms.TypedMultipleChoiceField(
        label='Días',
        choices=Horario.Dia.choices,
        coerce=int,
        widget=forms.CheckboxSelectMultiple,
        error_messages={'required': 'Selecciona al menos un día.'},
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['auxiliar'].disabled = True
            del self.fields['dias']
        else:
            del self.fields['dia']

    class Meta:
        model = Horario
        fields = ['auxiliar', 'dia', 'hora_inicio', 'hora_fin', 'fecha_inicio', 'fecha_fin']
        widgets = {
            'auxiliar': Select2Widget(attrs={
                'data-placeholder': 'Seleccione un auxiliar',
                'style': 'width: 100%; display: none !important;',
                'class': 'select2-daisy',
            }),
            'dia': forms.Select(attrs={
                'class': 'select select-bordered w-full',
            }),
            'hora_inicio': forms.TimeInput(format='%H:%M', attrs={
                'class': 'input input-bordered w-full',
                'type': 'time',
            }),
            'hora_fin': forms.TimeInput(format='%H:%M', attrs={
                'class': 'input input-bordered w-full',
                'type': 'time',
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

    def _dias(self):
        if 'dias' in self.fields:
            return self.cleaned_data.get('dias') or []
        dia = self.cleaned_data.get('dia')
        return [dia] if dia else []

    def clean(self):
        cleaned_data = super().clean()
        auxiliar = cleaned_data.get('auxiliar')
        hora_inicio = cleaned_data.get('hora_inicio')
        hora_fin = cleaned_data.get('hora_fin')
        fecha_inicio = cleaned_data.get('fecha_inicio')
        fecha_fin = cleaned_data.get('fecha_fin')

        if hora_inicio and hora_fin and hora_fin <= hora_inicio:
            self.add_error('hora_fin', 'La hora fin debe ser posterior a la hora inicio.')
        if fecha_inicio and fecha_fin and fecha_fin < fecha_inicio:
            self.add_error('fecha_fin', 'El fin de labores debe ser igual o posterior al inicio de labores.')

        dias = self._dias()
        if self.errors or not (auxiliar and dias):
            return cleaned_data

        # Un auxiliar no puede tener dos horarios que se crucen el mismo día dentro del mismo periodo.
        cruces = Horario.objects.filter(
            auxiliar=auxiliar,
            dia__in=dias,
            hora_inicio__lt=hora_fin,
            hora_fin__gt=hora_inicio,
        ).vigentes_entre(fecha_inicio, fecha_fin).exclude(pk=self.instance.pk)
        dias_con_cruce = sorted({horario.get_dia_display() for horario in cruces}, key=lambda nombre: Horario.Dia.labels.index(nombre))
        if dias_con_cruce:
            self.add_error(
                None,
                f"El auxiliar ya tiene un horario que se cruza el {', '.join(dias_con_cruce).lower()} en ese periodo.",
            )
        return cleaned_data

    def save(self, commit=True):
        if 'dias' not in self.fields:
            return super().save(commit)
        datos = {campo: self.cleaned_data[campo] for campo in ('auxiliar', 'hora_inicio', 'hora_fin', 'fecha_inicio', 'fecha_fin')}
        horarios = [Horario(dia=dia, **datos) for dia in self.cleaned_data['dias']]
        if commit:
            for horario in horarios:
                horario.save()
        return horarios


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

        self.fields['auxiliar'].label = 'Auxiliar (opcional)'
        self.fields['auxiliar'].required = False

        # Dentro de la agenda de una convocatoria, la visita siempre es de esa convocatoria.
        self.convocatoria_fija = convocatoria_fija
        if convocatoria_fija:
            self.fields['convocatoria'].widget = forms.HiddenInput()
            self.fields['convocatoria'].initial = convocatoria_fija.pk

        # Al crear (o antes de la hora de la visita) queda en pendiente; el estado se marca después.
        if not self.instance.pk or not self.instance.ya_empezo:
            del self.fields['estado']

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

        # Basta con que algún horario semanal del auxiliar que aplique ese día se cruce con el bloque.
        if auxiliar and fecha and hora and not horario_sin_cambios and not Horario.objects.filter(
            auxiliar=auxiliar,
            hora_inicio__lt=fin_de_bloque(hora),
            hora_fin__gt=hora,
        ).del_dia(fecha).exists():
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
                'data-placeholder': 'Sin asignar por ahora',
                'data-allow-clear': 'true',
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