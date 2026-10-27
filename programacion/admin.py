from django.contrib import admin
from .models import Asistencia, Convocatoria, ConvocatoriaPersonal, Personal, Programacion, Horario


class ConvocatoriaPersonalInline(admin.TabularInline):
    model = ConvocatoriaPersonal
    extra = 0
    autocomplete_fields = ('persona',)


@admin.register(Convocatoria)
class ConvocatoriaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'fecha_inicio', 'fecha_fin')
    search_fields = ('nombre', 'descripcion')
    ordering = ('fecha_inicio',)
    inlines = (ConvocatoriaPersonalInline,)
    fieldsets = (
        ('Información básica', {
            'fields': ('nombre', 'descripcion', 'fecha_inicio', 'fecha_fin')
        }),
    )


@admin.register(Personal)
class PersonalAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'apellido', 'tipo', 'activo', 'cargo', 'institucion', 'email', 'telefono')
    list_filter = ('tipo', 'activo')
    search_fields = ('nombre', 'apellido', 'email', 'cargo', 'institucion')
    ordering = ('apellido', 'nombre')
    fieldsets = (
        ('Información personal', {
            'fields': ('tipo', 'nombre', 'apellido', 'email', 'telefono', 'activo')
        }),
        ('Planta / práctica', {
            'fields': ('cargo', 'institucion')
        }),
    )

    def has_delete_permission(self, request, obj=None):
        # Se desactiva en lugar de eliminar, para no perder su asistencia ni sus asignaciones.
        return False


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
    list_display = ('persona', 'dia', 'jornada', 'fecha_inicio', 'fecha_fin')
    list_filter = ('dia', 'persona')
    search_fields = ('persona__nombre', 'persona__apellido')
    ordering = ('persona', 'dia')
    fieldsets = (
        ('Información básica', {
            'fields': ('persona', 'dia', 'jornada')
        }),
        ('Periodo de labores', {
            'fields': ('fecha_inicio', 'fecha_fin')
        }),
    )


@admin.register(Asistencia)
class AsistenciaAdmin(admin.ModelAdmin):
    list_display = ('persona', 'fecha', 'estado', 'observacion')
    list_filter = ('estado', 'fecha')
    search_fields = ('persona__nombre', 'persona__apellido', 'observacion')
    autocomplete_fields = ('persona',)
    ordering = ('-fecha',)
    fieldsets = (
        ('Información básica', {
            'fields': ('persona', 'fecha', 'estado', 'observacion')
        }),
    )
