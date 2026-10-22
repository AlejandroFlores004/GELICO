from django import forms
from django_select2.forms import Select2Widget
from django.db.models import Q
from django.urls import reverse_lazy
from django.utils import timezone

from escuela.models import Escuela
from .models import Asistencia, Personal, Convocatoria, ConvocatoriaPersonal, Horario, Jornada, Programacion, jornadas_que_se_cruzan
from .services import registrar_asistencia


class PersonalForm(forms.ModelForm):
    """Planta lleva cargo; practicante, institución (lo valida Personal.clean)."""

    # Campo explícito para que los radios no incluyan la opción vacía "---------".
    tipo = forms.ChoiceField(label='Tipo', choices=Personal.Tipo.choices, widget=forms.RadioSelect, initial=Personal.Tipo.PRACTICANTE)

    def clean(self):
        cleaned_data = super().clean()
        # Solo se guarda el dato que corresponde al tipo (el otro campo queda oculto en el formulario).
        if cleaned_data.get('tipo') == Personal.Tipo.PLANTA:
            cleaned_data['institucion'] = ''
        elif cleaned_data.get('tipo') == Personal.Tipo.PRACTICANTE:
            cleaned_data['cargo'] = ''
        return cleaned_data

    class Meta:
        model = Personal
        fields = ['tipo', 'nombre', 'apellido', 'email', 'telefono', 'cargo', 'institucion']
        widgets = {
            'cargo': forms.TextInput(attrs={'class': 'input input-bordered w-full', 'placeholder': 'Ej. Contador', 'list': 'cargos-existentes'}),
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


class FiltrarPersonalForm(forms.Form):
    """Filtros del listado de personas. Fecha, día y jornada se refieren a su horario semanal:
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
        widget=forms.TextInput(attrs={'class': 'input input-bordered w-full', 'placeholder': 'Nombre, correo, teléfono, cargo o institución'}),
    )
    tipo = forms.ChoiceField(
        required=False, label='Tipo', choices=[('', 'Todos'), *Personal.Tipo.choices], widget=forms.Select(attrs={'class': CLASE_SELECT}),
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
        instituciones = Personal.objects.exclude(institucion='').order_by('institucion').values_list('institucion', flat=True).distinct()
        self.fields['institucion'].choices = [('', 'Todas'), *[(nombre, nombre) for nombre in instituciones]]

    def filtros_activos(self):
        """Cuántos filtros hay aplicados, para mostrarlo junto al título."""
        if not self.is_valid():
            return 0
        return sum(1 for valor in self.cleaned_data.values() if valor not in (None, ''))


class FiltrarAsistenciaForm(forms.Form):
    """Filtros del historial de asistencia."""

    persona = forms.ModelChoiceField(
        queryset=Personal.objects.filter(tipo=Personal.Tipo.PRACTICANTE).order_by('apellido', 'nombre'),
        required=False,
        label='Practicante',
        widget=Select2Widget(attrs={
            'data-placeholder': 'Todos los practicantes',
            'style': 'width: 100%',
            'class': 'select2-daisy',
            'data-allow-clear': 'true',
        }),
    )
    desde = forms.DateField(
        required=False, label='Desde',
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'class': 'input input-bordered w-full', 'type': 'date'}),
    )
    hasta = forms.DateField(
        required=False, label='Hasta',
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'class': 'input input-bordered w-full', 'type': 'date'}),
    )
    estado = forms.ChoiceField(
        required=False, label='Estado', choices=[('', 'Todos'), *Asistencia.Estado.choices],
        widget=forms.Select(attrs={'class': CLASE_SELECT}),
    )

    def clean(self):
        cleaned_data = super().clean()
        desde, hasta = cleaned_data.get('desde'), cleaned_data.get('hasta')
        if desde and hasta and hasta < desde:
            self.add_error('hasta', 'La fecha final debe ser igual o posterior a la inicial.')
        return cleaned_data


class HorarioForm(forms.ModelForm):
    """Horario semanal de un practicante. Al crear se pueden marcar varios días con el mismo horario
    (se guarda un Horario por día); al editar se cambia un solo día."""

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
        # Solo los practicantes tienen horario: el personal de planta llega cuando se le indica.
        self.fields['persona'].queryset = Personal.objects.filter(tipo=Personal.Tipo.PRACTICANTE).order_by('apellido', 'nombre')
        self.fields['persona'].label = 'Practicante'
        if self.instance.pk:
            self.fields['persona'].disabled = True
            del self.fields['dias']
        else:
            del self.fields['dia']

    class Meta:
        model = Horario
        fields = ['persona', 'dia', 'jornada', 'fecha_inicio', 'fecha_fin']
        widgets = {
            'persona': Select2Widget(attrs={
                'data-placeholder': 'Seleccione un practicante',
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
        persona = cleaned_data.get('persona')
        jornada = cleaned_data.get('jornada')
        fecha_inicio = cleaned_data.get('fecha_inicio')
        fecha_fin = cleaned_data.get('fecha_fin')

        if fecha_inicio and fecha_fin and fecha_fin < fecha_inicio:
            self.add_error('fecha_fin', 'El fin de labores debe ser igual o posterior al inicio de labores.')

        dias = self._dias()
        if self.errors or not (persona and dias):
            return cleaned_data

        # Una persona no puede tener dos horarios que se crucen el mismo día dentro del mismo periodo
        # (p. ej. "mañana" y "todo el día").
        cruces = Horario.objects.filter(
            persona=persona,
            dia__in=dias,
            jornada__in=jornadas_que_se_cruzan(jornada),
        ).vigentes_entre(fecha_inicio, fecha_fin).exclude(pk=self.instance.pk)
        dias_con_cruce = sorted({horario.get_dia_display() for horario in cruces}, key=lambda nombre: Horario.Dia.labels.index(nombre))
        if dias_con_cruce:
            self.add_error(
                None,
                f"La persona ya tiene un horario que se cruza el {', '.join(dias_con_cruce).lower()} en ese periodo.",
            )
        return cleaned_data

    def save(self, commit=True):
        if 'dias' not in self.fields:
            return super().save(commit)
        datos = {campo: self.cleaned_data[campo] for campo in ('persona', 'jornada', 'fecha_inicio', 'fecha_fin')}
        horarios = [Horario(dia=dia, **datos) for dia in self.cleaned_data['dias']]
        if commit:
            for horario in horarios:
                horario.save()
        return horarios


class ProgramacionForm(forms.ModelForm):
    """Visita a una escuela en la jornada de la mañana, de la tarde o todo el día. No lleva persona:
    la cubren las personas de la convocatoria que trabajan esa jornada según su horario."""

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


class PersonalDelDia:
    """Gestión del personal asignado a un día de una convocatoria.

    Se puede agregar a cualquier persona de planta (no tiene horario fijo) y a los practicantes que
    tienen horario ese día y no están ausentes; se puede quitar a cualquiera de los asignados. A los
    practicantes asignados se les registra que no llegaron ("ausente" en su asistencia) a partir de
    ese día; al personal de planta no se le toma asistencia."""

    MOTIVO_POR_DEFECTO = 'No se presentó'

    def __init__(self, convocatoria, fecha):
        self.convocatoria, self.fecha = convocatoria, fecha
        self.horarios = {}
        for horario in Horario.objects.del_dia(fecha):
            self.horarios.setdefault(horario.persona_id, []).append(horario)
        self._cargar_asistencias()

    def _cargar_asistencias(self):
        self.asistencias = {asistencia.persona_id: asistencia for asistencia in Asistencia.objects.filter(fecha=self.fecha)}
        self.ausentes = {persona_id for persona_id, asistencia in self.asistencias.items() if asistencia.no_trabajo}

    @property
    def se_puede_registrar_inasistencia(self):
        return self.fecha <= timezone.localdate()

    def asignados_ids(self):
        return set(self.convocatoria.asignaciones.filter(fecha=self.fecha).values_list('persona_id', flat=True))

    def puede_agregarse(self, persona):
        if not persona.es_practicante:
            return True
        return persona.pk in self.horarios and persona.pk not in self.ausentes

    def opciones(self):
        """(asignados, los demás disponibles ese día): practicantes con horario ese día y todo el personal
        de planta, cada uno con su jornada y si está ausente."""
        asignados = self.asignados_ids()
        personas = Personal.objects.filter(
            Q(pk__in=set(self.horarios) | asignados) | Q(tipo=Personal.Tipo.PLANTA)
        ).order_by('-tipo', 'apellido', 'nombre')
        filas = [
            {
                'persona': persona,
                'jornadas': [horario.get_jornada_display() for horario in self.horarios.get(persona.pk, [])],
                'ausente': persona.pk in self.ausentes,
                'asistencia': self.asistencias.get(persona.pk),
                'puede_agregarse': self.puede_agregarse(persona),
            }
            for persona in personas
        ]
        return (
            [fila for fila in filas if fila['persona'].pk in asignados],
            [fila for fila in filas if fila['persona'].pk not in asignados],
        )

    def agregar(self, persona_id):
        """Devuelve un mensaje de error, o None si se agregó (o ya estaba)."""
        persona = Personal.objects.filter(pk=persona_id).first()
        if persona is None:
            return 'La persona no existe.'
        if persona.pk in self.asignados_ids():
            return None
        if not self.puede_agregarse(persona):
            motivo = f'tiene registrado «{self.asistencias[persona.pk].get_estado_display().lower()}»' if persona.pk in self.ausentes else 'no tiene horario'
            return f'No se puede asignar a {persona.nombre} {persona.apellido}: {motivo} ese día.'
        ConvocatoriaPersonal.objects.create(convocatoria=self.convocatoria, persona=persona, fecha=self.fecha)
        return None

    def quitar(self, persona_id):
        # delete() por objeto para que la auditoría registre la baja.
        for asignacion in self.convocatoria.asignaciones.filter(fecha=self.fecha, persona_id=persona_id):
            asignacion.delete()

    def registrar_inasistencia(self, persona_id, motivo=''):
        """Marca que un practicante asignado no llegó ese día. Devuelve un mensaje de error, o None."""
        if not self.se_puede_registrar_inasistencia:
            return 'La inasistencia se registra a partir de ese día.'
        if int(persona_id) not in self.asignados_ids():
            return 'Solo se registra la inasistencia de personas asignadas a este día.'
        if not Personal.objects.filter(pk=persona_id, tipo=Personal.Tipo.PRACTICANTE).exists():
            return 'Al personal de planta no se le toma asistencia.'
        if int(persona_id) not in self.ausentes:
            registrar_asistencia(persona_id, self.fecha, Asistencia.Estado.AUSENTE, motivo.strip() or self.MOTIVO_POR_DEFECTO, validar=False)
            self._cargar_asistencias()
        return None

    def quitar_inasistencia(self, persona_id):
        """Deshace el "no llegó": el practicante queda presente ese día."""
        if int(persona_id) in self.ausentes:
            registrar_asistencia(persona_id, self.fecha, Asistencia.Estado.PRESENTE, validar=False)
            self._cargar_asistencias()


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