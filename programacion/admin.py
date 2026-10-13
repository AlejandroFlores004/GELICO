from django.contrib import admin
from .models import Convocatoria, ConvocatoriaAuxiliar, Auxiliar, Programacion, Horario, Ausencia


class ConvocatoriaAuxiliarInline(admin.TabularInline):
    model = ConvocatoriaAuxiliar
    extra = 0
    autocomplete_fields = ('auxiliar',)


@admin.register(Convocatoria)
class ConvocatoriaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'fecha_inicio', 'fecha_fin')
    search_fields = ('nombre', 'descripcion')
    ordering = ('fecha_inicio',)
    inlines = (ConvocatoriaAuxiliarInline,)
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
    list_display = ('convocatoria', 'fecha_programada', 'jornada', 'estado', 'escuela')
    list_filter = ('estado', 'jornada', 'convocatoria', 'fecha_programada')
    search_fields = ('convocatoria__nombre', 'escuela__nombre', 'escuela__nombre_corto')
    ordering = ('-fecha_programada',)
    fieldsets = (
        ('Información básica', {
            'fields': ('convocatoria', 'fecha_programada', 'jornada', 'estado', 'escuela')
        }),
    )


@admin.register(Horario)
class HorarioAdmin(admin.ModelAdmin):
    list_display = ('auxiliar', 'dia', 'jornada', 'fecha_inicio', 'fecha_fin')
    list_filter = ('dia', 'auxiliar')
    search_fields = ('auxiliar__nombre', 'auxiliar__apellido')
    ordering = ('auxiliar', 'dia')
    fieldsets = (
        ('Información básica', {
            'fields': ('auxiliar', 'dia', 'jornada')
        }),
        ('Periodo de labores', {
            'fields': ('fecha_inicio', 'fecha_fin')
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
