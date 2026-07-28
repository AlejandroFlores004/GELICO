from django.urls import path, include
from . import views

urlpatterns = [
    path('auxiliar/',views.auxiliarHomeView, name='auxliar')
]