from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.home_liquidaciones, name='home_liquidaciones'),
    path('escuela/buscar/', views.buscar_escuela, name='buscar_escuela'),
    path('bono/buscar/', views.buscar_bono, name='buscar_bono'),
    path('recibos/nuevo/', views.recibo_form, name='recibo_nuevo'),
    path('recibos/<int:pk>/editar/', views.recibo_form, name='recibo_editar'),
    path('recibos/<int:pk>/eliminar/', views.recibo_eliminar, name='recibo_eliminar'),
    path('recibos/<int:recibo_pk>/observaciones/nueva/', views.observacion_crear, name='observacion_crear'),
    path('observaciones/<int:pk>/resolver/', views.observacion_resolver, name='observacion_resolver'),

    path('asignaciones/', views.home_asignaciones, name='home_asignaciones'),
    path('asignaciones/buscar/', views.buscar_asignaciones, name='buscar_asignaciones'),
    path('asignaciones/imprimir/', views.asignacion_imprimir, name='asignacion_imprimir'),
    path('asignaciones/nueva/', views.asignacion_form, name='asignacion_nueva'),
    path('asignaciones/<int:pk>/editar/', views.asignacion_form, name='asignacion_editar'),
    path('asignaciones/<int:pk>/eliminar/', views.asignacion_eliminar, name='asignacion_eliminar'),

    path('transferencias/', views.home_transferencias, name='home_transferencias'),
    path('transferencias/buscar/', views.buscar_transferencias, name='buscar_transferencias'),
    path('transferencias/asignaciones-por-escuela/', views.transferencia_asignaciones_por_escuela, name='transferencia_asignaciones_por_escuela'),
    path('transferencias/saldo-asignacion/', views.transferencia_saldo_asignacion, name='transferencia_saldo_asignacion'),
    path('transferencias/nueva/', views.transferencia_form, name='transferencia_nueva'),
    path('transferencias/<int:pk>/eliminar/', views.transferencia_eliminar, name='transferencia_eliminar'),
]