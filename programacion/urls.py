from django.urls import path, include
from . import views

urlpatterns = [
    path('auxiliar/', views.auxiliarHomeView, name='home_auxiliar'),
    path('auxiliar/buscar/', views.buscar_auxiliares, name='buscar_auxiliares'),
    path('auxiliar/imprimir/', views.auxiliar_imprimir, name='auxiliar_imprimir'),
    path('auxiliar/nuevo/', views.auxiliar_form, name='auxiliar_nuevo'),
    path('auxiliar/<int:pk>/editar/', views.auxiliar_form, name='auxiliar_editar'),
    path('auxiliar/<int:pk>/eliminar/', views.auxiliar_eliminar, name='auxiliar_eliminar'),
    path('convocatorias/', views.convocatoriasHomeView, name='home_convocatorias'),
    path('convocatorias/buscar/', views.buscar_convocatorias, name='buscar_convocatorias'),
    path('convocatorias/imprimir/', views.convocatoria_imprimir, name='convocatoria_imprimir'),
    path('convocatorias/nueva/', views.convocatoria_form, name='convocatoria_nueva'),
    path('convocatorias/<int:pk>/editar/', views.convocatoria_form, name='convocatoria_editar'),
    path('convocatorias/<int:pk>/eliminar/', views.convocatoria_eliminar, name='convocatoria_eliminar'),
]