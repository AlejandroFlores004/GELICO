from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path('notificaciones/', views.notificacionesHomeView, name='home_notificaciones'),
    path('notificaciones/campana/', views.notificaciones_campana, name='notificaciones_campana'),
    path('reportes/', views.reportesHomeView, name='home_reportes'),
    path('reportes/<slug:reporte>/', views.reporte_individual, name='reporte_individual'),
    path('auditoria/', views.auditoriaHomeView, name='home_auditoria'),
    path('auditoria/buscar/', views.buscar_auditoria, name='buscar_auditoria'),
    path('auditoria/imprimir/', views.auditoria_imprimir, name='auditoria_imprimir'),
    path('auditoria/<int:pk>/', views.auditoria_detalle, name='auditoria_detalle'),
]
