from django import forms
from django_select2.forms import Select2Widget
from .models import Escuela, Encargado

#Formulario para filtrar/Buscar encargados en el listado
class FiltrarEncargadosForm(forms.Form):
    #Lista desplegable de Todas las escuelas
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
            fields = ['nombre', 'apellido', 'telefono', 'email', 'escuela']
            
            widgets = {
                'nombre': forms.TextInput(attrs={'class': 'input input-bordered w-full'}),
                'apellido': forms.TextInput(attrs={'class': 'input input-bordered w-full'}),
                'telefono': forms.TextInput(attrs={'class': 'input input-bordered w-full'}),
                'email': forms.EmailInput(attrs={'class': 'input input-bordered w-full'}),
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