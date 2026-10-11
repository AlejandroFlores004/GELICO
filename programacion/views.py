from calendar import Calendar
from collections import defaultdict

from django.contrib import messages
from django.http import HttpResponse, HttpResponseNotAllowed, HttpResponseRedirect
from django.core.paginator import Paginator
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from weasyprint import HTML

from .forms import AuxiliarForm, AusenciaForm, ConvocatoriaForm, HorarioForm, ProgramacionEstadoForm, ProgramacionFiltroForm, ProgramacionForm
from .models import Auxiliar, Ausencia, Convocatoria, Horario, Programacion


def _programaciones_filtradas(request, paginar=True):
    filtro_form = ProgramacionFiltroForm(request.GET or None)
    programaciones = Programacion.objects.select_related(
        'convocatoria', 'auxiliar', 'escuela'
    ).order_by('-fecha_programada', '-hora_programada')

    if filtro_form.is_valid():
        search = filtro_form.cleaned_data.get('q', '').strip()
        convocatoria = filtro_form.cleaned_data.get('convocatoria')
        escuela = filtro_form.cleaned_data.get('escuela')
        auxiliar = filtro_form.cleaned_data.get('auxiliar')

        if convocatoria:
            programaciones = programaciones.filter(convocatoria=convocatoria)
        if escuela:
            programaciones = programaciones.filter(escuela=escuela)
        if auxiliar:
            programaciones = programaciones.filter(auxiliar=auxiliar)
        if search:
            programaciones = programaciones.filter(
                Q(convocatoria__nombre__icontains=search)
                | Q(auxiliar__nombre__icontains=search)
                | Q(auxiliar__apellido__icontains=search)
                | Q(escuela__nombre__icontains=search)
                | Q(escuela__nombre_corto__icontains=search)
                | Q(estado__icontains=search)
            )

    if paginar:
        paginator = Paginator(programaciones, 20)
        programaciones = paginator.get_page(request.GET.get('page'))
    return filtro_form, programaciones


def programacionHomeView(request):
    filtro_form, programaciones = _programaciones_filtradas(request)
    return render(request, 'programacion/programacionHome.html', {
        'programaciones': programaciones,
        'filtro_form': filtro_form,
        'form_media': ProgramacionForm().media + filtro_form.media,
    })


def calendario_programaciones(request):
    mes_parametro = request.GET.get('mes', '')
    mes_actual = parse_date(f'{mes_parametro}-01') if mes_parametro else None
    if mes_actual is None:
        mes_actual = timezone.localdate().replace(day=1)
    else:
        mes_actual = mes_actual.replace(day=1)

    if mes_actual.month == 1:
        mes_anterior = mes_actual.replace(year=mes_actual.year - 1, month=12)
    else:
        mes_anterior = mes_actual.replace(month=mes_actual.month - 1)
    if mes_actual.month == 12:
        mes_siguiente = mes_actual.replace(year=mes_actual.year + 1, month=1)
    else:
        mes_siguiente = mes_actual.replace(month=mes_actual.month + 1)

    programaciones = Programacion.objects.filter(
        fecha_programada__gte=mes_actual,
        fecha_programada__lt=mes_siguiente,
    ).select_related('convocatoria', 'auxiliar', 'escuela').order_by(
        'fecha_programada', 'hora_programada'
    )
    programaciones_por_fecha = defaultdict(list)
    for programacion in programaciones:
        programacion.estado_form = ProgramacionEstadoForm(instance=programacion)
        programaciones_por_fecha[programacion.fecha_programada].append(programacion)

    calendario = [
        [
            {
                'fecha': fecha,
                'en_mes': fecha.month == mes_actual.month,
                'programaciones': programaciones_por_fecha[fecha],
            }
            for fecha in semana
        ]
        for semana in Calendar(firstweekday=6).monthdatescalendar(
            mes_actual.year, mes_actual.month
        )
    ]
    nombres_meses = (
        'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
        'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
    )

    return render(request, 'programacion/calendarioHome.html', {
        'calendario': calendario,
        'mes_titulo': f'{nombres_meses[mes_actual.month - 1].capitalize()} {mes_actual.year}',
        'mes_anterior': mes_anterior.strftime('%Y-%m'),
        'mes_siguiente': mes_siguiente.strftime('%Y-%m'),
        'mes_actual': mes_actual.strftime('%Y-%m'),
        'total_programaciones': programaciones.count(),
    })


