from urllib.parse import urlparse

from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.dateparse import parse_date
from django_htmx.http import HttpResponseClientRedirect
from weasyprint import HTML
from django.core.paginator import Paginator
from django.db.models import Prefetch, Q
from django.shortcuts import render, get_object_or_404
from django.urls import Resolver404, resolve, reverse
from . import forms
from .models import Encargado, CDE, Escuela


def _escuela_en_gestion(request):
    """Si la petición htmx viene de la página "Gestionar" de una escuela,
    devuelve esa escuela. Así los modales de encargado y CDE saben que deben
    usar esa escuela y recargar esa página al guardar."""
    url_actual = request.htmx.current_url if request.htmx else None
    if not url_actual:
        return None
    try:
        coincidencia = resolve(urlparse(url_actual).path)
    except Resolver404:
        return None
    if coincidencia.url_name != 'escuela_gestionar':
        return None
    return Escuela.objects.filter(pk=coincidencia.kwargs['pk']).first()


def _recargar_gestion(escuela):
    """Cierra el modal y recarga la página "Gestionar" de la escuela."""
    return HttpResponseClientRedirect(reverse('escuela_gestionar', args=[escuela.pk]))

def _encargados_filtrados(request):
    # exactamente el cuerpo que ya tenías en _filtrar_encargados, PERO sin el Paginator
    filtro_form = forms.FiltrarEncargadosForm(request.GET or None)

    encargados_list = Encargado.objects.select_related(
        'escuela', 'escuela__distrito'
    ).prefetch_related('telefonos').order_by('escuela__nombre_corto', '-estado', 'apellido')

    if filtro_form.is_valid():
        escuela = filtro_form.cleaned_data.get('escuela')
        estado = filtro_form.cleaned_data.get('estado')
        texto = filtro_form.cleaned_data.get('texto')
        distrito = filtro_form.cleaned_data.get('distrito')

        if distrito:
            encargados_list = encargados_list.filter(escuela__distrito=distrito)
        if escuela:
            encargados_list = encargados_list.filter(escuela=escuela)
        if estado:
            encargados_list = encargados_list.filter(estado=(estado == '1'))
        if texto:
            encargados_list = encargados_list.filter(
                Q(nombre__icontains=texto) |
                Q(apellido__icontains=texto) |
                Q(email__icontains=texto)
            )

    return filtro_form, encargados_list


def _filtrar_encargados(request):
    # ahora esta SOLO agrega la paginación, reutilizando la de arriba
    filtro_form, encargados_list = _encargados_filtrados(request)

    paginator = Paginator(encargados_list, 20)
    encargados = paginator.get_page(request.GET.get('page'))

    return filtro_form, encargados

def encargado_imprimir(request):
    _, encargados = _encargados_filtrados(request)

    html_string = render_to_string(
        'partials/encargado/_encargado_reporte_pdf.html',
        {'encargados': encargados, 'fecha_generacion': timezone.localdate()}
    )
    pdf = HTML(string=html_string, base_url=request.build_absolute_uri('/')).write_pdf()

    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="Encargados.pdf"'
    return response


def home_encargados(request):
    breadcrumbs = [
        {'name': 'Inicio', 'url': reverse('home')},
        {'name': 'Encargados', 'url': reverse('home_encargados')},
    ]
    
    filtro_form, encargados = _filtrar_encargados(request)
    
    return render(
        request, 'encargado/encargadoHome.html',
        {
            'breadcrumbs': breadcrumbs,
            'encargados': encargados,
            'filtro_form': filtro_form,
            'form_media': filtro_form.media, ##JS,CSS que usa el Select2
        }
    )

#Se utilizacuando se oprime buscar

def buscar_encargados(request):
    _, encargados = _filtrar_encargados(request)
    
    return render(
        request,
        'partials/encargado/_listado_encargados.html',
        {'encargados': encargados}
    )
    
    
