from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path('auditoria/', views.auditoriaHomeView, name='home_auditoria'),
    path('auditoria/buscar/', views.buscar_auditoria, name='buscar_auditoria'),
    path('auditoria/imprimir/', views.auditoria_imprimir, name='auditoria_imprimir'),
    path('auditoria/<int:pk>/', views.auditoria_detalle, name='auditoria_detalle'),
]
