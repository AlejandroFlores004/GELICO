from django.shortcuts import render
from django.urls import reverse
from . import forms
from escuela import models

# Create your views here.
def home_liquidaciones(request):
    
    seleccionarEscuelas = forms.SeleccionarEscuelaForm(request.GET or None)
    seleccionarBonos = forms.SeleccionarBonoForm(request.GET or None)


    breadcrumbs = [
        {'name': 'Inicio', 'url': reverse('home')},
        {'name': 'Liquidaciones', 'url': reverse('home_liquidaciones')},
    ]

    return render(
        request, 
        'liquidacion/liquidacionHome.html', 
        {
            'breadcrumbs': breadcrumbs, 
            'seleccionarEscuelas': seleccionarEscuelas,
            'seleccionarBonos': seleccionarBonos,
        }
    )


def buscar_escuela(request):
    seleccionarEscuelas = forms.SeleccionarEscuelaForm(request.GET or None)

    if seleccionarEscuelas.is_valid():
        escuela = seleccionarEscuelas.cleaned_data['escuela']
        encargado = models.Encargado.objects.filter(escuela=escuela).first()
        return render(
            request,
            'partials/liquidacion/_escuela_info_result.html',
            {'escuela': escuela, 'encargado': encargado}
        )

    return render(request, 'partials/liquidacion/_escuela_info.html', {})