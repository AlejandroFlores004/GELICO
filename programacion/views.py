from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from weasyprint import HTML

from .forms import AuxiliarForm
from .models import Auxiliar


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