#Sirve para crear y Editar
def encargado_form(request, pk=None):
    #Si pk es None, se crea un nuevo encargado, si no, se edita el encargado 
    # con ese pk.
    instance = get_object_or_404(Encargado, pk=pk) if pk else None
    escuela_gestion = _escuela_en_gestion(request)
    # Desde "Gestionar escuela" el encargado nuevo ya va con esa escuela fija
    initial = {'escuela': escuela_gestion.pk} if escuela_gestion and not instance else None
    if request.method == 'POST':
        form = forms.EncargadoForm(request.POST, instance=instance, prefix='encargado', initial=initial)
        if escuela_gestion:
            form.fields['escuela'].disabled = True
        formset = forms.TelefonoFormSet(request.POST, instance=instance, prefix='telefonos')
        if form.is_valid() and formset.is_valid():
            es_nuevo = instance is None
            encargado = form.save() #Guarda (crea o actualiza) en la bd
            formset.instance = encargado #Necesario cuando instance era None (creación)
            formset.save()
            if es_nuevo and encargado.estado:
                # Al crear un encargado nuevo (activo por defecto), desactiva
                # a los demás encargados activos de la misma escuela.
                Encargado.objects.filter(
                    escuela=encargado.escuela, estado=True
                ).exclude(pk=encargado.pk).update(estado=False)
            if escuela_gestion:
                return _recargar_gestion(escuela_gestion)
            _, encargados = _filtrar_encargados(request)
            return render(
                request,
                'partials/encargado/_encargado_form_success.html',
                {'encargados': encargados}
            )
    else:
        #Primera vez que se carga el formulario, se crea el formulario
        # con la instancia del encargado
        form = forms.EncargadoForm(instance=instance, prefix='encargado', initial=initial)
        if escuela_gestion:
            form.fields['escuela'].disabled = True
        formset = forms.TelefonoFormSet(instance=instance, prefix='telefonos')

    return render(
         request,
       'partials/encargado/_encargado_form_modal.html',
         {'form': form, 'formset': formset, 'instance': instance, 'escuela_gestion': escuela_gestion}
     )

# Cambiar Encargado: Crea un nuevo encargado y desactiva el anterior.

def encargado_cambiar(request, pk):
    activo = get_object_or_404(Encargado, pk=pk)
    nuevo_instance = Encargado(escuela=activo.escuela)
    
    if request.method == 'POST':
        form = forms.EncargadoForm(request.POST, instance=nuevo_instance, prefix='encargado')
        #Siempre se bloquea la escuela
        form.fields['escuela'].disabled = True
        formset = forms.TelefonoFormSet(request.POST, instance=nuevo_instance, prefix='telefonos')

        if form.is_valid() and formset.is_valid():
            encargado = form.save() #Guarda al nuevo encargado
            formset.instance = encargado
            formset.save()
            activo.estado = False #El anterior encargado pasa a inactivo
            activo.save() # El anterior pasa a inactivo
            escuela_gestion = _escuela_en_gestion(request)
            if escuela_gestion:
                return _recargar_gestion(escuela_gestion)
            _, encargados = _filtrar_encargados(request)
            return render(request, 'partials/encargado/_encargado_form_success.html',
                          {'encargados': encargados}
            )
    else:
            form = forms.EncargadoForm(instance=nuevo_instance, prefix='encargado')
            form.fields['escuela'].disabled = True
            formset = forms.TelefonoFormSet(instance=nuevo_instance, prefix='telefonos')

    return render(
            request,
            'partials/encargado/_encargado_form_modal.html',
            {'form': form, 'formset': formset, 'instance': None, 'cambiar': True, 'activo': activo}
        )
    
# Cambiar estado de un encargado, activo/inactivo
def encargado_toggle_estado(request, pk):
    encargado = get_object_or_404(Encargado, pk=pk)
    
    if request.method == 'POST':
        encargado.estado = not encargado.estado
        encargado.save()
        
        if encargado.estado:
            Encargado.objects.filter(
                escuela=encargado.escuela, estado=True
            ).exclude(pk=encargado.pk).update(estado=False)

        escuela_gestion = _escuela_en_gestion(request)
        if escuela_gestion:
            return _recargar_gestion(escuela_gestion)

        _, encargados = _filtrar_encargados(request)
        
        return render( request,
                      'partials/encargado/_encargado_form_success.html',
                      {'encargados': encargados}
        )
        
        #Modal de confirmación para cambiar el estado de un encargado
    return render( request,
                      'partials/encargado/_encargado_toggle_confirm.html',
                      {'encargado': encargado}
        )


