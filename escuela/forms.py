import re

from django import forms
from django_select2.forms import Select2Widget
from .models import Escuela, Encargado, Distrito, CDE, Telefono

# Nombres/apellidos: solo letras (con tildes y ñ), separadas por un espacio,
# guion o apóstrofo; se permite punto en abreviaturas.
# Ej: "María José", "Pérez-Gómez", "D'Aubuisson", "Acevedo vda. Ramírez".
PATRON_NOMBRE = r"[^\W\d_]+\.?(?:[ '\-][^\W\d_]+\.?)*"
PATRON_NOMBRE_HTML = r"\s*[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+\.?([ '\-]+[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+\.?)*\s*"
MENSAJE_NOMBRE = 'Solo se permiten letras (mínimo 2), sin números ni símbolos.'

# Teléfonos de El Salvador: fijos empiezan con 2, celulares con 6 o 7.
PATRON_TELEFONO = r'[267]\d{3}-\d{4}'
MENSAJE_TELEFONO = 'Número inválido: formato 0000-0000 y debe empezar con 2 (fijo), 6 o 7 (celular).'

#Formulario para filtrar/Buscar encargados en el listado
class FiltrarEncargadosForm(forms.Form):
    #Lista desplegable de Todas las escuelas
    escuela = forms.ModelChoiceField(
        queryset=Escuela.objects.all(),
        widget=Select2Widget(attrs={
            'data-placeholder': 'Todas las escuelas',
            'style': 'width: 100%',
            'class': 'select2-daisy',
            'data-allow-clear': 'false', #Esta linea quita la x
        }),
        label='Escuela',
        required=False,
    )
    
    distrito = forms.ModelChoiceField(
        queryset=Distrito.objects.all(),
        widget=Select2Widget(attrs={
            'data-placeholder': 'Todos los distritos',
            'style': 'width: 100%',
            'class': 'select2-daisy',
            'data-allow-clear': 'false',
        }),
        label='Distrito',
        required=False,
    )
     
    #Selector simple con 3 choices fijas.
    estado = forms.ChoiceField(
        choices=[
            ('','Todos'),
            ('1','Activo'),
            ('0','Inactivo'),   
            ],
        required=False,
        widget=forms.Select(attrs={'class': 'select select-bordered w-full'}),
        label='Estado',
    )
    
    #Campo de texto para búsqueda
    texto= forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'input input-bordered w-full',
            'placeholder': 'Nombre,apellido, email',
        }),
        label ='Buscar',
    )
    
    #Formulario para crear o editar un encargado
class EncargadoForm(forms.ModelForm):
    class Meta:
            model = Encargado
            fields = ['nombre', 'apellido', 'email', 'escuela']

            widgets = {
                'nombre': forms.TextInput(attrs={
                    'class': 'input input-bordered w-full', 'placeholder': 'Ej: Juan',
                    'pattern': PATRON_NOMBRE_HTML, 'minlength': 2, 'title': MENSAJE_NOMBRE,
                }),
                'apellido': forms.TextInput(attrs={
                    'class': 'input input-bordered w-full', 'placeholder': 'Ej: Pérez',
                    'pattern': PATRON_NOMBRE_HTML, 'minlength': 2, 'title': MENSAJE_NOMBRE,
                }),
                'email': forms.EmailInput(attrs={'class': 'input input-bordered w-full', 'placeholder': 'nombre.apellido@clases.edu.sv'}),
                'escuela': Select2Widget(attrs={
                    'data-placeholder': 'Seleccione una Escuela',
                    'style': ' width: 100%',
                    'class': 'select2-daisy',
                }),
            }

    def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if self.instance and self.instance.pk:
                self.fields['escuela'].disabled = True

    def _limpiar_nombre(self, campo):
        # Quita espacios de más ("  Juan   Carlos " -> "Juan Carlos")
        valor = ' '.join((self.cleaned_data.get(campo) or '').split())
        if len(valor) < 2 or not re.fullmatch(PATRON_NOMBRE, valor):
            raise forms.ValidationError(MENSAJE_NOMBRE)
        return valor

    def clean_nombre(self):
        return self._limpiar_nombre('nombre')

    def clean_apellido(self):
        return self._limpiar_nombre('apellido')

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if not email.endswith('@clases.edu.sv'):
            raise forms.ValidationError('El correo debe ser institucional (@clases.edu.sv).')
        return email


#Formulario de un teléfono: valida el formato también en el servidor
class TelefonoForm(forms.ModelForm):
    class Meta:
        model = Telefono
        fields = ['numero', 'etiqueta']

    def clean_numero(self):
        numero = (self.cleaned_data.get('numero') or '').strip()
        if numero and not re.fullmatch(PATRON_TELEFONO, numero):
            raise forms.ValidationError(MENSAJE_TELEFONO)
        return numero


