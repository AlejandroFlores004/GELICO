from django import forms
from django_select2.forms import Select2Widget
from django.urls import reverse_lazy
from django.utils import timezone

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


CLASE_SELECT = 'select select-bordered w-full'


class FiltrarAuxiliaresForm(forms.Form):
    """Filtros del listado de auxiliares. Fecha, día y jornada se refieren a su horario semanal:
    con ellos, "con horario" significa que trabaja esa fecha / ese día / esa jornada."""

    HORARIO = [
        ('', 'Todos'),
        ('con', 'Con horario'),
        ('sin', 'Sin horario'),
        ('vigente', 'Con horario vigente hoy'),
        ('vencido', 'Con horario ya vencido'),
    ]

    q = forms.CharField(
        required=False,
        label='Buscar',
        widget=forms.TextInput(attrs={'class': 'input input-bordered w-full', 'placeholder': 'Nombre, apellido, correo o teléfono'}),
    )
    institucion = forms.ChoiceField(required=False, label='Institución', widget=forms.Select(attrs={'class': CLASE_SELECT}))
    horario = forms.ChoiceField(required=False, label='Horario', choices=HORARIO, widget=forms.Select(attrs={'class': CLASE_SELECT}))
    fecha = forms.DateField(
        required=False,
        label='Trabaja el día',
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'class': 'input input-bordered w-full', 'type': 'date'}),
    )
    dia = forms.TypedChoiceField(
        required=False,
        label='Día de la semana',
        coerce=int,
        empty_value=None,
        choices=[('', 'Cualquiera'), *Horario.Dia.choices],
        widget=forms.Select(attrs={'class': CLASE_SELECT}),
    )
    jornada = forms.ChoiceField(
        required=False,
        label='Jornada',
        choices=[('', 'Cualquiera'), *Jornada.choices],
        widget=forms.Select(attrs={'class': CLASE_SELECT}),
    )
    convocatoria = forms.ModelChoiceField(
        queryset=Convocatoria.objects.order_by('-fecha_inicio'),
        required=False,
        label='Asignado en la convocatoria',
        widget=Select2Widget(attrs={
            'data-placeholder': 'Cualquier convocatoria',
            'style': 'width: 100%',
            'class': 'select2-daisy',
            'data-allow-clear': 'true',
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instituciones = Auxiliar.objects.order_by('institucion').values_list('institucion', flat=True).distinct()
        self.fields['institucion'].choices = [('', 'Todas'), *[(nombre, nombre) for nombre in instituciones]]

    def filtros_activos(self):
        """Cuántos filtros hay aplicados, para mostrarlo junto al título."""
        if not self.is_valid():
            return 0
        return sum(1 for valor in self.cleaned_data.values() if valor not in (None, ''))


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


class AuxiliaresDelDia:
    """Gestión de los auxiliares asignados a un día de una convocatoria.

    Se puede agregar a quien tiene horario ese día y no está ausente; se puede quitar a cualquiera
    de los asignados (aunque su horario haya cambiado después de asignarlo). A los asignados se les
    registra la inasistencia ("no llegó") a partir de ese día, como una Ausencia de esa fecha."""

    MOTIVO_POR_DEFECTO = 'No se presentó'

    def __init__(self, convocatoria, fecha):
        self.convocatoria, self.fecha = convocatoria, fecha
        self.horarios = {}
        for horario in Horario.objects.del_dia(fecha):
            self.horarios.setdefault(horario.auxiliar_id, []).append(horario)
        self._cargar_ausencias()

    def _cargar_ausencias(self):
        self.ausencias = {ausencia.auxiliar_id: ausencia for ausencia in Ausencia.objects.filter(fecha=self.fecha)}
        self.ausentes = set(self.ausencias)

    @property
    def se_puede_registrar_inasistencia(self):
        return self.fecha <= timezone.localdate()

    def asignados_ids(self):
        return set(self.convocatoria.asignaciones.filter(fecha=self.fecha).values_list('auxiliar_id', flat=True))

    def puede_agregarse(self, auxiliar_id):
        return auxiliar_id in self.horarios and auxiliar_id not in self.ausentes

    def opciones(self):
        """(asignados, los demás con horario ese día), cada uno con su jornada y si está ausente."""
        asignados = self.asignados_ids()
        auxiliares = Auxiliar.objects.filter(pk__in=set(self.horarios) | asignados).order_by('apellido', 'nombre')
        filas = [
            {
                'auxiliar': auxiliar,
                'jornadas': [horario.get_jornada_display() for horario in self.horarios.get(auxiliar.pk, [])],
                'ausente': auxiliar.pk in self.ausentes,
                'ausencia': self.ausencias.get(auxiliar.pk),
                'puede_agregarse': self.puede_agregarse(auxiliar.pk),
            }
            for auxiliar in auxiliares
        ]
        return (
            [fila for fila in filas if fila['auxiliar'].pk in asignados],
            [fila for fila in filas if fila['auxiliar'].pk not in asignados],
        )

    def agregar(self, auxiliar_id):
        """Devuelve un mensaje de error, o None si se agregó (o ya estaba)."""
        auxiliar = Auxiliar.objects.filter(pk=auxiliar_id).first()
        if auxiliar is None:
            return 'El auxiliar no existe.'
        if auxiliar.pk in self.asignados_ids():
            return None
        if not self.puede_agregarse(auxiliar.pk):
            motivo = 'tiene registrado que no llegó' if auxiliar.pk in self.ausentes else 'no tiene horario'
            return f'No se puede asignar a {auxiliar.nombre} {auxiliar.apellido}: {motivo} ese día.'
        ConvocatoriaAuxiliar.objects.create(convocatoria=self.convocatoria, auxiliar=auxiliar, fecha=self.fecha)
        return None

    def quitar(self, auxiliar_id):
        # delete() por objeto para que la auditoría registre la baja.
        for asignacion in self.convocatoria.asignaciones.filter(fecha=self.fecha, auxiliar_id=auxiliar_id):
            asignacion.delete()

    def registrar_inasistencia(self, auxiliar_id, motivo=''):
        """Marca que un auxiliar asignado no llegó ese día. Devuelve un mensaje de error, o None."""
        if not self.se_puede_registrar_inasistencia:
            return 'La inasistencia se registra a partir de ese día.'
        if int(auxiliar_id) not in self.asignados_ids():
            return 'Solo se registra la inasistencia de auxiliares asignados a este día.'
        if int(auxiliar_id) not in self.ausentes:
            Ausencia.objects.create(auxiliar_id=auxiliar_id, fecha=self.fecha, motivo=motivo.strip() or self.MOTIVO_POR_DEFECTO)
            self._cargar_ausencias()
        return None

    def quitar_inasistencia(self, auxiliar_id):
        """Deshace el "no llegó": borra la ausencia de ese día."""
        for ausencia in Ausencia.objects.filter(auxiliar_id=auxiliar_id, fecha=self.fecha):
            ausencia.delete()
        self._cargar_ausencias()


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