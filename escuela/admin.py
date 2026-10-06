from django.contrib import admin
from .forms import TelefonoForm
from .models import Distrito, Escuela, CDE, Encargado, Telefono


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


class TelefonoInline(admin.TabularInline):
    model = Telefono
    form = TelefonoForm  # misma validación de formato que el modal de encargado
    extra = 1


@admin.register(Encargado)
class EncargadoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'apellido', 'email', 'escuela', 'estado')
    list_filter = ('estado', 'escuela')
    search_fields = ('nombre', 'apellido', 'email', 'telefonos__numero')
    ordering = ('apellido', 'nombre')
    inlines = [TelefonoInline]
    fieldsets = (
        ('Información Personal', {
            'fields': ('nombre', 'apellido')
        }),
        ('Contacto', {
            'fields': ('email',)
        }),
        ('Relaciones', {
            'fields': ('escuela',)
        }),
        ('Estado', {
            'fields': ('estado',)
        }),
    )
