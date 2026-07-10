from django.shortcuts import render
from django.urls import reverse

# Create your views here.
def home_liquidaciones(request):
    breadcrumbs = [
        {'name': 'Inicio', 'url': reverse('home')},
        {'name': 'Liquidaciones', 'url': reverse('home_liquidaciones')},
    ]
    return render(
        request, 
        'home_liquidaciones.html', 
        {'breadcrumbs': breadcrumbs}
    )