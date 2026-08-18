from django.urls import path, include
from . import views

urlpatterns = [
    path('encargado/',views.encargadoHomeView, name='home_encargados')
]