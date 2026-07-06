from django.contrib import admin
from .models import Bono


@admin.register(Bono)
class BonoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'descripcion')
    search_fields = ('nombre', 'descripcion')
    ordering = ('nombre',)
    fieldsets = (
        ('Información básica', {
            'fields': ('nombre', 'descripcion')
        }),
    )
