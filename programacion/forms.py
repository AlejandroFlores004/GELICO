from django import forms
from django_select2.forms import Select2Widget
from django.urls import reverse_lazy

from escuela.models import Escuela
from .models import Auxiliar, Ausencia, Convocatoria, ConvocatoriaAuxiliar, Horario, Jornada, Programacion, jornadas_que_se_cruzan


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
    """Visita a una escuela en la jornada de la mañana, de la tarde o todo el día. No lleva auxiliar:
    la cubren los auxiliares de la convocatoria que trabajan esa jornada según su horario."""

    # Campo explícito para que los radios no incluyan la opción vacía "---------".
    jornada = forms.ChoiceField(label='Jornada', choices=Jornada.choices, widget=forms.RadioSelect)

    def __init__(self, *args, convocatoria_fija=None, **kwargs):
        super().__init__(*args, **kwargs)
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
        fecha = cleaned_data.get('fecha_programada')
        jornada = cleaned_data.get('jornada')
        escuela = cleaned_data.get('escuela')

        if convocatoria and fecha and not convocatoria.fecha_inicio <= fecha <= convocatoria.fecha_fin:
            self.add_error(
                'fecha_programada',
                f'La fecha debe estar dentro del periodo de la convocatoria '
                f'({convocatoria.fecha_inicio:%d/%m/%Y} al {convocatoria.fecha_fin:%d/%m/%Y}).',
            )

        # Una escuela no recibe dos visitas el mismo día en jornadas que se cruzan (la mañana se cruza con "todo el día").
        if escuela and fecha and jornada and Programacion.objects.filter(
            escuela=escuela,
            fecha_programada=fecha,
            jornada__in=jornadas_que_se_cruzan(jornada),
        ).exclude(pk=self.instance.pk).exists():
            self.add_error(None, 'Esta escuela ya tiene otra programación asignada en esa fecha y jornada.')

        return cleaned_data

    class Meta:
        model = Programacion
        fields = [
            'convocatoria',
            'escuela',
            'fecha_programada',
            'jornada',
            'estado',
        ]
        widgets = {
            'convocatoria': Select2Widget(attrs={
                'data-placeholder': 'Seleccione una convocatoria',
                'style': 'width: 100%; display: none !important;',
                'class': 'select2-daisy',
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


class AsignarAuxiliaresDiaForm(forms.Form):
    """Auxiliares asignados a un día de una convocatoria. Solo se pueden asignar los que tienen horario
    ese día y no están ausentes; los que ya estaban asignados se conservan aunque eso cambie."""

    auxiliares = forms.ModelMultipleChoiceField(
        queryset=Auxiliar.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, convocatoria, fecha, **kwargs):
        self.convocatoria, self.fecha = convocatoria, fecha
        self.actuales = set(
            convocatoria.asignaciones.filter(fecha=fecha).values_list('auxiliar_id', flat=True)
        )
        kwargs.setdefault('initial', {'auxiliares': list(self.actuales)})
        super().__init__(*args, **kwargs)

        self.horarios = {}
        for horario in Horario.objects.filter(auxiliar__isnull=False).del_dia(fecha):
            self.horarios.setdefault(horario.auxiliar_id, []).append(horario)
        self.ausentes = set(Ausencia.objects.filter(fecha=fecha).values_list('auxiliar_id', flat=True))
        # Se listan los que tienen horario ese día y los que ya estaban asignados.
        self.fields['auxiliares'].queryset = Auxiliar.objects.filter(
            pk__in=set(self.horarios) | self.actuales,
        ).order_by('apellido', 'nombre')

    def _puede_asignarse(self, auxiliar_id):
        return auxiliar_id in self.horarios and auxiliar_id not in self.ausentes

    def opciones(self):
        """Cada auxiliar con su jornada de ese día, si está ausente y si se puede marcar."""
        seleccionados = {str(valor) for valor in (self['auxiliares'].value() or [])}
        return [
            {
                'auxiliar': auxiliar,
                'jornadas': [horario.get_jornada_display() for horario in self.horarios.get(auxiliar.pk, [])],
                'ausente': auxiliar.pk in self.ausentes,
                'marcado': str(auxiliar.pk) in seleccionados,
                'habilitado': self._puede_asignarse(auxiliar.pk) or auxiliar.pk in self.actuales,
            }
            for auxiliar in self.fields['auxiliares'].queryset
        ]

    def clean_auxiliares(self):
        auxiliares = self.cleaned_data['auxiliares']
        no_validos = [
            f'{auxiliar.nombre} {auxiliar.apellido}'
            for auxiliar in auxiliares
            if auxiliar.pk not in self.actuales and not self._puede_asignarse(auxiliar.pk)
        ]
        if no_validos:
            raise forms.ValidationError(f"No tienen horario ese día o están ausentes: {', '.join(no_validos)}.")
        return auxiliares

    def save(self):
        elegidos = {auxiliar.pk for auxiliar in self.cleaned_data['auxiliares']}
        self.convocatoria.asignaciones.filter(fecha=self.fecha).exclude(auxiliar__in=elegidos).delete()
        # Uno por uno (no bulk_create) para que la auditoría registre cada asignación.
        for auxiliar_id in elegidos - self.actuales:
            ConvocatoriaAuxiliar.objects.create(convocatoria=self.convocatoria, auxiliar_id=auxiliar_id, fecha=self.fecha)


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
        label='Convocatoria, escuela o estado',
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