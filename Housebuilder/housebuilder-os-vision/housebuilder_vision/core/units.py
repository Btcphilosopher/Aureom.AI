"""Unit handling.  Internally everything is SI metric (m, m2, m3, kg, hr).

Display may be metric or imperial; conversion is explicit and dimension-checked.
Count-like units (nr, sheet, pack, ...) are dimensionless and only convert to
themselves unless a product-specific conversion factor is supplied elsewhere.
"""

from __future__ import annotations

import re

#: unit -> (dimension, factor to SI base unit)
_UNITS: dict[str, tuple[str, float]] = {
    # length (base m)
    "m": ("length", 1.0), "mm": ("length", 1e-3), "cm": ("length", 1e-2), "km": ("length", 1e3),
    "in": ("length", 0.0254), "ft": ("length", 0.3048), "yd": ("length", 0.9144),
    # area (base m2)
    "m2": ("area", 1.0), "mm2": ("area", 1e-6), "cm2": ("area", 1e-4), "ha": ("area", 1e4),
    "ft2": ("area", 0.09290304), "yd2": ("area", 0.83612736), "in2": ("area", 0.00064516),
    "acre": ("area", 4046.8564224),
    # volume (base m3)
    "m3": ("volume", 1.0), "l": ("volume", 1e-3), "litre": ("volume", 1e-3),
    "ft3": ("volume", 0.028316846592), "yd3": ("volume", 0.764554857984),
    # mass (base kg)
    "kg": ("mass", 1.0), "g": ("mass", 1e-3), "t": ("mass", 1000.0), "tonne": ("mass", 1000.0),
    "lb": ("mass", 0.45359237),
    # time (base hr)
    "hr": ("time", 1.0), "min": ("time", 1.0 / 60.0), "s": ("time", 1.0 / 3600.0),
    "day": ("time", 24.0), "week": ("time", 168.0),
    # angle (base deg)
    "deg": ("angle", 1.0), "rad": ("angle", 57.29577951308232),
    # pixel (own dimension)
    "px": ("pixel", 1.0),
    # ratio
    "fraction": ("ratio", 1.0), "%": ("ratio", 0.01), "ratio": ("ratio", 1.0),
    # carbon
    "kgCO2e": ("carbon", 1.0), "tCO2e": ("carbon", 1000.0),
    # energy / power
    "W": ("power", 1.0), "kW": ("power", 1000.0),
    "kWh": ("energy", 1.0), "MWh": ("energy", 1000.0),
}

#: Dimensionless count units: each converts only to itself (factor 1).
COUNT_UNITS = {
    "nr", "item", "sheet", "pack", "bag", "roll", "pallet", "load", "sum", "storeys",
    "dwelling", "length", "board", "tile", "brick", "block", "unit", "point", "set",
}

_ALIASES = {
    "m²": "m2", "sqm": "m2", "sq m": "m2", "sq.m": "m2", "m^2": "m2",
    "m³": "m3", "cum": "m3", "cu m": "m3", "m^3": "m3",
    "ft²": "ft2", "sq ft": "ft2", "sqft": "ft2", "ft³": "ft3", "cu ft": "ft3",
    "lm": "m", "lin m": "m", "metre": "m", "meter": "m", "metres": "m", "meters": "m",
    "no": "nr", "no.": "nr", "each": "nr", "ea": "nr", "pcs": "nr", "pc": "nr", "number": "nr",
    "h": "hr", "hrs": "hr", "hour": "hr", "hours": "hr",
    "tonnes": "tonne", "kgs": "kg", "litres": "l", "liter": "l",
    "degrees": "deg", "°": "deg", "percent": "%",
    "m/px": "m/px",
}


class UnitError(ValueError):
    pass


def normalise_unit(unit: str) -> str:
    """Canonical spelling of a unit string (case-sensitive for W/kW etc.)."""
    if unit is None:
        raise UnitError("unit is None")
    u = unit.strip()
    if u in _UNITS or u in COUNT_UNITS:
        return u
    lu = u.lower()
    if lu in _ALIASES:
        return _ALIASES[lu]
    if u in _ALIASES:
        return _ALIASES[u]
    if lu in _UNITS:
        return lu
    if lu in COUNT_UNITS:
        return lu
    # plural count units: "sheets", "packs", "bags" ...
    if lu.endswith("s") and lu[:-1] in COUNT_UNITS:
        return lu[:-1]
    return u


def dimension(unit: str) -> str:
    u = normalise_unit(unit)
    if u in _UNITS:
        return _UNITS[u][0]
    if u in COUNT_UNITS:
        return f"count:{u}"
    raise UnitError(f"unknown unit '{unit}'")


def is_known_unit(unit: str) -> bool:
    try:
        dimension(unit)
        return True
    except UnitError:
        return False


def convert(value: float, from_unit: str, to_unit: str) -> float:
    """Convert ``value`` between compatible units; raise :class:`UnitError` otherwise."""
    fu, tu = normalise_unit(from_unit), normalise_unit(to_unit)
    if fu == tu:
        return float(value)
    if fu in COUNT_UNITS or tu in COUNT_UNITS:
        raise UnitError(f"cannot convert count unit '{from_unit}' to '{to_unit}' without a product factor")
    if fu not in _UNITS:
        raise UnitError(f"unknown unit '{from_unit}'")
    if tu not in _UNITS:
        raise UnitError(f"unknown unit '{to_unit}'")
    fd, ff = _UNITS[fu]
    td, tf = _UNITS[tu]
    if fd != td:
        raise UnitError(f"incompatible units '{from_unit}' ({fd}) and '{to_unit}' ({td})")
    return float(value) * ff / tf


def convert_rate(rate: float, rate_unit: str, target_unit: str) -> float:
    """Convert a price per ``rate_unit`` into a price per ``target_unit``.

    e.g. £50 per tonne -> £0.05 per kg: convert_rate(50, 't', 'kg') == 0.05
    """
    # price per unit scales inversely with the unit size
    return float(rate) / convert(1.0, rate_unit, target_unit)


_IMPERIAL_DISPLAY = {"length": "ft", "area": "ft2", "volume": "ft3", "mass": "lb"}


def to_display(value: float, unit: str, unit_system: str = "metric") -> tuple[float, str]:
    """Convert an SI value to the display unit system (metric is unchanged)."""
    if unit_system != "imperial":
        return value, unit
    try:
        dim = dimension(unit)
    except UnitError:
        return value, unit
    target = _IMPERIAL_DISPLAY.get(dim)
    if not target:
        return value, unit
    return convert(value, unit, target), target


def parse_quantity(text: str) -> tuple[float, str]:
    """Parse strings like '9.6 m', '31ft', '9600mm' into (value, unit)."""
    m = re.fullmatch(r"\s*([-+]?\d+(?:[.,]\d+)?)\s*([A-Za-z²³%°/\^ .0-9]*)\s*", text or "")
    if not m:
        raise UnitError(f"cannot parse quantity '{text}'")
    val = float(m.group(1).replace(",", "."))
    unit = normalise_unit(m.group(2) or "m")
    if not is_known_unit(unit):
        raise UnitError(f"unknown unit in '{text}'")
    return val, unit
