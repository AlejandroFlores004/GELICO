from django.contrib import admin
from .models import Asignacion, Transferencia, Recibo, Observacion


@admin.register(Asignacion)
class AsignacionAdmin(admin.ModelAdmin):
    list_display = ('escuela', 'bono', 'valor')
    list_filter = ('escuela', 'bono')
    search_fields = ('escuela__nombre', 'escuela__nombre_corto', 'bono__nombre')
    ordering = ('escuela__nombre',)
    fieldsets = (
        ('Información básica', {
            'fields': ('valor', 'escuela', 'bono')
        }),
    )


@admin.register(Transferencia)
class TransferenciaAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'asignacion', 'monto')
    list_filter = ('fecha', 'asignacion')
    search_fields = ('asignacion__escuela__nombre', 'asignacion__bono__nombre')
    ordering = ('-fecha',)
    fieldsets = (
        ('Información básica', {
            'fields': ('fecha', 'asignacion', 'monto')
        }),
    )


@admin.register(Recibo)
class ReciboAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'transferencia', 'monto')
    list_filter = ('fecha', 'transferencia')
    search_fields = ('transferencia__asignacion__escuela__nombre', 'transferencia__asignacion__bono__nombre')
    ordering = ('-fecha',)
    fieldsets = (
        ('Información básica', {
            'fields': ('fecha', 'transferencia', 'monto')
        }),
    )


@admin.register(Observacion)
class ObservacionAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'recibo', 'resuelto')
    list_filter = ('resuelto', 'fecha')
    search_fields = ('comentario', 'recibo__transferencia__asignacion__escuela__nombre')
    ordering = ('-fecha',)
    fieldsets = (
        ('Información básica', {
            'fields': ('fecha', 'recibo', 'comentario', 'resuelto')
        }),
    )