def programacion_estado(request, pk):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    programacion = get_object_or_404(Programacion, pk=pk)
    form = ProgramacionEstadoForm(request.POST, instance=programacion)
    if form.is_valid():
        form.save()
    else:
        messages.error(request, 'No se pudo actualizar el estado de la programación.')

    mes = parse_date(f'{request.POST.get("mes", "")}-01')
    url_calendario = reverse('home_calendario')
    if mes:
        url_calendario = f'{url_calendario}?mes={mes.strftime("%Y-%m")}'
    return HttpResponseRedirect(url_calendario)


def buscar_programaciones(request):
    _, programaciones = _programaciones_filtradas(request)
    return render(request, 'partials/programacion/tabla.html', {
        'programaciones': programaciones,
    })


def _auxiliar_horarios_contexto(auxiliar, mes_parametro=None, convocatoria=None):
    mes_actual = parse_date(f'{mes_parametro}-01') if mes_parametro else None
    if mes_actual is None:
        mes_actual = timezone.localdate().replace(day=1)
    else:
        mes_actual = mes_actual.replace(day=1)

    if mes_actual.month == 1:
        mes_anterior = mes_actual.replace(year=mes_actual.year - 1, month=12)
    else:
        mes_anterior = mes_actual.replace(month=mes_actual.month - 1)
    if mes_actual.month == 12:
        mes_siguiente = mes_actual.replace(year=mes_actual.year + 1, month=1)
    else:
        mes_siguiente = mes_actual.replace(month=mes_actual.month + 1)

    horarios = Horario.objects.filter(
        auxiliar=auxiliar,
        fecha__gte=mes_actual,
        fecha__lt=mes_siguiente,
    ).order_by('fecha', 'hora_inicio') if auxiliar else Horario.objects.none()
    horarios_por_fecha = defaultdict(list)
    for horario in horarios:
        horarios_por_fecha[horario.fecha].append(horario)

    calendario_horarios = [
        [
            {
                'fecha': fecha,
                'en_mes': fecha.month == mes_actual.month,
                'horarios': horarios_por_fecha[fecha],
                'en_periodo_convocatoria': bool(
                    convocatoria
                    and convocatoria.fecha_inicio <= fecha <= convocatoria.fecha_fin
                ),
                'inicio_convocatoria': bool(
                    convocatoria and fecha == convocatoria.fecha_inicio
                ),
                'fin_convocatoria': bool(
                    convocatoria and fecha == convocatoria.fecha_fin
                ),
            }
            for fecha in semana
        ]
        for semana in Calendar(firstweekday=6).monthdatescalendar(
            mes_actual.year, mes_actual.month
        )
    ]
    nombres_meses = (
        'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
        'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
    )
    return {
        'auxiliar': auxiliar,
        'convocatoria': convocatoria,
        'calendario_horarios': calendario_horarios,
        'mes_actual': mes_actual.strftime('%Y-%m'),
        'mes_anterior': mes_anterior.strftime('%Y-%m'),
        'mes_siguiente': mes_siguiente.strftime('%Y-%m'),
        'mes_titulo': f'{nombres_meses[mes_actual.month - 1].capitalize()} {mes_actual.year}',
    }


def programacion_auxiliar_horario(request):
    auxiliar_id = request.GET.get('auxiliar')
    convocatoria_id = request.GET.get('convocatoria')
    auxiliar = Auxiliar.objects.filter(pk=auxiliar_id).first() if auxiliar_id else None
    convocatoria = Convocatoria.objects.filter(pk=convocatoria_id).first() if convocatoria_id else None
    return render(request, 'partials/programacion/auxiliar_horarios.html', _auxiliar_horarios_contexto(
        auxiliar,
        request.GET.get('mes'),
        convocatoria,
    ))


def programacion_form(request, pk=None):
    instance = get_object_or_404(Programacion, pk=pk) if pk else None
    auxiliar_actual = instance.auxiliar if instance else None
    convocatoria_actual = instance.convocatoria if instance else None
    mes_horarios = instance.fecha_programada.strftime('%Y-%m') if instance else None
    if request.method == 'POST':
        form = ProgramacionForm(request.POST, instance=instance)
        auxiliar_id = request.POST.get('auxiliar')
        convocatoria_id = request.POST.get('convocatoria')
        mes_horarios = request.POST.get('mes') or mes_horarios
        if auxiliar_id:
            auxiliar_actual = Auxiliar.objects.filter(pk=auxiliar_id).first()
        if convocatoria_id:
            convocatoria_actual = Convocatoria.objects.filter(pk=convocatoria_id).first()
        if form.is_valid():
            form.save()
            _, programaciones = _programaciones_filtradas(request)
            return render(request, 'partials/programacion/modal_form_success.html', {
                'programaciones': programaciones,
            })
    else:
        form = ProgramacionForm(instance=instance)

    return render(request, 'partials/programacion/modal_form.html', {
        'form': form,
        'instance': instance,
        **_auxiliar_horarios_contexto(auxiliar_actual, mes_horarios, convocatoria_actual),
    })


