from django.shortcuts import render
from django.urls import reverse
from . import forms

# Create your views here.
def home_liquidaciones(request):
    
    seleccionarEscuelas = forms.SeleccionarEscuelaForm(request.GET or None)


    breadcrumbs = [
        {'name': 'Inicio', 'url': reverse('home')},
        {'name': 'Liquidaciones', 'url': reverse('home_liquidaciones')},
    ]

    return render(
        request, 
        'home_liquidaciones.html', 
        {
            'breadcrumbs': breadcrumbs, 
            'seleccionarEscuelas': seleccionarEscuelas
        }
    )