#Formset para los teléfonos (uno o más) de un Encargado
class BaseTelefonoFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        # No se permite repetir el mismo número en un encargado
        vistos = set()
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get('DELETE', False):
                continue
            numero = form.cleaned_data.get('numero')
            if not numero:
                continue
            if numero in vistos:
                form.add_error('numero', 'Este número ya fue ingresado.')
            vistos.add(numero)
        if any(self.errors):
            return

        hay_numero = any(
            form.cleaned_data.get('numero') and not form.cleaned_data.get('DELETE', False)
            for form in self.forms
            if form.cleaned_data
        )
        if not hay_numero:
            raise forms.ValidationError('Debe ingresar al menos un número de teléfono.')


TelefonoFormSet = forms.inlineformset_factory(
    Encargado, Telefono,
    form=TelefonoForm,
    formset=BaseTelefonoFormSet,
    fields=['numero', 'etiqueta'],
    widgets={
        'numero': forms.TextInput(attrs={
            'class': 'input input-bordered w-full telefono-input', 'placeholder': '0000-0000',
            'pattern': PATRON_TELEFONO, 'title': MENSAJE_TELEFONO,
        }),
        'etiqueta': forms.Select(attrs={'class': 'select select-bordered w-full'}),
    },
    extra=1,
    can_delete=True,
)


class CDEFilterForm(forms.Form):
    q = forms.CharField(
        required=False,
        label='Buscar',
        widget=forms.TextInput(attrs={
            'class': 'input input-bordered w-full',
            'placeholder': 'Código, nombre o distrito',
        }),
    )
    escuela = forms.ModelChoiceField(
        queryset=Escuela.objects.all().order_by('nombre_corto'),
        required=False,
        label='Escuela',
        widget=Select2Widget(attrs={
            'data-placeholder': 'Seleccione una escuela',
            'style': 'width: 100%',
            'class': 'select2-daisy',
        }),
    )
    distrito = forms.ModelChoiceField(
        queryset=Distrito.objects.all(),
        widget=Select2Widget(attrs={
            'data-placeholder': 'Todos los distritos',
            'style': 'width: 100%',
            'class': 'select2-daisy',
            'data-allow-clear': 'false',
        }),
        label='Distrito',
        required=False,
    )

    estado = forms.ChoiceField(
        choices=[
            ('', 'Todos'),
            ('1', 'Activo'),
            ('0', 'Inactivo'),
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'select select-bordered w-full'}),
        label='Estado',
    )

    texto = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'input input-bordered w-full',
            'placeholder': 'Código, nombre',
        }),
        label='Buscar',
    )


#Formulario para crear o editar una escuela
class EscuelaForm(forms.ModelForm):
    class Meta:
        model = Escuela
        fields = ['codigo', 'nombre', 'nombre_corto', 'distrito']

        widgets = {
            'codigo': forms.TextInput(attrs={'class': 'input input-bordered w-full', 'placeholder': 'Ej: 12319'}),
            'nombre': forms.TextInput(attrs={'class': 'input input-bordered w-full', 'placeholder': 'Ej: C.E. Caserío Las Calderas'}),
            'nombre_corto': forms.TextInput(attrs={'class': 'input input-bordered w-full', 'placeholder': 'Ej: Calderas'}),
            'distrito': Select2Widget(attrs={
                'data-placeholder': 'Seleccione un Distrito',
                'style': 'width: 100%',
                'class': 'select2-daisy',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['escuela'].disabled = True

#Formulario para filtrar/Buscar escuelas en el listado
class FiltrarEscuelasForm(forms.Form):
    escuela = forms.ModelChoiceField(
        queryset=Escuela.objects.select_related('distrito').order_by('nombre_corto'),
        widget=Select2Widget(attrs={
            'data-placeholder': 'Todas las escuelas',
            'style': 'width: 100%',
            'class': 'select2-daisy',
            'data-allow-clear': 'false',
        }),
        label='Escuela',
        required=False,
    )

    distrito = forms.ModelChoiceField(
        queryset=Distrito.objects.all(),
        widget=Select2Widget(attrs={
            'data-placeholder': 'Todos los distritos',
            'style': 'width: 100%',
            'class': 'select2-daisy',
            'data-allow-clear': 'false',
        }),
        label='Distrito',
        required=False,
    )

    estado = forms.ChoiceField(
        choices=[
            ('', 'Todos'),
            ('1', 'Activo'),
            ('0', 'Inactivo'),
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'select select-bordered w-full'}),
        label='Estado',
    )

    texto = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'input input-bordered w-full',
            'placeholder': 'Código, nombre',
        }),
        label='Buscar',
    )


#Formulario para crear o editar una escuela
class EscuelaForm(forms.ModelForm):
    class Meta:
        model = Escuela
        fields = ['codigo', 'nombre', 'nombre_corto', 'distrito']

        widgets = {
            'codigo': forms.TextInput(attrs={'class': 'input input-bordered w-full', 'placeholder': 'Ej: 12319'}),
            'nombre': forms.TextInput(attrs={'class': 'input input-bordered w-full', 'placeholder': 'Ej: C.E. Caserío Las Calderas'}),
            'nombre_corto': forms.TextInput(attrs={'class': 'input input-bordered w-full', 'placeholder': 'Ej: Calderas'}),
            'distrito': Select2Widget(attrs={
                'data-placeholder': 'Seleccione un Distrito',
                'style': 'width: 100%',
                'class': 'select2-daisy',
            }),
        }
