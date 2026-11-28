"""Montants monétaires : stockage en unités mineures entières, calculs en Decimal.

Règle : aucun ``float`` ne transporte de montant. Les API exposent des chaînes
décimales (« 480000.00 ») accompagnées de leur devise.
"""
from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

from horizon.core.errors import DomainError

EXPONENTS = {"EUR": 2, "USD": 2, "GBP": 2, "CHF": 2, "JPY": 0, "SEK": 2, "PLN": 2}


def exponent(currency: str) -> int:
    try:
        return EXPONENTS[currency]
    except KeyError as exc:
        raise DomainError("UNSUPPORTED_CURRENCY", f"Devise non prise en charge : {currency}", 422) from exc


def to_minor(amount: str | Decimal | int, currency: str) -> int:
    """Convertit un montant décimal en unités mineures, sans arrondi implicite."""
    exp = exponent(currency)
    try:
        d = Decimal(str(amount))
    except InvalidOperation as exc:
        raise DomainError("INVALID_AMOUNT", f"Montant invalide : {amount}", 422) from exc
    if not d.is_finite():
        raise DomainError("INVALID_AMOUNT", "Montant non fini", 422)
    scaled = d * (Decimal(10) ** exp)
    if scaled != scaled.to_integral_value():
        raise DomainError(
            "INVALID_AMOUNT_PRECISION",
            f"Le montant {amount} dépasse la précision de la devise {currency} ({exp} décimales)",
            422,
        )
    return int(scaled)


def from_minor(minor: int, currency: str) -> Decimal:
    exp = exponent(currency)
    return (Decimal(minor) / (Decimal(10) ** exp)).quantize(Decimal(1).scaleb(-exp))


def fmt(minor: int, currency: str) -> str:
    return str(from_minor(minor, currency))


def money(minor: int, currency: str) -> dict:
    return {"amount": fmt(minor, currency), "currency": currency, "minor_units": int(minor)}


def convert_minor(minor: int, from_ccy: str, to_ccy: str, rate: Decimal) -> int:
    """Convertit en appliquant ``rate`` (unités de to_ccy pour 1 from_ccy), arrondi bancaire."""
    value = from_minor(minor, from_ccy) * rate
    exp = exponent(to_ccy)
    q = value.quantize(Decimal(1).scaleb(-exp), rounding=ROUND_HALF_EVEN)
    return int(q * (Decimal(10) ** exp))
