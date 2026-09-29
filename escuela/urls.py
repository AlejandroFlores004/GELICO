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

    path('cde/', views.cdeHomeView, name='home_cde'),
    path('cde/buscar/', views.buscar_cdes, name='buscar_cdes'),
    path('cde/imprimir/', views.cde_imprimir, name='cde_imprimir'),
    path('cde/nuevo/', views.cde_form, name='cde_nuevo'),
    path('cde/<int:pk>/editar/', views.cde_form, name='cde_editar'),
    path('cde/<int:pk>/eliminar/', views.cde_eliminar, name='cde_eliminar'),
]