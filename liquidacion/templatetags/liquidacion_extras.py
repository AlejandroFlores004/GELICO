from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def moneda(valor):
    """Formatea un monto como 3,181.34 (formato de los reportes del ministerio)."""
    try:
        return f"{Decimal(valor):,.2f}"
    except (InvalidOperation, TypeError, ValueError):
        return valor
