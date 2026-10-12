from django.urls import path
from . import views

urlpatterns = [
    path('', views.usuariosHomeView, name='home_usuarios'),
    path('buscar/', views.buscar_usuarios, name='buscar_usuarios'),
    path('imprimir/', views.usuario_imprimir, name='usuario_imprimir'),
    path('nuevo/', views.usuario_form, name='usuario_nuevo'),
    path('<int:pk>/editar/', views.usuario_form, name='usuario_editar'),
    path('<int:pk>/contrasena/', views.usuario_contrasena, name='usuario_contrasena'),
    path('<int:pk>/toggle/', views.usuario_toggle_estado, name='usuario_toggle'),
    path('<int:pk>/eliminar/', views.usuario_eliminar, name='usuario_eliminar'),

    path('grupos/', views.gruposHomeView, name='home_grupos'),
    path('grupos/buscar/', views.buscar_grupos, name='buscar_grupos'),
    path('grupos/imprimir/', views.grupo_imprimir, name='grupo_imprimir'),
    path('grupos/nuevo/', views.grupo_form, name='grupo_nuevo'),
    path('grupos/<int:pk>/editar/', views.grupo_form, name='grupo_editar'),
    path('grupos/<int:pk>/eliminar/', views.grupo_eliminar, name='grupo_eliminar'),
]
