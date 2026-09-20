from django.urls import path
from . import views

urlpatterns = [
    path('asignacion/', views.home_asignaciones, name='home_asignaciones'),
    path('recibo/', views.home_recibos, name='home_recibos'),
    path('abono/', views.home_abonos, name='home_abonos'),
    path('carga-excel/', views.home_carga_excel, name='home_carga_excel'),
]
