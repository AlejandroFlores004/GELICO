from django import forms
from django_select2.forms import Select2Widget
from django.urls import reverse_lazy
from escuela.models import Escuela
from .models import Auxiliar, Ausencia, Convocatoria, Horario, Jornada, Programacion, jornadas_que_se_cruzan, turnos_de


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

    # Campo explícito para que los radios no incluyan la opción vacía "---------".
    jornada = forms.ChoiceField(label='Jornada', choices=Jornada.choices, widget=forms.RadioSelect)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['auxiliar'].disabled = True
            del self.fields['dias']
        else:
            del self.fields['dia']

    class Meta:
        model = Horario
        fields = ['auxiliar', 'dia', 'jornada', 'fecha_inicio', 'fecha_fin']
        widgets = {
            'auxiliar': Select2Widget(attrs={
                'data-placeholder': 'Seleccione un auxiliar',
                'style': 'width: 100%; display: none !important;',
                'class': 'select2-daisy',
            }),
            'dia': forms.Select(attrs={
                'class': 'select select-bordered w-full',
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
        jornada = cleaned_data.get('jornada')
        fecha_inicio = cleaned_data.get('fecha_inicio')
        fecha_fin = cleaned_data.get('fecha_fin')

        if fecha_inicio and fecha_fin and fecha_fin < fecha_inicio:
            self.add_error('fecha_fin', 'El fin de labores debe ser igual o posterior al inicio de labores.')

        dias = self._dias()
        if self.errors or not (auxiliar and dias):
            return cleaned_data

        # Un auxiliar no puede tener dos horarios que se crucen el mismo día dentro del mismo periodo
        # (p. ej. "mañana" y "todo el día").
        cruces = Horario.objects.filter(
            auxiliar=auxiliar,
            dia__in=dias,
            jornada__in=jornadas_que_se_cruzan(jornada),
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
        datos = {campo: self.cleaned_data[campo] for campo in ('auxiliar', 'jornada', 'fecha_inicio', 'fecha_fin')}
        horarios = [Horario(dia=dia, **datos) for dia in self.cleaned_data['dias']]
        if commit:
            for horario in horarios:
                horario.save()
        return horarios


class ProgramacionForm(forms.ModelForm):
    """Visita de un auxiliar a una escuela en la jornada de la mañana, de la tarde o todo el día."""

    # Campo explícito para que los radios no incluyan la opción vacía "---------".
    jornada = forms.ChoiceField(label='Jornada', choices=Jornada.choices, widget=forms.RadioSelect)

    def __init__(self, *args, convocatoria_fija=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['auxiliar'].label = 'Auxiliar (opcional)'
        self.fields['auxiliar'].required = False

        # Dentro de la agenda de una convocatoria, la visita siempre es de esa convocatoria.
        self.convocatoria_fija = convocatoria_fija
        if convocatoria_fija:
            self.fields['convocatoria'].widget = forms.HiddenInput()
            self.fields['convocatoria'].initial = convocatoria_fija.pk

        # Al crear (o antes de que empiece la jornada de la visita) queda en pendiente; el estado se marca después.
        if not self.instance.pk or not self.instance.ya_empezo:
            del self.fields['estado']

    def clean(self):
        cleaned_data = super().clean()
        convocatoria = cleaned_data.get('convocatoria')
        auxiliar = cleaned_data.get('auxiliar')
        fecha = cleaned_data.get('fecha_programada')
        jornada = cleaned_data.get('jornada')
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
            and jornada == self.instance.jornada
        )

        # El horario semanal del auxiliar ese día debe cubrir todos los turnos de la jornada
        # (para "todo el día" sirve un horario de todo el día, o uno de mañana y otro de tarde).
        if auxiliar and fecha and jornada and not horario_sin_cambios:
            turnos_con_horario = {
                turno
                for horario in Horario.objects.filter(auxiliar=auxiliar).del_dia(fecha)
                for turno in horario.turnos
            }
            if not set(turnos_de(jornada)) <= turnos_con_horario:
                self.add_error(None, 'El auxiliar no tiene horario en esa jornada de esa fecha.')

        if fecha and jornada:
            # Se cruzan las visitas del mismo día que comparten turno (la mañana se cruza con "todo el día").
            mismo_turno = Programacion.objects.filter(
                fecha_programada=fecha,
                jornada__in=jornadas_que_se_cruzan(jornada),
            ).exclude(pk=self.instance.pk)

            if auxiliar and mismo_turno.filter(auxiliar=auxiliar).exists():
                self.add_error(None, 'Este auxiliar ya tiene otra programación asignada en esa fecha y jornada.')
            if escuela and mismo_turno.filter(escuela=escuela).exists():
                self.add_error(None, 'Esta escuela ya tiene otra programación asignada en esa fecha y jornada.')

        return cleaned_data

    class Meta:
        model = Programacion
        fields = [
            'convocatoria',
            'auxiliar',
            'fecha_programada',
            'jornada',
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