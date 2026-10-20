from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from weasyprint import HTML


def respuesta_pdf(request, plantilla, contexto, nombre_archivo):
    """Renderiza una plantilla de reporte con WeasyPrint y la devuelve como PDF en línea.

    Todas las plantillas reciben la fecha de generación e impresión, además de su contexto.
    """
    html_string = render_to_string(
        plantilla,
        {'fecha_generacion': timezone.localdate(), 'fecha_impresion': timezone.localtime(), **contexto},
    )
    pdf = HTML(string=html_string, base_url=request.build_absolute_uri('/')).write_pdf()

    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{nombre_archivo}"'
    return response


def datos_filtro(filtro_form):
    """cleaned_data del formulario de filtros, o {} si no es válido (= sin filtros)."""
    return filtro_form.cleaned_data if filtro_form.is_valid() else {}
