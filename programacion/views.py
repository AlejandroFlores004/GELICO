from django.contrib import messages
from django.shortcuts import redirect, render


def auxiliarHomeView(request):
    auxiliares = request.session.get("auxiliares", [])

    if request.method == "POST":
        nombre = request.POST.get("nombre", "").strip()
        apellido = request.POST.get("apellido", "").strip()
        email = request.POST.get("email", "").strip()
        telefono = request.POST.get("telefono", "").strip()
        institucion = request.POST.get("institucion", "").strip()

        if nombre and apellido and email and institucion:
            auxiliares.append(
                {
                    "nombre": nombre,
                    "apellido": apellido,
                    "email": email,
                    "telefono": telefono or "",
                    "institucion": institucion,
                }
            )
            request.session["auxiliares"] = auxiliares
            messages.success(request, "Auxiliar agregado para prueba.")
        else:
            messages.error(request, "Completa los campos obligatorios para guardar.")

        return redirect("auxliar")

    search = request.GET.get("q", "").strip()
    if search:
        filtered = [
            auxiliar
            for auxiliar in auxiliares
            if search.lower() in " ".join(
                [
                    auxiliar.get("nombre", ""),
                    auxiliar.get("apellido", ""),
                    auxiliar.get("email", ""),
                    auxiliar.get("institucion", ""),
                ]
            ).lower()
        ]
    else:
        filtered = auxiliares

    return render(
        request,
        "auxiliar/auxiliarHome.html",
        {"auxiliares": auxiliares, "auxiliares_filtrados": filtered, "search": search},
    )