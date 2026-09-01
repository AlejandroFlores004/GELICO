from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter(name='moneda')
def moneda(value):
    """Formatea un número como monto en dólares: coma para miles, punto para decimales (ej. 1,234.56)."""
    if value in (None, ''):
        value = 0

    try:
        value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return value

    return f"{value:,.2f}"
