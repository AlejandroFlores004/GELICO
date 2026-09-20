from django.contrib import admin
from .models import Asignacion, Recibo, Abono, Observacion


@admin.register(Asignacion)
class AsignacionAdmin(admin.ModelAdmin):
    list_display = ('bono', 'escuela', 'valor')
    list_filter = ('bono', 'escuela')
    search_fields = ('bono__nombre', 'escuela__nombre', 'escuela__nombre_corto')
    ordering = ('bono',)
    fieldsets = (
        ('Información básica', {
            'fields': ('bono', 'escuela', 'valor')
        }),
    )


@admin.register(Recibo)
class ReciboAdmin(admin.ModelAdmin):
    list_display = ('asignacion', 'monto')
    list_filter = ('asignacion__bono',)
    search_fields = ('asignacion__bono__nombre',)
    ordering = ('-id',)
    fieldsets = (
        ('Información básica', {
            'fields': ('asignacion', 'monto')
        }),
    )


@admin.register(Abono)
class AbonoAdmin(admin.ModelAdmin):
    list_display = ('recibo', 'monto', 'requerimiento', 'estado')
    list_filter = ('estado', 'recibo__asignacion__bono')
    search_fields = ('requerimiento', 'recibo__asignacion__bono__nombre')
    ordering = ('-id',)
    fieldsets = (
        ('Información básica', {
            'fields': ('recibo', 'monto', 'requerimiento', 'estado')
        }),
    )


@admin.register(Observacion)
class ObservacionAdmin(admin.ModelAdmin):
    list_display = ('recibo', 'resuelta', 'descripcion')
    list_filter = ('resuelta', 'recibo__asignacion__bono')
    search_fields = ('descripcion', 'recibo__asignacion__bono__nombre')
    ordering = ('-id',)
    fieldsets = (
        ('Información básica', {
            'fields': ('recibo', 'descripcion', 'resuelta')
        }),
    )
