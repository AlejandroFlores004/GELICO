from django.urls import path
from . import views

urlpatterns = [
    path('asignacion/', views.asignacionHomeView, name='home_asignaciones'),
    path('asignacion/buscar/', views.buscar_asignaciones, name='buscar_asignaciones'),
    path('asignacion/imprimir/', views.asignacion_imprimir, name='asignacion_imprimir'),
    path('asignacion/nueva/', views.asignacion_form, name='asignacion_nueva'),
    path('asignacion/<int:pk>/editar/', views.asignacion_form, name='asignacion_editar'),
    path('asignacion/<int:pk>/eliminar/', views.asignacion_eliminar, name='asignacion_eliminar'),
    path('asignacion/<int:pk>/detalle/', views.asignacion_detalle, name='asignacion_detalle'),
    path('asignacion/<int:pk>/gestionar/', views.asignacion_gestionar, name='asignacion_gestionar'),
    path('recibo/<int:pk>/abonos/', views.recibo_abonos, name='recibo_abonos'),
    path('asignacion/<int:asignacion_pk>/recibo/nuevo/', views.recibo_nuevo, name='recibo_nuevo'),
    path('recibo/<int:pk>/editar/', views.recibo_editar, name='recibo_editar'),
    path('recibo/<int:pk>/eliminar/', views.recibo_eliminar, name='recibo_eliminar'),
    path('recibo/<int:recibo_pk>/abono/nuevo/', views.abono_nuevo, name='abono_nuevo'),
    path('abono/<int:pk>/editar/', views.abono_editar, name='abono_editar'),
    path('abono/<int:pk>/eliminar/', views.abono_eliminar, name='abono_eliminar'),
    path('recibo/<int:recibo_pk>/observacion/nueva/', views.observacion_nueva, name='observacion_nueva'),
    path('observacion/<int:pk>/editar/', views.observacion_editar, name='observacion_editar'),
    path('observacion/<int:pk>/eliminar/', views.observacion_eliminar, name='observacion_eliminar'),
    path('observacion/<int:pk>/toggle/', views.observacion_toggle, name='observacion_toggle'),
    path('carga-excel/', views.home_carga_excel, name='home_carga_excel'),
    path('carga-excel/bonos/preview/', views.carga_bonos_preview, name='carga_bonos_preview'),
    path('carga-excel/bonos/confirmar/', views.carga_bonos_confirmar, name='carga_bonos_confirmar'),
    path('carga-excel/recibos/procesar/', views.carga_recibos_procesar, name='carga_recibos_procesar'),
]
