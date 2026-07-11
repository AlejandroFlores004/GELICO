from django.contrib import admin
from .models import Distrito, Escuela, CDE, Encargado


@admin.register(Distrito)
class DistritoAdmin(admin.ModelAdmin):
    list_display = ('nombre',)
    search_fields = ('nombre',)
    ordering = ('nombre',)


@admin.register(Escuela)
class EscuelaAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre', 'nombre_corto', 'distrito', 'estado')
    list_filter = ('estado', 'distrito')
    search_fields = ('codigo', 'nombre', 'nombre_corto','distrito__nombre')
    ordering = ('codigo',)
    fieldsets = (
        ('Información Básica', {
            'fields': ('codigo', 'nombre', 'nombre_corto')
        }),
        ('Relaciones', {
            'fields': ('distrito',)
        }),
        ('Estado', {
            'fields': ('estado',)
        }),
    )


@admin.register(CDE)
class CDEAdmin(admin.ModelAdmin):
    list_display = ('escuela', 'FechaInicio', 'FechaFin', 'estado')
    list_filter = ('estado', 'escuela', 'FechaInicio')
    search_fields = ('escuela__nombre',)
    ordering = ('-FechaInicio',)
    fieldsets = (
        ('Fechas', {
            'fields': ('FechaInicio', 'FechaFin')
        }),
        ('Relaciones', {
            'fields': ('escuela',)
        }),
        ('Estado', {
            'fields': ('estado',)
        }),
    )


@admin.register(Encargado)
class EncargadoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'apellido', 'email', 'telefono', 'escuela', 'estado')
    list_filter = ('estado', 'escuela')
    search_fields = ('nombre', 'apellido', 'email', 'telefono')
    ordering = ('apellido', 'nombre')
    fieldsets = (
        ('Información Personal', {
            'fields': ('nombre', 'apellido')
        }),
        ('Contacto', {
            'fields': ('email', 'telefono')
        }),
        ('Relaciones', {
            'fields': ('escuela',)
        }),
        ('Estado', {
            'fields': ('estado',)
        }),
    )
