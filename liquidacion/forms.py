from django import forms
from django.urls import reverse_lazy
from django_select2.forms import Select2Widget
from escuela.models import Escuela, Distrito
from catalogo.models import Bono
from .models import Asignacion, Transferencia

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

class SeleccionarBonoForm(forms.Form):
    bono = forms.ModelChoiceField(
        queryset=Bono.objects.none(),
        widget=Select2Widget(attrs={
            'data-placeholder': 'Seleccione un bono',
            'style': 'width: 100%',
            'class': 'select2-daisy',
        }),
        label='Bono',
        required=True
    )

    def __init__(self, *args, escuela=None, **kwargs):
        super().__init__(*args, **kwargs)
        if escuela is not None:
            self.fields['bono'].queryset = Bono.objects.filter(asignacion__escuela=escuela).distinct()


class FiltrarAsignacionesForm(forms.Form):
    distrito = forms.ModelChoiceField(
        queryset=Distrito.objects.all(),
        widget=Select2Widget(attrs={
            'data-placeholder': 'Todos los distritos',
            'style': 'width: 100%',
            'class': 'select2-daisy',
        }),
        label='Distrito',
        required=False,
    )
    escuela = forms.ModelChoiceField(
        queryset=Escuela.objects.all(),
        widget=Select2Widget(attrs={
            'data-placeholder': 'Todas las escuelas',
            'style': 'width: 100%',
            'class': 'select2-daisy',
        }),
        label='Escuela',
        required=False,
    )
    bono = forms.ModelChoiceField(
        queryset=Bono.objects.all(),
        widget=Select2Widget(attrs={
            'data-placeholder': 'Todos los bonos',
            'style': 'width: 100%',
            'class': 'select2-daisy',
        }),
        label='Bono',
        required=False,
    )
    fecha = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'input input-bordered w-full',
        }, format='%Y-%m-%d'),
        label='Fecha',
    )


class AsignacionForm(forms.ModelForm):
    class Meta:
        model = Asignacion
        fields = ['escuela', 'bono', 'valor', 'fecha']
        widgets = {
            'escuela': Select2Widget(attrs={
                'data-placeholder': 'Seleccione una escuela',
                'style': 'width: 100%',
                'class': 'select2-daisy',
            }),
            'bono': Select2Widget(attrs={
                'data-placeholder': 'Seleccione un bono',
                'style': 'width: 100%',
                'class': 'select2-daisy',
            }),
            'valor': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'step': '0.01',
                'min': '0',
            }),
            'fecha': forms.DateInput(attrs={
                'type': 'date',
                'class': 'input input-bordered w-full',
            }, format='%Y-%m-%d'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['escuela'].disabled = True


class FiltrarTransferenciasForm(forms.Form):
    distrito = forms.ModelChoiceField(
        queryset=Distrito.objects.all(),
        widget=Select2Widget(attrs={
            'data-placeholder': 'Todos los distritos',
            'style': 'width: 100%',
            'class': 'select2-daisy',
        }),
        label='Distrito',
        required=False,
    )
    escuela = forms.ModelChoiceField(
        queryset=Escuela.objects.all(),
        widget=Select2Widget(attrs={
            'data-placeholder': 'Todas las escuelas',
            'style': 'width: 100%',
            'class': 'select2-daisy',
        }),
        label='Escuela',
        required=False,
    )
    bono = forms.ModelChoiceField(
        queryset=Bono.objects.all(),
        widget=Select2Widget(attrs={
            'data-placeholder': 'Todos los bonos',
            'style': 'width: 100%',
            'class': 'select2-daisy',
        }),
        label='Bono',
        required=False,
    )
    fecha = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'input input-bordered w-full',
        }, format='%Y-%m-%d'),
        label='Fecha',
    )


class TransferenciaForm(forms.ModelForm):
    field_order = ['escuela', 'asignacion', 'monto', 'fecha']

    escuela = forms.ModelChoiceField(
        queryset=Escuela.objects.all(),
        widget=Select2Widget(attrs={
            'data-placeholder': 'Seleccione una escuela',
            'style': 'width: 100%',
            'class': 'select2-daisy',
            'hx-get': reverse_lazy('transferencia_asignaciones_por_escuela'),
            'hx-target': '#transferencia-asignacion-select-wrapper',
            'hx-swap': 'outerHTML',
            'hx-trigger': 'change',
        }),
        label='Escuela',
    )

    class Meta:
        model = Transferencia
        fields = ['asignacion', 'monto', 'fecha']
        widgets = {
            'asignacion': Select2Widget(attrs={
                'data-placeholder': 'Primero seleccione una escuela',
                'style': 'width: 100%',
                'class': 'select2-daisy',
                'hx-get': reverse_lazy('transferencia_saldo_asignacion'),
                'hx-target': '#transferencia-saldo-wrapper',
                'hx-swap': 'outerHTML',
                'hx-trigger': 'change',
            }),
            'monto': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'step': '0.01',
                'min': '0',
            }),
            'fecha': forms.DateInput(attrs={
                'type': 'date',
                'class': 'input input-bordered w-full',
            }, format='%Y-%m-%d'),
        }

    def __init__(self, *args, escuela=None, **kwargs):
        super().__init__(*args, **kwargs)

        if escuela is None and self.data:
            escuela_id = self.data.get(self.add_prefix('escuela'))
            if escuela_id:
                escuela = Escuela.objects.filter(pk=escuela_id).first()

        if escuela is not None:
            queryset = Asignacion.objects.filter(escuela=escuela).select_related('bono')
            ids_con_saldo = [asignacion.pk for asignacion in queryset if asignacion.saldo_disponible > 0]
            self.fields['asignacion'].queryset = queryset.filter(pk__in=ids_con_saldo)
            self.fields['asignacion'].label_from_instance = (
                lambda asignacion: f"{asignacion.bono.nombre} (Saldo disponible: ${asignacion.saldo_disponible:.2f})"
            )
        else:
            self.fields['asignacion'].queryset = Asignacion.objects.none()

    def clean(self):
        cleaned_data = super().clean()
        asignacion = cleaned_data.get('asignacion')
        monto = cleaned_data.get('monto')

        if asignacion is not None and monto is not None:
            saldo_disponible = asignacion.saldo_disponible
            if monto > saldo_disponible:
                self.add_error(
                    'monto',
                    f'El monto excede el saldo disponible de la asignación (${saldo_disponible:.2f}).'
                )

        return cleaned_data