def _cdes_filtrados(request):
    filtro_form = forms.CDEFilterForm(request.GET or None)

    cdes = CDE.objects.select_related('escuela', 'escuela__distrito').order_by('FechaInicio', 'escuela__nombre_corto')

    if filtro_form.is_valid():
        escuela = filtro_form.cleaned_data.get('escuela')
        distrito = filtro_form.cleaned_data.get('distrito')
        search = (filtro_form.cleaned_data.get('q') or '').strip()
        fecha_inicio = filtro_form.cleaned_data.get('fecha_inicio')
        fecha_fin = filtro_form.cleaned_data.get('fecha_fin')

        if distrito:
            cdes = cdes.filter(escuela__distrito=distrito)
        if escuela:
            cdes = cdes.filter(escuela=escuela)
        if search:
            cdes = cdes.filter(
                Q(escuela__nombre__icontains=search) |
                Q(escuela__codigo__icontains=search) |
                Q(escuela__nombre_corto__icontains=search) |
                Q(escuela__distrito__nombre__icontains=search)
            )
        if fecha_inicio:
            cdes = cdes.filter(FechaInicio__gte=fecha_inicio)
        if fecha_fin:
            cdes = cdes.filter(FechaFin__lte=fecha_fin)
    else:
        search = (request.GET.get('q', '') or '').strip()
        fecha_inicio = request.GET.get('fecha_inicio', '').strip()
        fecha_fin = request.GET.get('fecha_fin', '').strip()

    return filtro_form, search, fecha_inicio, fecha_fin, cdes


def _filtrar_cdes(request):
    filtro_form, search, fecha_inicio, fecha_fin, cdes_list = _cdes_filtrados(request)
    paginator = Paginator(cdes_list, 20)
    cdes = paginator.get_page(request.GET.get('page'))
    return filtro_form, search, fecha_inicio, fecha_fin, cdes


def cdeHomeView(request):
    filtro_form, search, fecha_inicio, fecha_fin, cdes = _filtrar_cdes(request)

    return render(
        request,
        'cde/cdeHome.html',
        {
            'cdes': cdes,
            'search': search,
            'fecha_inicio': fecha_inicio,
            'fecha_fin': fecha_fin,
            'filtro_form': filtro_form,
            'form_media': filtro_form.media,
        },
    )


def buscar_cdes(request):
    _, _, _, _, cdes = _filtrar_cdes(request)

    return render(
        request,
        'partials/cde/tabla.html',
        {'cdes': cdes},
    )


def cde_form(request, pk=None):
    instance = get_object_or_404(CDE, pk=pk) if pk else None
    escuela_gestion = _escuela_en_gestion(request)
    # Desde "Gestionar escuela" el CDE nuevo ya va con esa escuela fija
    initial = {'escuela': escuela_gestion.pk} if escuela_gestion and not instance else None

    if request.method == 'POST':
        form = forms.CDEForm(request.POST, instance=instance, initial=initial)
        if escuela_gestion:
            form.fields['escuela'].disabled = True
        if form.is_valid():
            form.save()
            if escuela_gestion:
                return _recargar_gestion(escuela_gestion)
            _, _, _, _, cdes = _filtrar_cdes(request)
            return render(
                request,
                'partials/cde/modal_form_success.html',
                {'cdes': cdes},
            )
    else:
        form = forms.CDEForm(instance=instance, initial=initial)
        if escuela_gestion:
            form.fields['escuela'].disabled = True

    return render(
        request,
        'partials/cde/modal_form.html',
        {'form': form, 'instance': instance, 'escuela_gestion': escuela_gestion},
    )


def cde_eliminar(request, pk):
    instance = get_object_or_404(CDE, pk=pk)

    if request.method == 'POST':
        instance.delete()
        escuela_gestion = _escuela_en_gestion(request)
        if escuela_gestion:
            return _recargar_gestion(escuela_gestion)
        _, _, _, _, cdes = _filtrar_cdes(request)
        return render(
            request,
            'partials/cde/modal_form_success.html',
            {'cdes': cdes},
        )

    return render(
        request,
        'partials/cde/modal_delete.html',
        {'instance': instance},
    )


def cde_imprimir(request):
    _, _, _, _, cdes = _cdes_filtrados(request)
    html_string = render_to_string(
        'partials/cde/reporte_pdf.html',
        {'cdes': cdes},
    )
    pdf = HTML(string=html_string, base_url=request.build_absolute_uri('/')).write_pdf()

    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="cdes.pdf"'
    return response



# ===================== Escuelas =====================

