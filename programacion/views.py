from django.shortcuts import get_object_or_404, render

from .forms import AuxiliarForm
from .models import Auxiliar


def auxiliarHomeView(request):
    search = request.GET.get("q", "").strip()
    auxiliares = Auxiliar.objects.all().order_by('apellido', 'nombre')
    if search:
        filtered = auxiliares.filter(nombre__icontains=search) | auxiliares.filter(apellido__icontains=search) | auxiliares.filter(email__icontains=search) | auxiliares.filter(institucion__icontains=search)
    else:
        filtered = auxiliares

    return render(
        request,
        "auxiliar/auxiliarHome.html",
        {
            "auxiliares": auxiliares,
            "auxiliares_filtrados": filtered,
            "search": search,
        },
    )


def auxiliar_form(request, pk=None):
    instance = get_object_or_404(Auxiliar, pk=pk) if pk else None

    if request.method == "POST":
        form = AuxiliarForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            auxiliares = Auxiliar.objects.all().order_by('apellido', 'nombre')
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