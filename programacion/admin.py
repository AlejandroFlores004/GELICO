from django.contrib import admin
from .models import Convocatoria, Auxiliar, Programacion, Horario, Ausencia


@admin.register(Convocatoria)
class ConvocatoriaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'fecha_inicio', 'fecha_fin')
    search_fields = ('nombre', 'descripcion')
    ordering = ('fecha_inicio',)
    fieldsets = (
        ('Información básica', {
            'fields': ('nombre', 'descripcion', 'fecha_inicio', 'fecha_fin')
        }),
    )


@admin.register(Auxiliar)
class AuxiliarAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'apellido', 'email', 'telefono', 'institucion')
    search_fields = ('nombre', 'apellido', 'email', 'institucion')
    ordering = ('apellido', 'nombre')
    fieldsets = (
        ('Información personal', {
            'fields': ('nombre', 'apellido', 'email', 'telefono', 'institucion')
        }),
    )


@admin.register(Programacion)
class ProgramacionAdmin(admin.ModelAdmin):
    list_display = ('convocatoria', 'auxiliar', 'fecha_programada', 'hora_programada', 'estado', 'escuela')
    list_filter = ('estado', 'convocatoria', 'fecha_programada')
    search_fields = ('convocatoria__nombre', 'auxiliar__nombre', 'auxiliar__apellido')
    ordering = ('-fecha_programada', '-hora_programada')
    fieldsets = (
        ('Información básica', {
            'fields': ('convocatoria', 'auxiliar', 'fecha_programada', 'hora_programada', 'estado', 'escuela')
        }),
    )


@admin.register(Horario)
class HorarioAdmin(admin.ModelAdmin):
    list_display = ('auxiliar', 'fecha', 'hora_inicio', 'hora_fin')
    list_filter = ('fecha', 'auxiliar')
    search_fields = ('auxiliar__nombre', 'auxiliar__apellido')
    ordering = ('-fecha', 'hora_inicio')
    fieldsets = (
        ('Información básica', {
            'fields': ('auxiliar', 'fecha', 'hora_inicio', 'hora_fin')
        }),
    )


@admin.register(Ausencia)
class AusenciaAdmin(admin.ModelAdmin):
    list_display = ('auxiliar', 'fecha', 'motivo')
    list_filter = ('fecha', 'auxiliar')
    search_fields = ('auxiliar__nombre', 'auxiliar__apellido', 'motivo')
    ordering = ('-fecha',)
    fieldsets = (
        ('Información básica', {
            'fields': ('auxiliar', 'fecha', 'motivo')
        }),
    )
