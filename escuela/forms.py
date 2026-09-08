from django import forms
from django_select2.forms import Select2Widget
from .models import Escuela, Encargado, Distrito, Telefono

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
                'nombre': forms.TextInput(attrs={'class': 'input input-bordered w-full', 'placeholder': 'Ej: Juan'}),
                'apellido': forms.TextInput(attrs={'class': 'input input-bordered w-full', 'placeholder': 'Ej: Pérez'}),
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

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if not email.endswith('@clases.edu.sv'):
            raise forms.ValidationError('El correo debe ser institucional (@clases.edu.sv).')
        return email


#Formset para los teléfonos (uno o más) de un Encargado
class BaseTelefonoFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
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
    formset=BaseTelefonoFormSet,
    fields=['numero', 'etiqueta'],
    widgets={
        'numero': forms.TextInput(attrs={'class': 'input input-bordered w-full telefono-input', 'placeholder': '0000-0000'}),
        'etiqueta': forms.Select(attrs={'class': 'select select-bordered w-full'}),
    },
    extra=1,
    can_delete=True,
)


#Formulario para filtrar/Buscar escuelas en el listado
class FiltrarEscuelasForm(forms.Form):
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