def programacion_eliminar(request, pk):
    instance = get_object_or_404(Programacion, pk=pk)
    if request.method == 'POST':
        instance.delete()
        _, programaciones = _programaciones_filtradas(request)
        return render(request, 'partials/programacion/modal_form_success.html', {
            'programaciones': programaciones,
        })
    return render(request, 'partials/programacion/modal_delete.html', {
        'instance': instance,
    })


def programacion_imprimir(request):
    _, programaciones = _programaciones_filtradas(request, paginar=False)
    html_string = render_to_string('partials/programacion/reporte_pdf.html', {
        'programaciones': programaciones,
        'fecha_generacion': timezone.localdate(),
    })
    pdf = HTML(string=html_string, base_url=request.build_absolute_uri('/')).write_pdf()
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="programaciones.pdf"'
    return response


def _auxiliares_filtrados(request):
    search = request.GET.get("q", "").strip()
    auxiliares = Auxiliar.objects.prefetch_related(
        Prefetch(
            'horario_set',
            queryset=Horario.objects.order_by('-fecha', 'hora_inicio'),
            to_attr='horarios',
        ),
        Prefetch(
            'ausencia_set',
            queryset=Ausencia.objects.order_by('-fecha'),
            to_attr='ausencias',
        ),
    ).order_by('apellido', 'nombre')
    if search:
        auxiliares = auxiliares.filter(
            nombre__icontains=search
        ) | auxiliares.filter(
            apellido__icontains=search
        ) | auxiliares.filter(
            email__icontains=search
        ) | auxiliares.filter(
            institucion__icontains=search
        )

    return search, auxiliares


def _filtrar_auxiliares(request):
    search, auxiliares_list = _auxiliares_filtrados(request)

    paginator = Paginator(auxiliares_list, 20)
    auxiliares = paginator.get_page(request.GET.get("page"))

    return search, auxiliares


def auxiliarHomeView(request):
    search, auxiliares = _filtrar_auxiliares(request)

    return render(
        request,
        "auxiliar/auxiliarHome.html",
        {
            "auxiliares": auxiliares,
            "search": search,
            "form_media": HorarioForm().media + AusenciaForm().media,
        },
    )


def buscar_auxiliares(request):
    _, auxiliares = _filtrar_auxiliares(request)

    return render(
        request,
        "partials/tabla.html",
        {"auxiliares": auxiliares},
    )


def auxiliar_form(request, pk=None):
    instance = get_object_or_404(Auxiliar, pk=pk) if pk else None

    if request.method == "POST":
        form = AuxiliarForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            _, auxiliares = _filtrar_auxiliares(request)
            return render(
                request,
                "partials/auxiliar/modal_form_success.html",
                {"auxiliares": auxiliares},
            )
    else:
        form = AuxiliarForm(instance=instance)

    return render(
        request,
        "partials/auxiliar/modal_form.html",
        {"form": form, "instance": instance},
    )


def auxiliar_eliminar(request, pk):
    instance = get_object_or_404(Auxiliar, pk=pk)

    if request.method == "POST":
        instance.delete()
        _, auxiliares = _filtrar_auxiliares(request)
        return render(
            request,
            "partials/auxiliar/modal_form_success.html",
            {"auxiliares": auxiliares},
        )

    return render(
        request,
        "partials/auxiliar/modal_delete.html",
        {"instance": instance},
    )


def horario_form(request, pk=None):
    instance = get_object_or_404(Horario, pk=pk) if pk else None
    if request.method == "POST":
        form = HorarioForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            _, auxiliares = _filtrar_auxiliares(request)
            return render(
                request,
                "partials/horario/modal_form_success.html",
                {"auxiliares": auxiliares},
            )
    elif instance:
        form = HorarioForm(instance=instance)
    else:
        auxiliar_id = request.GET.get('auxiliar')
        form = HorarioForm(initial={'auxiliar': auxiliar_id})

    return render(
        request,
        "partials/horario/modal_form.html",
        {"form": form, "instance": instance},
    )


