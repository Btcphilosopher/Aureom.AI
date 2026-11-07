"""Packaging and waste arithmetic (pure functions, no I/O, no randomness).

For an installed (net, measured) quantity ``q`` of a material:

* ``cutting = q * cutting_loss_fraction``  (offcuts, laps, breakage in cutting)
* ``waste   = q * waste_fraction``         (site handling / damage / over-ordering)
* ``required = q + cutting + waste``  - the two loss fractions are **additive, not
  compounded** (``q * (1 + c + w)``, not ``q * (1 + c) * (1 + w)``), so each loss
  is reported against the same installed base and the two can be audited
  independently.
* ``purchase_required = required * purchase_per_installed`` (installed units ->
  purchase units, e.g. m2 of board -> boards)
* ``packs = ceil(purchase_required / pack_size - 1e-9)`` (the small tolerance stops
  floating-point noise such as 1000.0000000001 / 500 buying an extra pack)
* ``purchased = packs * pack_size`` and ``surplus = purchased - purchase_required``
  (both in purchase units).

Installed quantities stay in installed units (``m2``, ``m3``, ``nr`` ...) and
purchased quantities in purchase units (``sheet``, ``board``, ``tonne`` ...);
they are never mixed.

Quantity lines are rounded to packs *per line* (what ordering that element on its
own would need).  Orders are normally placed per material across the project, so
:func:`procurement_schedule` re-does the pack rounding on the aggregated required
quantity and reports the difference; costing / logistics may use either basis but
should state which.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Union

from ..core.models import AssemblyLibrary, BillOfQuantities, MaterialSpec, QuantityLine, QuantityStatus

__all__ = ["procure", "procurement_schedule", "PACK_TOLERANCE"]

#: Tolerance used when rounding up to whole packs.
PACK_TOLERANCE = 1e-9


def procure(installed: float, material: MaterialSpec) -> dict[str, Any]:
    """Losses, purchase quantity and packaging for ``installed`` units of ``material``.

    Returns a dict with keys ``installed``, ``installed_unit``, ``cutting_loss_fraction``,
    ``cutting_loss_qty``, ``waste_fraction``, ``waste_qty``, ``required`` (installed units),
    ``purchase_unit``, ``purchase_per_installed``, ``purchase_required``, ``pack_size``,
    ``packs`` (int), ``purchased`` and ``surplus`` (purchase units).

    Raises ``ValueError`` for negative or non-finite quantities.
    """
    q = float(installed)
    if not math.isfinite(q) or q < 0.0:
        raise ValueError(f"installed quantity must be a finite, non-negative number (got {installed!r})")
    c = material.cutting_loss_fraction
    w = material.waste_fraction
    cutting = q * c
    waste = q * w
    required = q + cutting + waste
    ppi = material.purchase_per_installed
    purchase_required = required * ppi
    pack = material.pack_size
    packs = 0 if purchase_required <= 0.0 else int(math.ceil(purchase_required / pack - PACK_TOLERANCE))
    packs = max(packs, 0)
    purchased = packs * pack
    surplus = max(0.0, purchased - purchase_required)
    return {
        "installed": q,
        "installed_unit": material.installed_unit,
        "cutting_loss_fraction": c,
        "cutting_loss_qty": cutting,
        "waste_fraction": w,
        "waste_qty": waste,
        "required": required,
        "purchase_unit": material.purchase_unit,
        "purchase_per_installed": ppi,
        "purchase_required": purchase_required,
        "pack_size": pack,
        "packs": packs,
        "purchased": purchased,
        "surplus": surplus,
    }


def procurement_schedule(boq_or_lines: Union[BillOfQuantities, Iterable[QuantityLine]],
                         library: AssemblyLibrary) -> list[dict[str, Any]]:
    """Order-level purchase quantities per material (pack rounding on the project total).

    Only priced material lines (``cost_key`` ``mat:...``) with a resolved required quantity are
    aggregated; allowance and rule lines are excluded.  Returns one dict per material (sorted by
    id) with ``material_id``, ``name``, ``installed_unit``, ``purchase_unit``, ``pack_size``,
    ``line_ids``, ``installed``, ``required``, ``purchase_required``, ``packs``, ``purchased``,
    ``surplus``, ``line_level_purchased`` (sum of per-line purchases) and ``rounding_saving``
    (line-level minus order-level purchase, purchase units).
    """
    lines = boq_or_lines.lines if isinstance(boq_or_lines, BillOfQuantities) else list(boq_or_lines)
    mats = {m.material_id: m for m in library.materials}
    agg: dict[str, dict[str, Any]] = {}
    for ln in lines:
        if (ln.status == QuantityStatus.UNRESOLVED or not ln.material_id or not ln.cost_key
                or not ln.cost_key.startswith("mat:") or ln.required_qty is None or ln.installed_qty is None):
            continue
        a = agg.setdefault(ln.material_id, {"line_ids": [], "installed": 0.0, "required": 0.0,
                                            "line_level_purchased": 0.0})
        a["line_ids"].append(ln.line_id)
        a["installed"] += ln.installed_qty
        a["required"] += ln.required_qty
        a["line_level_purchased"] += ln.purchased_qty or 0.0
    out: list[dict[str, Any]] = []
    for mid in sorted(agg):
        a = agg[mid]
        mat = mats.get(mid)
        if mat is None:
            continue
        preq = a["required"] * mat.purchase_per_installed
        packs = 0 if preq <= 0 else int(math.ceil(preq / mat.pack_size - PACK_TOLERANCE))
        purchased = packs * mat.pack_size
        out.append({
            "material_id": mid, "name": mat.name, "installed_unit": mat.installed_unit,
            "purchase_unit": mat.purchase_unit, "pack_size": mat.pack_size, "line_ids": a["line_ids"],
            "installed": a["installed"], "required": a["required"], "purchase_required": preq, "packs": packs,
            "purchased": purchased, "surplus": max(0.0, purchased - preq),
            "line_level_purchased": a["line_level_purchased"],
            "rounding_saving": a["line_level_purchased"] - purchased,
        })
    return out
