from django.contrib import admin
from .models import Bono


@admin.register(Bono)
class BonoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'id_sistema', 'descripcion')
    search_fields = ('nombre', 'descripcion', 'id_sistema')
    ordering = ('nombre',)
    fieldsets = (
        ('Información básica', {
            'fields': ('nombre', 'id_sistema', 'descripcion')
        }),
    )