def horario_eliminar(request, pk):
    instance = get_object_or_404(Horario, pk=pk)
    if request.method == "POST":
        instance.delete()
        _, auxiliares = _filtrar_auxiliares(request)
        return render(
            request,
            "partials/horario/modal_form_success.html",
            {"auxiliares": auxiliares},
        )

    return render(
        request,
        "partials/horario/modal_delete.html",
        {"instance": instance},
    )


def auxiliar_imprimir(request):
    _, auxiliares = _auxiliares_filtrados(request)
    html_string = render_to_string(
        "partials/auxiliar/reporte_pdf.html",
        {"auxiliares": auxiliares},
    )
    pdf = HTML(
        string=html_string,
        base_url=request.build_absolute_uri("/"),
    ).write_pdf()

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="auxiliares.pdf"'
    return response


def _ausencias_filtradas(request, paginar=True):
    search = request.GET.get("q", "").strip()
    fecha = request.GET.get("fecha", "").strip()
    ausencias = Ausencia.objects.select_related('auxiliar').order_by('-fecha', 'auxiliar__apellido', 'auxiliar__nombre')
    if search:
        ausencias = ausencias.filter(
            auxiliar__nombre__icontains=search
        ) | ausencias.filter(
            auxiliar__apellido__icontains=search
        ) | ausencias.filter(
            motivo__icontains=search
        )
    if fecha_date := parse_date(fecha):
        ausencias = ausencias.filter(fecha=fecha_date)

    if paginar:
        paginator = Paginator(ausencias, 20)
        ausencias = paginator.get_page(request.GET.get('page'))
    return search, fecha, ausencias


def _auxiliares_con_ausencias(request):
    search = request.GET.get("q", "").strip()
    fecha = request.GET.get("fecha", "").strip()
    ausencias = Ausencia.objects.order_by('-fecha')

    auxiliares = Auxiliar.objects.prefetch_related(
        Prefetch('horario_set', queryset=Horario.objects.order_by('-fecha', 'hora_inicio'), to_attr='horarios'),
        Prefetch('ausencia_set', queryset=ausencias, to_attr='ausencias'),
    ).order_by('apellido', 'nombre')

    if search:
        auxiliares = auxiliares.filter(
            Q(nombre__icontains=search)
            | Q(apellido__icontains=search)
            | Q(ausencia__motivo__icontains=search)
        ).distinct()
    if fecha_date := parse_date(fecha):
        auxiliares = auxiliares.filter(ausencia__fecha=fecha_date).distinct()

    paginator = Paginator(auxiliares, 20)
    return paginator.get_page(request.GET.get('page'))


def ausenciaHomeView(request):
    search = request.GET.get("q", "").strip()
    fecha = request.GET.get("fecha", "").strip()
    auxiliares = _auxiliares_con_ausencias(request)
    return render(request, "ausencia/ausenciaHome.html", {
        "auxiliares": auxiliares,
        "search": search,
        "fecha": fecha,
        "form_media": AusenciaForm().media,
    })


def buscar_ausencias(request):
    auxiliares = _auxiliares_con_ausencias(request)
    return render(request, "partials/ausencia/tabla.html", {"auxiliares": auxiliares})


def ausencia_form(request, pk=None):
    instance = get_object_or_404(Ausencia, pk=pk) if pk else None
    origen_auxiliares = request.GET.get('origen') == 'auxiliares'
    auxiliar_seleccionado = instance.auxiliar if instance else None
    if request.method == "POST":
        if not auxiliar_seleccionado and request.POST.get('auxiliar'):
            auxiliar_seleccionado = Auxiliar.objects.filter(pk=request.POST.get('auxiliar')).first()
        form = AusenciaForm(request.POST, instance=instance, auxiliar=auxiliar_seleccionado)
        if form.is_valid():
            form.save()
            contexto = {'origen_auxiliares': origen_auxiliares}
            if origen_auxiliares:
                _, auxiliares = _filtrar_auxiliares(request)
                contexto['auxiliares'] = auxiliares
            else:
                contexto['auxiliares'] = _auxiliares_con_ausencias(request)
            return render(request, "partials/ausencia/modal_form_success.html", contexto)
    else:
        auxiliar_id = request.GET.get('auxiliar') if not instance else None
        if auxiliar_id:
            auxiliar_seleccionado = Auxiliar.objects.filter(pk=auxiliar_id).first()
        form = AusenciaForm(
            instance=instance,
            initial={'auxiliar': auxiliar_id},
            auxiliar=auxiliar_seleccionado,
        )
    return render(request, "partials/ausencia/modal_form.html", {
        "form": form,
        "instance": instance,
        "auxiliar_seleccionado": auxiliar_seleccionado,
    })


