from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from . import forms
from escuela.models import Escuela, Encargado
from .models import Asignacion

# Create your views here.


#Liquidaciones views
def home_liquidaciones(request):

    seleccionarEscuelas = forms.SeleccionarEscuelaForm(request.GET or None)
    seleccionarBono = forms.SeleccionarBonoForm()

#Liquidaciones views
def home_liquidaciones(request):

    seleccionarEscuelas = forms.SeleccionarEscuelaForm(request.GET or None)
    seleccionarBono = forms.SeleccionarBonoForm()

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
            'seleccionarBono': seleccionarBono,
            'form_media': seleccionarEscuelas.media + seleccionarBono.media,
        }
    )


def buscar_escuela(request):
    seleccionarEscuelas = forms.SeleccionarEscuelaForm(request.GET or None)

    if seleccionarEscuelas.is_valid():
        escuela = seleccionarEscuelas.cleaned_data['escuela']
        encargado = Encargado.objects.filter(escuela=escuela).first()
        seleccionarBono = forms.SeleccionarBonoForm(escuela=escuela)
        return render(
            request,
            'partials/liquidacion/_escuela_info_result.html',
            {'escuela': escuela, 'encargado': encargado}
        )

    return render(request, 'partials/liquidacion/_escuela_info.html', {})