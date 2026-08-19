from django.urls import path, include
from . import views

urlpatterns = [
    path('auxiliar/', views.auxiliarHomeView, name='home_auxiliar'),
    path('auxiliar/nuevo/', views.auxiliar_form, name='auxiliar_nuevo'),
    path('auxiliar/<int:pk>/editar/', views.auxiliar_form, name='auxiliar_editar'),
]