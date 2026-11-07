"""Number, currency and unit formatting for display (internal values stay SI metric).

Display conversion uses :func:`housebuilder_vision.core.units.to_display` (metric is unchanged;
imperial maps length -> ft, area -> ft2, volume -> ft3, mass -> lb).  Values typed into editors
in display units are converted back to SI with :func:`to_si` before they reach the engine.
Count-like units (nr, sheet, pack ...) never convert.
"""

from __future__ import annotations

import math
from typing import Optional

from ..core.provenance import Distribution, TrackedValue
from ..core.units import UnitError, convert, to_display

CURRENCY_SYMBOLS = {"GBP": "£", "EUR": "€", "USD": "$", "AUD": "A$", "CAD": "C$", "NZD": "NZ$", "IEP": "£"}
UNIT_LABELS = {"m2": "m²", "m3": "m³", "ft2": "ft²", "ft3": "ft³", "deg": "°", "fraction": "", "storeys": "",
               "week": "wk", "hr": "h"}


def is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))


def unit_label(unit: str) -> str:
    return UNIT_LABELS.get(unit, unit)


def num(v, nd: int = 2, *, dash: str = "–") -> str:
    if not is_num(v):
        return dash
    return f"{float(v):,.{nd}f}"


def money(v, currency: str = "GBP", *, nd: int = 0, dash: str = "–") -> str:
    if not is_num(v):
        return dash
    sym = CURRENCY_SYMBOLS.get(currency.upper())
    s = f"{abs(float(v)):,.{nd}f}"
    sign = "−" if float(v) < 0 else ""
    return f"{sign}{sym}{s}" if sym else f"{sign}{currency} {s}"


def money_short(v, currency: str = "GBP") -> str:
    if not is_num(v):
        return "–"
    a = abs(float(v))
    if a >= 1e6:
        return money(float(v) / 1e6, currency, nd=2) + "m"
    if a >= 1e4:
        return money(float(v) / 1e3, currency, nd=1) + "k"
    return money(v, currency)


def pct(v, nd: int = 1) -> str:
    return "–" if not is_num(v) else f"{100.0 * float(v):.{nd}f}%"


def disp(value, unit: str, system: str = "metric") -> tuple[Optional[float], str]:
    """SI value -> (display value, display unit)."""
    if not is_num(value):
        return None, unit
    try:
        v, u = to_display(float(value), unit, system)
    except UnitError:
        return float(value), unit
    return v, u


def to_si(value, display_unit: str, si_unit: str) -> float:
    """Display value back to SI (no-op when the units match)."""
    if display_unit == si_unit:
        return float(value)
    return convert(float(value), display_unit, si_unit)


def disp_unit(unit: str, system: str = "metric") -> str:
    return disp(1.0, unit, system)[1]


def qty(value, unit: str, system: str = "metric", nd: int = 2) -> str:
    v, u = disp(value, unit, system)
    if v is None:
        return "–"
    lab = unit_label(u)
    return f"{v:,.{nd}f} {lab}".strip()


def tv_value(tv: Optional[TrackedValue], system: str = "metric", nd: int = 2) -> str:
    if tv is None or tv.value is None:
        return "unknown"
    if tv.unit == "fraction":
        return pct(tv.value, 0)
    return qty(tv.value, tv.unit, system, nd)


def tv_range(tv: Optional[TrackedValue], system: str = "metric", nd: int = 2) -> str:
    """``"low–high unit (triangular)"`` or ``"fixed"`` / ``"unknown"``."""
    if tv is None or tv.value is None:
        return "unknown - no evidence"
    if not tv.is_uncertain:
        return "fixed (no range)"
    lo, _ = disp(tv.low, tv.unit, system)
    hi, u = disp(tv.high, tv.unit, system)
    if tv.unit == "fraction":
        return f"{pct(tv.low, 0)}–{pct(tv.high, 0)}"
    dist = tv.distribution.value if isinstance(tv.distribution, Distribution) else str(tv.distribution)
    return f"{lo:,.{nd}f}–{hi:,.{nd}f} {unit_label(u)} · {dist}"


__all__ = ["CURRENCY_SYMBOLS", "disp", "disp_unit", "is_num", "money", "money_short", "num", "pct", "qty",
           "to_si", "tv_range", "tv_value", "unit_label"]
