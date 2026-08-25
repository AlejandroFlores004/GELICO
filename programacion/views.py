from django.http import HttpResponse
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.utils.dateparse import parse_date
from weasyprint import HTML

from .forms import AuxiliarForm, ConvocatoriaForm
from .models import Auxiliar, Convocatoria


def _auxiliares_filtrados(request):
    search = request.GET.get("q", "").strip()
    auxiliares = Auxiliar.objects.all().order_by('apellido', 'nombre')
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


def auxiliarHomeView(request):
    search, auxiliares = _auxiliares_filtrados(request)

    return render(
        request,
        "auxiliar/auxiliarHome.html",
        {
            "auxiliares": auxiliares,
            "search": search,
        },
    )


def buscar_auxiliares(request):
    _, auxiliares = _auxiliares_filtrados(request)

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
            _, auxiliares = _auxiliares_filtrados(request)
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
        _, auxiliares = _auxiliares_filtrados(request)
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