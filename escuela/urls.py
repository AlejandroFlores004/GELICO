from django.urls import path, include
from . import views

urlpatterns = [
    path('encargado/',views.home_encargados, name='home_encargados'),
    path('encargado/buscar/',views.buscar_encargados, name='encargado_buscar'),
    path('encargado/nuevo/',views.encargado_form, name='encargado_nuevo'),
    path('encargado/<int:pk>/editar/',views.encargado_form, name='encargado_editar'),
    path('encargado/<int:pk>/cambiar/',views.encargado_cambiar, name='encargado_cambiar'),
    path('encargado/<int:pk>/toggle/',views.encargado_toggle_estado, name='encargado_toggle'),
    path('encargado/imprimir/', views.encargado_imprimir, name='encargado_imprimir'),

    path('', views.home_escuelas, name='home_escuelas'),
    path('buscar/', views.buscar_escuelas, name='escuela_buscar'),
    path('nueva/', views.escuela_form, name='escuela_nueva'),
    path('<int:pk>/editar/', views.escuela_form, name='escuela_editar'),
    path('<int:pk>/toggle/', views.escuela_toggle_estado, name='escuela_toggle'),
    path('imprimir/', views.escuela_imprimir, name='escuela_imprimir'),
]