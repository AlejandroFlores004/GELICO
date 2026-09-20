from django.urls import path
from . import views

urlpatterns = [
    path('asignacion/', views.home_asignaciones, name='home_asignaciones'),
    path('recibo/', views.home_recibos, name='home_recibos'),
    path('abono/', views.home_abonos, name='home_abonos'),
    path('carga-excel/', views.home_carga_excel, name='home_carga_excel'),
    path('carga-excel/bonos/preview/', views.carga_bonos_preview, name='carga_bonos_preview'),
    path('carga-excel/bonos/confirmar/', views.carga_bonos_confirmar, name='carga_bonos_confirmar'),
    path('carga-excel/recibos/procesar/', views.carga_recibos_procesar, name='carga_recibos_procesar'),
]