def _escuelas_filtradas(request):
    filtro_form = forms.FiltrarEscuelasForm(request.GET or None)

    escuelas_list = Escuela.objects.select_related('distrito').order_by('codigo')

    if filtro_form.is_valid():
        escuela = filtro_form.cleaned_data.get('escuela')
        distrito = filtro_form.cleaned_data.get('distrito')
        estado = filtro_form.cleaned_data.get('estado')
        texto = filtro_form.cleaned_data.get('texto')

        if escuela:
            escuelas_list = escuelas_list.filter(pk=escuela.pk)
        if distrito:
            escuelas_list = escuelas_list.filter(distrito=distrito)
        if estado:
            escuelas_list = escuelas_list.filter(estado=(estado == '1'))
        if texto:
            escuelas_list = escuelas_list.filter(
                Q(codigo__icontains=texto) |
                Q(nombre__icontains=texto) |
                Q(nombre_corto__icontains=texto)
            )

    return filtro_form, escuelas_list


def _con_encargado_y_cde(escuelas):
    # Encargado activo (con sus teléfonos) y CDE activos de cada escuela, sin N+1
    return escuelas.prefetch_related(
        Prefetch(
            'encargado_set',
            queryset=Encargado.objects.filter(estado=True).prefetch_related('telefonos'),
            to_attr='encargados_activos',
        ),
        Prefetch(
            'cde_set',
            queryset=CDE.objects.filter(estado=True).order_by('-FechaInicio'),
            to_attr='cdes_activos',
        ),
    )


def _hay_filtros(filtro_form):
    return filtro_form.is_valid() and any(filtro_form.cleaned_data.values())


def _filtrar_escuelas(request):
    filtro_form, escuelas_list = _escuelas_filtradas(request)

    # Sin filtros no se lista nada: la página arranca solo con el buscador.
    if not _hay_filtros(filtro_form):
        return filtro_form, None

    paginator = Paginator(_con_encargado_y_cde(escuelas_list), 20)
    escuelas = paginator.get_page(request.GET.get('page'))

    return filtro_form, escuelas


def _respuesta_pdf(request, template, contexto, nombre_archivo):
    html_string = render_to_string(
        template,
        {'fecha_generacion': timezone.localdate(), 'fecha_impresion': timezone.localtime(), **contexto}
    )
    pdf = HTML(string=html_string, base_url=request.build_absolute_uri('/')).write_pdf()

    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{nombre_archivo}"'
    return response


# --- Imprimir: reportes individuales, con los filtros del buscador ---

def escuela_imprimir(request):
    _, escuelas = _escuelas_filtradas(request)
    return _respuesta_pdf(
        request, 'partials/escuela/_escuela_reporte_pdf.html',
        {'escuelas': escuelas}, 'Escuelas.pdf'
    )


def escuela_imprimir_encargados(request):
    _, escuelas = _escuelas_filtradas(request)
    # ?anteriores=1 agrega los encargados inactivos (debajo del activo de cada escuela)
    con_anteriores = request.GET.get('anteriores') == '1'

    encargados = Encargado.objects.filter(
        escuela__in=escuelas
    ).select_related('escuela', 'escuela__distrito').prefetch_related(
        'telefonos'
    ).order_by('escuela__codigo', '-estado', 'apellido')
    if not con_anteriores:
        encargados = encargados.filter(estado=True)

    return _respuesta_pdf(
        request, 'partials/encargado/_encargado_reporte_pdf.html',
        {'encargados': encargados},
        'Encargados_con_anteriores.pdf' if con_anteriores else 'Encargados.pdf'
    )


def escuela_imprimir_cde(request):
    _, escuelas = _escuelas_filtradas(request)
    cdes = CDE.objects.filter(
        escuela__in=escuelas
    ).select_related('escuela', 'escuela__distrito').order_by('escuela__codigo', '-FechaInicio')
    return _respuesta_pdf(
        request, 'partials/cde/reporte_pdf.html',
        {'cdes': cdes}, 'CDE.pdf'
    )


# --- Imprimir: reporte general (escuela + encargado + CDE en una sola hoja) ---

def escuela_imprimir_general(request):
    _, escuelas = _escuelas_filtradas(request)
    return _respuesta_pdf(
        request, 'partials/escuela/_escuela_reporte_general_pdf.html',
        {'escuelas': _con_encargado_y_cde(escuelas)}, 'Reporte_general_escuelas.pdf'
    )


# --- Imprimir: ficha de una sola escuela ---

