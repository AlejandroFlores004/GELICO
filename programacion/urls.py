from django.urls import path, include
from . import views

urlpatterns = [
    path('auxiliar/', views.auxiliarHomeView, name='home_auxiliar'),
    path('auxiliar/buscar/', views.buscar_auxiliares, name='buscar_auxiliares'),
    path('auxiliar/imprimir/', views.auxiliar_imprimir, name='auxiliar_imprimir'),
    path('auxiliar/nuevo/', views.auxiliar_form, name='auxiliar_nuevo'),
    path('auxiliar/<int:pk>/editar/', views.auxiliar_form, name='auxiliar_editar'),
    path('auxiliar/<int:pk>/eliminar/', views.auxiliar_eliminar, name='auxiliar_eliminar'),
    path('ausencias/', views.ausenciaHomeView, name='home_ausencias'),
    path('ausencias/buscar/', views.buscar_ausencias, name='buscar_ausencias'),
    path('ausencias/imprimir/', views.ausencia_imprimir, name='ausencia_imprimir'),
    path('ausencias/nueva/', views.ausencia_form, name='ausencia_nueva'),
    path('ausencias/<int:pk>/editar/', views.ausencia_form, name='ausencia_editar'),
    path('ausencias/<int:pk>/eliminar/', views.ausencia_eliminar, name='ausencia_eliminar'),
    path('convocatorias/', views.convocatoriasHomeView, name='home_convocatorias'),
    path('convocatorias/buscar/', views.buscar_convocatorias, name='buscar_convocatorias'),
    path('convocatorias/imprimir/', views.convocatoria_imprimir, name='convocatoria_imprimir'),
    path('convocatorias/nueva/', views.convocatoria_form, name='convocatoria_nueva'),
    path('convocatorias/<int:pk>/editar/', views.convocatoria_form, name='convocatoria_editar'),
    path('convocatorias/<int:pk>/eliminar/', views.convocatoria_eliminar, name='convocatoria_eliminar'),
]