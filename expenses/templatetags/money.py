from decimal import Decimal, InvalidOperation

from django import template
from django.conf import settings
from django.utils.formats import number_format

register = template.Library()


@register.filter
def money(value, with_symbol=True):
    """Render a Decimal amount as currency. The symbol lives in settings.CURRENCY_SYMBOL."""
    if value is None:
        value = Decimal("0")
    try:
        amount = Decimal(value).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return value
    text = number_format(amount, decimal_pos=2, use_l10n=True, force_grouping=True)
    return f"{settings.CURRENCY_SYMBOL}{text}" if with_symbol else text


@register.filter
def plain(value):
    """The same number without the currency symbol — for tight columns."""
    return money(value, with_symbol=False)


@register.simple_tag
def currency_symbol():
    return settings.CURRENCY_SYMBOL


@register.simple_tag(takes_context=True)
def query_replace(context, **kwargs):
    """
    Rebuild the current querystring with some keys replaced.

    Keeps month/category/search intact while flipping a sort order, which is
    otherwise a mess of hand-built links in the template.
    """
    params = context["request"].GET.copy()
    for key, value in kwargs.items():
        if value in (None, ""):
            params.pop(key, None)
        else:
            params[key] = value
    encoded = params.urlencode()
    return f"?{encoded}" if encoded else ""
