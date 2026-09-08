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
    #Estos 4 campos no son del modelo Encargado, son de Telefono (relación aparte)
    telefono_fijo = forms.CharField(
        required=False,
        label='Teléfono Fijo',
        widget=forms.TextInput(attrs={'class': 'input input-bordered w-full', 'placeholder': '0000-0000'}),
    )
    etiqueta_fijo = forms.ChoiceField(
        choices=Telefono.Etiqueta.choices,
        required=False,
        initial=Telefono.Etiqueta.INSTITUCIONAL,
        label='Etiqueta',
        widget=forms.Select(attrs={'class': 'select select-bordered w-full'}),
    )
    telefono_celular = forms.CharField(
        required=False,
        label='Teléfono Celular',
        widget=forms.TextInput(attrs={'class': 'input input-bordered w-full', 'placeholder': '0000-0000'}),
    )
    etiqueta_celular = forms.ChoiceField(
        choices=Telefono.Etiqueta.choices,
        required=False,
        initial=Telefono.Etiqueta.PERSONAL,
        label='Etiqueta',
        widget=forms.Select(attrs={'class': 'select select-bordered w-full'}),
    )

    class Meta:
            model = Encargado
            fields = ['nombre', 'apellido', 'email', 'escuela']

            widgets = {
                'nombre': forms.TextInput(attrs={'class': 'input input-bordered w-full', 'placeholder': 'Ej: Juan'}),
                'apellido': forms.TextInput(attrs={'class': 'input input-bordered w-full', 'placeholder': 'Ej: Pérez'}),
                'email': forms.EmailInput(attrs={'class': 'input input-bordered w-full', 'placeholder': 'correo@ejemplo.com'}),
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
                telefono_fijo = self.instance.telefonos.filter(tipo=Telefono.Tipo.FIJO).first()
                telefono_celular = self.instance.telefonos.filter(tipo=Telefono.Tipo.CELULAR).first()
                if telefono_fijo:
                    self.fields['telefono_fijo'].initial = telefono_fijo.numero
                    self.fields['etiqueta_fijo'].initial = telefono_fijo.etiqueta
                if telefono_celular:
                    self.fields['telefono_celular'].initial = telefono_celular.numero
                    self.fields['etiqueta_celular'].initial = telefono_celular.etiqueta

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get('telefono_fijo') and not cleaned_data.get('telefono_celular'):
            raise forms.ValidationError('Debe ingresar al menos un número de teléfono (fijo o celular).')
        return cleaned_data

    def save(self, commit=True):
        encargado = super().save(commit=commit)

        def _guardar_telefono(tipo, numero, etiqueta):
            numero = (numero or '').strip()
            if numero:
                Telefono.objects.update_or_create(
                    encargado=encargado, tipo=tipo,
                    defaults={'numero': numero, 'etiqueta': etiqueta or Telefono.Etiqueta.PERSONAL},
                )
            else:
                Telefono.objects.filter(encargado=encargado, tipo=tipo).delete()

        if commit:
            _guardar_telefono(Telefono.Tipo.FIJO, self.cleaned_data.get('telefono_fijo'), self.cleaned_data.get('etiqueta_fijo'))
            _guardar_telefono(Telefono.Tipo.CELULAR, self.cleaned_data.get('telefono_celular'), self.cleaned_data.get('etiqueta_celular'))

        return encargado


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