def ausencia_eliminar(request, pk):
    instance = get_object_or_404(Ausencia, pk=pk)
    if request.method == "POST":
        instance.delete()
        origen_auxiliares = request.GET.get('origen') == 'auxiliares'
        contexto = {'origen_auxiliares': origen_auxiliares}
        if origen_auxiliares:
            _, auxiliares = _filtrar_auxiliares(request)
            contexto['auxiliares'] = auxiliares
        else:
            contexto['auxiliares'] = _auxiliares_con_ausencias(request)
        return render(request, "partials/ausencia/modal_form_success.html", contexto)
    return render(request, "partials/ausencia/modal_delete.html", {"instance": instance})


def ausencia_imprimir(request):
    _, _, ausencias = _ausencias_filtradas(request, paginar=False)
    html_string = render_to_string("partials/ausencia/reporte_pdf.html", {"ausencias": ausencias})
    pdf = HTML(string=html_string, base_url=request.build_absolute_uri("/")).write_pdf()
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="ausencias.pdf"'
    return response


def _convocatorias_filtradas(request, paginar=True):
    search = request.GET.get("q", "").strip()
    fecha_inicio = request.GET.get("fecha_inicio", "").strip()
    fecha_fin = request.GET.get("fecha_fin", "").strip()
    convocatorias = Convocatoria.objects.all().order_by('fecha_inicio')
    if search:
        convocatorias = convocatorias.filter(
            nombre__icontains=search
        ) | convocatorias.filter(
            descripcion__icontains=search
        )
    if fecha_inicio_date := parse_date(fecha_inicio):
        convocatorias = convocatorias.filter(fecha_inicio__gte=fecha_inicio_date)
    if fecha_fin_date := parse_date(fecha_fin):
        convocatorias = convocatorias.filter(fecha_fin__lte=fecha_fin_date)

    if paginar:
        paginator = Paginator(convocatorias, 20)
        convocatorias = paginator.get_page(request.GET.get('page'))
    return search, fecha_inicio, fecha_fin, convocatorias

def convocatoriasHomeView(request):
    search, fecha_inicio, fecha_fin, convocatorias = _convocatorias_filtradas(request)

    return render(
        request,
        "convocatorias/convocatoriasHome.html",
        {
            "convocatorias": convocatorias,
            "search": search,
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
        },
    )


def buscar_convocatorias(request):
    _, _, _, convocatorias = _convocatorias_filtradas(request)
    return render(
        request,
        "partials/convocatorias/tabla.html",
        {"convocatorias": convocatorias},
    )


def convocatoria_form(request, pk=None):
    instance = get_object_or_404(Convocatoria, pk=pk) if pk else None

    if request.method == "POST":
        form = ConvocatoriaForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            _, _, _, convocatorias = _convocatorias_filtradas(request)
            return render(
                request,
                "partials/convocatorias/modal_form_success.html",
                {"convocatorias": convocatorias},
            )
    else:
        form = ConvocatoriaForm(instance=instance)

    return render(
        request,
        "partials/convocatorias/modal_form.html",
        {"form": form, "instance": instance},
    )


def convocatoria_eliminar(request, pk):
    instance = get_object_or_404(Convocatoria, pk=pk)

    if request.method == "POST":
        instance.delete()
        _, _, _, convocatorias = _convocatorias_filtradas(request)
        return render(
            request,
            "partials/convocatorias/modal_form_success.html",
            {"convocatorias": convocatorias},
        )

    return render(
        request,
        "partials/convocatorias/modal_delete.html",
        {"instance": instance},
    )


def convocatoria_imprimir(request):
    _, _, _, convocatorias = _convocatorias_filtradas(request, paginar=False)
    html_string = render_to_string(
        "partials/convocatorias/reporte_pdf.html",
        {"convocatorias": convocatorias},
    )
    pdf = HTML(
        string=html_string,
        base_url=request.build_absolute_uri("/"),
    ).write_pdf()

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="convocatorias.pdf"'
    return response