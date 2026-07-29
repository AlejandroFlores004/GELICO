from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.home_liquidaciones, name='home_liquidaciones'),
    path('escuela/buscar/', views.buscar_escuela, name='buscar_escuela'),
]