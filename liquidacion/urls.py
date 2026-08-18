from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.home_liquidaciones, name='home_liquidaciones'),
    path('escuela/buscar/', views.buscar_escuela, name='buscar_escuela'),

    path('asignaciones/', views.home_asignaciones, name='home_asignaciones'),
    path('asignaciones/buscar/', views.buscar_asignaciones, name='buscar_asignaciones'),
]