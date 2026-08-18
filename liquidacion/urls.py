from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.home_liquidaciones, name='home_liquidaciones'),
    path('escuela/buscar/', views.buscar_escuela, name='buscar_escuela'),

    path('asignaciones/', views.home_asignaciones, name='home_asignaciones'),
<<<<<<< HEAD
<<<<<<< HEAD
    path('asignaciones/buscar/', views.buscar_asignaciones, name='buscar_asignaciones'),
    path('asignaciones/nueva/', views.asignacion_form, name='asignacion_nueva'),
    path('asignaciones/<int:pk>/editar/', views.asignacion_form, name='asignacion_editar'),
=======
>>>>>>> 4ae7a94 (Add asignaciones feature with search and listing functionality)
=======
    path('asignaciones/buscar/', views.buscar_asignaciones, name='buscar_asignaciones'),
    path('asignaciones/nueva/', views.asignacion_form, name='asignacion_nueva'),
    path('asignaciones/<int:pk>/editar/', views.asignacion_form, name='asignacion_editar'),
]