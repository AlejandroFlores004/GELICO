from django import forms
from django_select2.forms import Select2Widget
from .models import Escuela, Encargado, Distrito, CDE

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
        queryset=Distrito.objects.all().order_by('nombre'),
        required=False,
        label='Distrito',
        widget=Select2Widget(attrs={
            'data-placeholder': 'Todos los distritos',
            'style': 'width: 100%',
            'class': 'select2-daisy',
            'data-allow-clear': 'false',
        }),
    )
    fecha_inicio = forms.DateField(
        required=False,
        label='Desde',
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'input input-bordered w-full',
        }),
    )
    fecha_fin = forms.DateField(
        required=False,
        label='Hasta',
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'input input-bordered w-full',
        }),
    )


class CDEForm(forms.ModelForm):
    class Meta:
        model = CDE
        fields = ['FechaInicio', 'FechaFin', 'escuela']
        labels = {
            'FechaInicio': 'Fecha Inicio',
            'FechaFin': 'Fecha Fin',
            'escuela': 'Escuela',
        }

        widgets = {
            'FechaInicio': forms.DateInput(
                attrs={
                    'type': 'date',
                    'class': 'input input-bordered w-full',
                }
            ),
            'FechaFin': forms.DateInput(
                attrs={
                    'type': 'date',
                    'class': 'input input-bordered w-full',
                }
            ),
            'escuela': Select2Widget(attrs={
                'data-placeholder': 'Seleccione una escuela',
                'style': 'width: 100%; display: none !important;',
                'class': 'select2-daisy',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['escuela'].disabled = True