def escuela_imprimir_ficha(request, pk):
    escuela = get_object_or_404(Escuela.objects.select_related('distrito'), pk=pk)
    encargados = list(
        escuela.encargado_set.prefetch_related('telefonos').order_by('-estado', '-pk')
    )
    return _respuesta_pdf(
        request, 'partials/escuela/_escuela_ficha_pdf.html',
        {
            'escuela': escuela,
            'encargado_activo': next((e for e in encargados if e.estado), None),
            'encargados_anteriores': [e for e in encargados if not e.estado],
            'cdes': escuela.cde_set.order_by('-FechaInicio'),
        },
        f'Ficha_{escuela.codigo}.pdf'
    )


def home_escuelas(request):
    breadcrumbs = [
        {'name': 'Inicio', 'url': reverse('home')},
        {'name': 'Escuelas'},
    ]

    filtro_form, escuelas = _filtrar_escuelas(request)

    return render(
        request, 'escuela/escuelaHome.html',
        {
            'breadcrumbs': breadcrumbs,
            'escuelas': escuelas,
            'filtro_form': filtro_form,
            'form_media': filtro_form.media,
        }
    )


def buscar_escuelas(request):
    _, escuelas = _filtrar_escuelas(request)

    return render(
        request,
        'partials/escuela/_listado_escuelas.html',
        {'escuelas': escuelas}
    )


# Contenido que se despliega al abrir una escuela en el listado
def escuela_detalle(request, pk):
    escuela = get_object_or_404(Escuela, pk=pk)
    encargados = list(
        escuela.encargado_set.prefetch_related('telefonos').order_by('-estado', '-pk')
    )

    return render(
        request,
        'partials/escuela/_detalle.html',
        {
            'escuela': escuela,
            'encargado_activo': next((e for e in encargados if e.estado), None),
            'total_anteriores': sum(1 for e in encargados if not e.estado),
            'cdes': escuela.cde_set.order_by('-FechaInicio'),
        }
    )


# Página completa de una escuela: datos, encargado (y anteriores) y CDE
def escuela_gestionar(request, pk):
    escuela = get_object_or_404(Escuela.objects.select_related('distrito'), pk=pk)
    encargados = list(
        escuela.encargado_set.prefetch_related('telefonos').order_by('-estado', '-pk')
    )

    breadcrumbs = [
        {'name': 'Inicio', 'url': reverse('home')},
        {'name': 'Escuelas', 'url': reverse('home_escuelas')},
        {'name': f"{escuela.codigo} · {escuela.nombre_corto}"},
    ]

    return render(
        request,
        'escuela/escuelaGestionar.html',
        {
            'breadcrumbs': breadcrumbs,
            'escuela': escuela,
            'encargado_activo': next((e for e in encargados if e.estado), None),
            'encargados_anteriores': [e for e in encargados if not e.estado],
            'cdes': escuela.cde_set.order_by('-FechaInicio'),
            # JS/CSS de select2 que usan los modales de escuela y encargado
            'form_media': forms.EscuelaForm().media,
        }
    )


#Sirve para crear y Editar
def escuela_form(request, pk=None):
    instance = get_object_or_404(Escuela, pk=pk) if pk else None
    if request.method == 'POST':
        form = forms.EscuelaForm(request.POST, instance=instance, prefix='escuela')
        if form.is_valid():
            escuela = form.save()
            # Escuela nueva: se abre su página para agregarle encargado y CDE
            if instance is None:
                return _recargar_gestion(escuela)
            escuela_gestion = _escuela_en_gestion(request)
            if escuela_gestion:
                return _recargar_gestion(escuela_gestion)
            _, escuelas = _filtrar_escuelas(request)
            return render(
                request,
                'partials/escuela/_escuela_form_success.html',
                {'escuelas': escuelas}
            )
    else:
        form = forms.EscuelaForm(instance=instance, prefix='escuela')

    return render(
        request,
        'partials/escuela/_escuela_form_modal.html',
        {'form': form, 'instance': instance}
    )


def escuela_toggle_estado(request, pk):
    escuela = get_object_or_404(Escuela, pk=pk)

    if request.method == 'POST':
        escuela.estado = not escuela.estado
        escuela.save()

        escuela_gestion = _escuela_en_gestion(request)
        if escuela_gestion:
            return _recargar_gestion(escuela_gestion)

        _, escuelas = _filtrar_escuelas(request)

        return render(
            request,
            'partials/escuela/_escuela_form_success.html',
            {'escuelas': escuelas}
        )

        #Modal de confirmación para cambiar el estado de una escuela
    return render(
        request,
        'partials/escuela/_escuela_toggle_confirm.html',
        {'escuela': escuela}
    )
