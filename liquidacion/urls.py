from django.urls import path
from . import views

urlpatterns = [
    path('asignacion/', views.asignacionHomeView, name='home_asignaciones'),
    path('asignacion/buscar/', views.buscar_asignaciones, name='buscar_asignaciones'),
    path('asignacion/imprimir/', views.asignacion_imprimir, name='asignacion_imprimir'),
    path('asignacion/nueva/', views.asignacion_form, name='asignacion_nueva'),
    path('asignacion/<int:pk>/editar/', views.asignacion_form, name='asignacion_editar'),
    path('asignacion/<int:pk>/eliminar/', views.asignacion_eliminar, name='asignacion_eliminar'),
    path('recibo/', views.home_recibos, name='home_recibos'),
    path('abono/', views.home_abonos, name='home_abonos'),
    path('carga-excel/', views.home_carga_excel, name='home_carga_excel'),
    path('carga-excel/bonos/preview/', views.carga_bonos_preview, name='carga_bonos_preview'),
    path('carga-excel/bonos/confirmar/', views.carga_bonos_confirmar, name='carga_bonos_confirmar'),
    path('carga-excel/recibos/procesar/', views.carga_recibos_procesar, name='carga_recibos_procesar'),
]
