"""Construction cost engine: bill of quantities x rate book -> layered, bounded estimate.

``estimate_construction_cost(boq, rate_book, params, *, settings, ...)`` prices a
:class:`~housebuilder_vision.core.models.BillOfQuantities` in nine explicit layers
(:class:`~housebuilder_vision.core.models.CostLayer`).  Every cost line keeps its
quantity, unit, net rate, rate id, formula, provenance basis and the rate's
uncertainty fractions; lines priced from a quantity line keep its
``quantity_line_id``.

Layers
------
1. **Materials** - every resolved quantity line with a ``mat:`` key is priced on its
   ``purchased_qty`` (pack-rounded *per line*, in the material's purchase unit);
   ``allow:`` lines (labelled allowances) are priced on their quantity by the
   ``allow:`` rate, which covers the material / supply component (labour on the line
   is priced in layer 2).
2. **Labour** - per quantity line, ``labour_hours x lab:<trade>`` (per hour).
3. **Plant** - quantity lines with a ``plant:`` key (``plant:excavation`` per m3 bank:
   excavator incl. fuel; when no per-m3 rate resolves but ``plant:excavator`` per hour
   does, hours = m3 x :attr:`CostRules.excavator_hours_per_m3`), plus derived hires
   (:class:`CostRules`): dumper weeks = ceil(groundworks labour hours /
   ``dumper_gang_hours_per_week``); scaffold m2-weeks = external wall gross area x
   ``scaffold_area_factor`` x ``scaffold_programme_share`` x programme weeks;
   telehandler weeks = ceil(``telehandler_programme_share`` x programme weeks).
4. **Logistics & waste** - ``log:`` quantity lines (spoil disposal per m3 loose);
   delivery loads x ``log:delivery_load`` (site receipt per load) where loads =
   ``logistics.total_loads`` when a logistics plan is given, else one order per
   material (``max(1, ceil(max(mass / payload_kg, volume / payload_m3)))``) plus one per
   allowance item; supplier delivery charges for rates that charge delivery separately
   (``delivery_charge`` once per material order); waste skips =
   ``ceil(waste volume x bulking / skip volume)`` x ``log:skip``, waste volume from the
   lines' cutting + waste quantities via the material's volume (or mass / density) per
   purchase unit.  ``log:`` rates fall back to ``CostParameters`` values (labelled).
5. **Preliminaries** - setup + weekly x programme weeks (``prelim:setup`` /
   ``prelim:weekly`` rates if present, else ``CostParameters``).
6. **Fees** - ``FeeItem.fraction x base`` (``direct`` = layers 1-4, ``construction`` = 1-5).
7. **Contingency** - ``contingency_fraction x (L1..L6)``.
8. **Overhead & margin** - overhead = ``o x (L1..L7)``; margin = ``m x (L1..L7 + overhead)``.
9. **Land, finance, taxes, sales** - only items the user entered: land; finance =
   ``rate x months / 12 x (land + drawdown x contract sum)`` (land is assumed drawn at the
   start; the build cost is assumed drawn evenly, so on average
   :attr:`CostRules.finance_drawdown_fraction` = 0.5 of the contract sum is outstanding);
   entered taxes; VAT only when ``settings.include_vat`` (``vat_rate x contract sum``, "as
   entered - check applicable treatment"); sales costs = ``fraction x sales_value``.

Boundaries (cumulative): ``materials`` (L1), ``direct_works`` (L1-4),
``construction_before_contingency`` (L1-6), ``construction_incl_contingency`` (L1-7),
``contract_sum`` (L1-8), ``total_development_cost`` (L1-9, only when a layer-9 item was
entered).  ``sales_value`` is reported separately and is never inside a boundary.

Unresolved quantity lines and missing rates are listed in ``unresolved_items`` with the
affected line ids - never priced as zero.

Boundaries of the method: concept-stage estimate from a conceptual reconstruction and
labelled assumptions.  Not a tender price, valuation or cost plan for contract; the
bundled demo rates are fictional.  VAT and tax treatment is never determined here.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

from ..core.models import (
    COST_LAYER_NAMES,
    AssemblyLibrary,
    BillOfQuantities,
    CostBoundary,
    CostEstimate,
    CostLayer,
    CostLine,
    CostParameters,
    DeliveryTreatment,
    LogisticsResult,
    MaterialSpec,
    QuantityLine,
    QuantityStatus,
    RateBook,
)
from ..core.provenance import Basis, weakest_basis
from ..core.settings import ProjectSettings
from .rates import RateIndex, ResolvedRate, cost_key_layer, rate_index, resolve_rate_detailed

__all__ = [
    "CostRules",
    "DEFAULT_COST_RULES",
    "BOUNDARY_KEYS",
    "COST_CONVENTIONS",
    "RULE_COST_KEYS",
    "estimate_construction_cost",
    "cost_lines_table",
    "boundary_table",
]

_LAYERS = list(CostLayer)
L1, L2, L3, L4, L5, L6, L7, L8, L9 = _LAYERS

#: Cost keys priced by derived rules (not emitted by the take-off) and their units.
RULE_COST_KEYS: dict[str, str] = {
    "plant:excavator": "hr",
    "plant:dumper": "week",
    "plant:scaffold": "m2_week",
    "plant:telehandler": "week",
    "log:delivery_load": "load",
    "log:skip": "nr",
    "prelim:setup": "sum",
    "prelim:weekly": "week",
}

BOUNDARY_KEYS = ("materials", "direct_works", "construction_before_contingency", "construction_incl_contingency",
                 "contract_sum", "total_development_cost")


@dataclass(frozen=True)
class CostRules:
    """Labelled rule assumptions used by the engine (all editable; none is a measured fact)."""

    #: Fallback only: excavator hours per m3 bank when pricing ``plant:excavator`` per hour.
    excavator_hours_per_m3: float = 0.10
    #: Groundworks labour hours served by one dumper-week (2 operatives x 37.5 h).
    dumper_gang_hours_per_week: float = 75.0
    #: Scaffold face area per m2 of external wall gross area (corners, lift above plate).
    scaffold_area_factor: float = 1.15
    #: Share of the programme the scaffold stays on hire.
    scaffold_programme_share: float = 0.40
    #: Share of the programme a telehandler is on hire (superstructure / roof loading-out).
    telehandler_programme_share: float = 0.35
    #: Rigid delivery vehicle payload used to estimate loads per material order.
    lorry_payload_kg: float = 10_000.0
    lorry_payload_m3: float = 20.0
    #: Average share of the contract sum outstanding over the finance period (even drawdown).
    finance_drawdown_fraction: float = 0.5


DEFAULT_COST_RULES = CostRules()

COST_CONVENTIONS: dict[str, str] = {
    "net_of_vat": "All rates are converted to net of VAT; VAT is only added in layer 9 when settings.include_vat.",
    "materials_quantity": "Layer 1 uses each BoQ line's purchased_qty (pack-rounded per line, purchase unit).",
    "allowances": "allow: rates price the supply / material component; installation labour is layer 2.",
    "labour": "Labour = labour_hours on each BoQ line x lab:<trade> hourly rate.",
    "plant": "plant:excavation per m3 bank (excavator incl. fuel); derived hires: dumper weeks = ceil(groundworks "
             "hours / 75), scaffold m2-weeks = external wall gross x 1.15 x 0.40 x programme weeks, telehandler weeks "
             "= ceil(0.35 x programme weeks) (CostRules defaults).",
    "logistics": "Loads from the logistics plan if given, else one order per material (payload 10 t / 20 m3) plus one "
                 "per allowance item; supplier delivery charges once per material order; skips = ceil(waste volume x "
                 "bulking / skip volume); all cutting and waste losses assumed to leave site in skips.",
    "prelims": "Preliminaries = setup + weekly x programme weeks.",
    "fees": "Fees = fraction x layers 1-4 ('direct') or layers 1-5 ('construction').",
    "contingency": "Contingency = fraction x layers 1-6.",
    "overhead_margin": "Overhead = o x layers 1-7; margin = m x (layers 1-7 + overhead).",
    "finance": "Finance = annual rate x months / 12 x (land + 0.5 x contract sum): land drawn at start, build cost "
               "drawn evenly (assumption).",
    "vat": "VAT line only when include_vat: rate x contract sum, as entered - check applicable treatment.",
    "sales_value": "Sales value (GDV) is reported separately and never included in a cost boundary.",
    "unresolved": "Unresolved quantities and missing rates are listed, never priced as zero.",
    "information_level": "Concept-stage estimate; not a tender price or valuation. Demo rates are FICTIONAL.",
}

_BOUNDARY_DEFS: list[tuple[str, str, list[CostLayer], str, str]] = [
    ("materials", "Materials", [L1],
     "Layer 1: purchased materials (per-line pack-rounded purchase quantities) and allowance supply components, "
     "net of VAT.",
     "Labour, plant, logistics, preliminaries, fees, contingency, overhead & margin, land, finance, taxes, sales "
     "costs and VAT."),
    ("direct_works", "Direct works", [L1, L2, L3, L4],
     "Layers 1-4: materials, direct installation labour, plant and logistics & waste.",
     "Preliminaries, fees, contingency, overhead & margin, land, finance, taxes, sales costs and VAT."),
    ("construction_before_contingency", "Construction cost before contingency", [L1, L2, L3, L4, L5, L6],
     "Layers 1-6: direct works plus site preliminaries and professional fees / allowances.",
     "Contingency, overhead & margin, land, finance, taxes, sales costs and VAT."),
    ("construction_incl_contingency", "Construction cost incl. contingency", [L1, L2, L3, L4, L5, L6, L7],
     "Layers 1-7: construction cost before contingency plus the risk contingency.",
     "Contractor overhead & margin, land, finance, taxes, sales costs and VAT."),
    ("contract_sum", "Indicative contract sum", [L1, L2, L3, L4, L5, L6, L7, L8],
     "Layers 1-8: construction cost incl. contingency plus contractor overhead and margin (ex VAT). Indicative, "
     "not a tender price.",
     "Land, finance, taxes, sales costs and VAT."),
    ("total_development_cost", "Total development cost", _LAYERS,
     "Layers 1-9: contract sum plus the land, finance, taxes, VAT (if included) and sales costs that were entered.",
     "Sales value (GDV) - reported separately, never a cost. Items not entered are not included."),
]


@lru_cache(maxsize=1)
def _default_library() -> AssemblyLibrary:
    from ..quantities.library import default_library

    return default_library()


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()[:40] or "item"


# =============================================================================
# Internal state
# =============================================================================
class _Resolver:
    """Per-estimate cache of rate resolutions (one lookup per (cost_key, unit))."""

    def __init__(self, idx: RateIndex, settings: ProjectSettings) -> None:
        self.idx = idx
        self.settings = settings
        self.cache: dict[tuple[str, str], ResolvedRate] = {}

    def get(self, cost_key: str, unit: str) -> ResolvedRate:
        k = (cost_key, unit)
        rr = self.cache.get(k)
        if rr is None:
            rr = self.cache[k] = resolve_rate_detailed(self.idx, cost_key, unit, settings=self.settings)
        return rr


@dataclass
class _State:
    currency: str
    lines: list[CostLine] = field(default_factory=list)
    totals: dict[CostLayer, float] = field(default_factory=lambda: {layer: 0.0 for layer in CostLayer})
    unresolved: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    #: (cost_key, unit) -> quantity line ids that could not be priced for lack of a rate
    missing: dict[tuple[str, str], list[str]] = field(default_factory=dict)
    used: dict[tuple[str, str], ResolvedRate] = field(default_factory=dict)

    def add(self, *, line_id: str, layer: CostLayer, description: str, amount: float, cost_key: Optional[str] = None,
            quantity: Optional[float] = None, unit: str = "", rr: Optional[ResolvedRate] = None,
            rate_value: Optional[float] = None, quantity_line_id: Optional[str] = None,
            basis: Basis = Basis.ASSUMED, formula: str = "", notes: str = "") -> None:
        rate = rr.rate if rr is not None else None
        if rr is not None and rate is not None:
            self.used[(rr.cost_key, rr.unit)] = rr
        self.lines.append(CostLine.model_construct(
            line_id=line_id, layer=layer, description=description, cost_key=cost_key, quantity=quantity, unit=unit,
            rate_value=rate_value if rate_value is not None else (rr.value if rate is not None else None),
            rate_id=rate.rate_id if rate is not None else None, currency=self.currency, amount=float(amount),
            quantity_line_id=quantity_line_id, basis=basis, formula=formula,
            uncertainty_low=rate.uncertainty_low if rate is not None else 0.0,
            uncertainty_high=rate.uncertainty_high if rate is not None else 0.0, notes=notes))
        self.totals[layer] += float(amount)

    def miss(self, cost_key: str, unit: str, ref: str) -> None:
        self.missing.setdefault((cost_key, unit), []).append(ref)


def _rate_formula(qty: float, unit: str, rr: ResolvedRate, cur: str, amount: float) -> str:
    assert rr.rate is not None
    adj = f"; {', '.join(rr.adjustments)}" if rr.adjustments else ""
    return (f"{qty:.3f} {unit} × {cur} {rr.value:.4f}/{unit} = {cur} {amount:.2f} "
            f"[rate {rr.rate.rate_id}: {rr.rate.value:g} {rr.rate.currency}/{rr.rate.unit}{adj}]")


def _priced(st: _State, *, line_id: str, layer: CostLayer, description: str, cost_key: str, qty: float, unit: str,
            rr: ResolvedRate, basis: Basis, quantity_line_id: Optional[str] = None, notes: str = "") -> float:
    amount = qty * rr.value
    st.add(line_id=line_id, layer=layer, description=description, amount=amount, cost_key=cost_key, quantity=qty,
           unit=unit, rr=rr, quantity_line_id=quantity_line_id, basis=weakest_basis(basis, rr.basis),
           formula=_rate_formula(qty, unit, rr, st.currency, amount), notes=notes)
    return amount


def _line_quantity(ln: QuantityLine) -> Optional[float]:
    for q in (ln.purchased_qty, ln.required_qty, ln.installed_qty):
        if q is not None:
            return float(q)
    return None


# =============================================================================
# Layers 1-3 from quantity lines
# =============================================================================
def _price_quantity_lines(st: _State, boq: BillOfQuantities, res: _Resolver, rules: CostRules) -> dict[str, float]:
    """Layers 1-4 lines that come straight from BoQ lines; returns aggregates for the rules."""
    agg = {"groundworks_hours": 0.0, "excavation_m3": 0.0}
    for ln in boq.lines:
        if ln.status == QuantityStatus.UNRESOLVED:
            reason = (ln.notes or ln.formula or "no reason given").removeprefix("UNRESOLVED: ")
            st.unresolved.append(f"{ln.line_id} ({ln.description}): quantity unresolved - {reason}; not priced")
            continue
        ck = ln.cost_key
        if ck:
            qty = _line_quantity(ln)
            unit = ln.purchase_unit or ln.unit
            if qty is None:
                st.unresolved.append(f"{ln.line_id} ({ln.description}): no quantity on a {ln.status.value} line; "
                                     "not priced")
            elif qty > 0:
                layer = cost_key_layer(ck)
                rr = res.get(ck, unit)
                note = "Labelled allowance (not measured)." if ln.status == QuantityStatus.ALLOWANCE else ""
                if rr.found:
                    layer = layer or rr.rate.layer
                    if layer == L1 and rr.rate.delivery_treatment not in (DeliveryTreatment.DELIVERED_INCLUDED,
                                                                         DeliveryTreatment.NOT_APPLICABLE):
                        note = (note + " " if note else "") + \
                            f"Delivery: {rr.rate.delivery_treatment.value.replace('_', ' ')} (see layer 4)."
                    _priced(st, line_id=f"{layer.value[0]}:{ln.line_id}", layer=layer, description=ln.description,
                            cost_key=ck, qty=qty, unit=unit, rr=rr, basis=ln.basis, quantity_line_id=ln.line_id,
                            notes=note)
                    if ck == "plant:excavation":
                        agg["excavation_m3"] += qty
                elif ck == "plant:excavation" and res.get("plant:excavator", "hr").found:
                    rx = res.get("plant:excavator", "hr")
                    hours = qty * rules.excavator_hours_per_m3
                    amount = hours * rx.value
                    st.add(line_id=f"3:{ln.line_id}", layer=L3, description=f"{ln.description} (excavator hours)",
                           amount=amount, cost_key="plant:excavator", quantity=hours, unit="hr", rr=rx,
                           quantity_line_id=ln.line_id, basis=weakest_basis(ln.basis, rx.basis, Basis.ASSUMED),
                           formula=f"{qty:.3f} m3 bank × {rules.excavator_hours_per_m3:g} hr/m3 = {hours:.3f} hr; "
                                   + _rate_formula(hours, "hr", rx, st.currency, amount),
                           notes="No per-m3 excavation rate: priced as excavator hours (CostRules assumption).")
                    agg["excavation_m3"] += qty
                else:
                    st.miss(ck, unit, ln.line_id)
        hours = ln.labour_hours
        if hours is not None and hours > 0:
            lk = f"lab:{ln.trade}"
            rr = res.get(lk, "hr")
            if rr.found:
                _priced(st, line_id=f"2:{ln.line_id}", layer=L2, description=f"Labour ({ln.trade}) - {ln.description}",
                        cost_key=lk, qty=float(hours), unit="hr", rr=rr, basis=ln.basis, quantity_line_id=ln.line_id)
            else:
                st.miss(lk, "hr", ln.line_id)
            if ln.trade == "groundworks":
                agg["groundworks_hours"] += float(hours)
    return agg


# =============================================================================
# Layer 3 derived plant
# =============================================================================
def _derived_plant(st: _State, boq: BillOfQuantities, res: _Resolver, rules: CostRules, weeks: float,
                   weeks_basis: Basis, agg: dict[str, float]) -> None:
    gw = agg["groundworks_hours"]
    items: list[tuple[str, str, str, float, str]] = []
    if gw > 0:
        dw = math.ceil(gw / rules.dumper_gang_hours_per_week - 1e-9)
        items.append(("dumper", "plant:dumper", "week", float(dw),
                      f"ceil({gw:.2f} groundworks hr / {rules.dumper_gang_hours_per_week:g} hr per dumper-week) "
                      f"= {dw} week"))
    ext = boq.geometry.external_wall_gross_m2
    if ext > 0 and weeks > 0:
        sw = rules.scaffold_programme_share * weeks
        m2wk = ext * rules.scaffold_area_factor * sw
        items.append(("scaffold", "plant:scaffold", "m2_week", m2wk,
                      f"{ext:.3f} m2 external wall gross × {rules.scaffold_area_factor:g} face factor × "
                      f"({rules.scaffold_programme_share:g} × {weeks:g} wk) = {m2wk:.3f} m2-week"))
    if weeks > 0:
        tw = math.ceil(rules.telehandler_programme_share * weeks - 1e-9)
        items.append(("telehandler", "plant:telehandler", "week", float(tw),
                      f"ceil({rules.telehandler_programme_share:g} × {weeks:g} programme weeks) = {tw} week"))
    for name, ck, unit, qty, rule_txt in items:
        if qty <= 0:
            continue
        rr = res.get(ck, unit)
        if not rr.found:
            st.miss(ck, unit, f"plant rule '{name}' ({qty:.2f} {unit})")
            continue
        amount = qty * rr.value
        st.add(line_id=f"3:plant.{name}", layer=L3, description=f"{name.capitalize()} hire (derived plant rule)",
               amount=amount, cost_key=ck, quantity=qty, unit=unit, rr=rr,
               basis=weakest_basis(Basis.ASSUMED, weeks_basis if name != "dumper" else Basis.ASSUMED, rr.basis),
               formula=rule_txt + "; " + _rate_formula(qty, unit, rr, st.currency, amount),
               notes="Derived from BoQ / programme by a labelled CostRules assumption.")


# =============================================================================
# Layer 4 logistics & waste
# =============================================================================
def _material_waste_volume(ln: QuantityLine, mat: MaterialSpec) -> Optional[float]:
    w = (ln.cutting_loss_qty or 0.0) + (ln.waste_qty or 0.0)
    if w <= 0:
        return 0.0
    if mat.installed_unit == "m3":
        return w
    pu = w * (ln.purchase_per_installed or mat.purchase_per_installed)
    if mat.volume_per_purchase_unit_m3:
        return pu * mat.volume_per_purchase_unit_m3
    if mat.mass_per_purchase_unit_kg and mat.density_kg_m3:
        return pu * mat.mass_per_purchase_unit_kg / mat.density_kg_m3
    return None


def _log_rate(st: _State, res: _Resolver, ck: str, unit: str, fallback: float, fallback_name: str
              ) -> tuple[Optional[ResolvedRate], float, str]:
    rr = res.get(ck, unit)
    if rr.found:
        return rr, rr.value, f"rate {rr.rate.rate_id}"
    return None, float(fallback), f"CostParameters.{fallback_name} (no '{ck}' rate; assumption)"


def _logistics(st: _State, boq: BillOfQuantities, res: _Resolver, params: CostParameters, rules: CostRules,
               logistics: Optional[LogisticsResult], mats: dict[str, MaterialSpec]) -> None:
    cur = st.currency
    priced_mat_lines = [ln for ln in boq.lines
                        if ln.status != QuantityStatus.UNRESOLVED and ln.cost_key and ln.cost_key.startswith("mat:")
                        and (_line_quantity(ln) or 0.0) > 0]
    # ---- delivery loads
    if logistics is not None:
        loads = int(logistics.total_loads)
        loads_txt = f"{loads} loads from the logistics plan"
        loads_basis = Basis.ASSUMED
    else:
        per_mat: dict[str, list[float]] = {}
        for ln in priced_mat_lines:
            mid = ln.material_id or ln.cost_key.split(":", 1)[1]
            acc = per_mat.setdefault(mid, [0.0, 0.0])
            mat = mats.get(mid)
            q = _line_quantity(ln) or 0.0
            if mat is not None:
                acc[0] += q * (mat.mass_per_purchase_unit_kg or 0.0)
                acc[1] += q * (mat.volume_per_purchase_unit_m3 or 0.0)
        mat_loads = 0
        for mass, vol in per_mat.values():
            mat_loads += max(1, math.ceil(max(mass / rules.lorry_payload_kg, vol / rules.lorry_payload_m3) - 1e-9))
        allow_orders = len({ln.cost_key for ln in boq.lines if ln.status != QuantityStatus.UNRESOLVED
                            and ln.cost_key and ln.cost_key.startswith("allow:") and (_line_quantity(ln) or 0) > 0})
        loads = mat_loads + allow_orders
        loads_txt = (f"{mat_loads} loads for {len(per_mat)} material orders (payload "
                     f"{rules.lorry_payload_kg / 1000:g} t / {rules.lorry_payload_m3:g} m3) + {allow_orders} "
                     f"allowance deliveries = {loads} loads (estimate; no logistics plan supplied)")
        loads_basis = Basis.ASSUMED
    if loads > 0:
        rr, val, src = _log_rate(st, res, "log:delivery_load", "load", params.cost_per_delivery_load,
                                 "cost_per_delivery_load")
        amount = loads * val
        st.add(line_id="4:log.delivery_loads", layer=L4, description="Delivery loads - site receipt and handling",
               amount=amount, cost_key="log:delivery_load", quantity=float(loads), unit="load", rr=rr,
               rate_value=val, basis=weakest_basis(loads_basis, rr.basis if rr else Basis.ASSUMED),
               formula=f"{loads_txt}; × {cur} {val:.2f}/load ({src}) = {cur} {amount:.2f}",
               notes="Supplier carriage is in the material rates unless charged separately (below).")
    # ---- supplier delivery charges (one order per material)
    seen: set[str] = set()
    for ln in priced_mat_lines:
        ck = ln.cost_key
        if ck in seen:
            continue
        seen.add(ck)
        rr = res.get(ck, ln.purchase_unit or ln.unit)
        if not rr.found:
            continue
        r = rr.rate
        t = r.delivery_treatment
        if t in (DeliveryTreatment.DELIVERY_CHARGED_SEPARATELY, DeliveryTreatment.EX_WORKS):
            if r.delivery_charge is None:
                st.unresolved.append(f"{ck}: rate '{r.rate_id}' is {t.value.replace('_', ' ')} but has no "
                                     "delivery_charge; carriage not priced")
                continue
            amount = float(r.delivery_charge) * rr.money_factor
            st.add(line_id=f"4:log.delivery_charge.{ck.split(':', 1)[1]}", layer=L4,
                   description=f"Supplier delivery charge - {ck.split(':', 1)[1]} (1 order)", amount=amount,
                   cost_key=ck, quantity=1.0, unit="order", rr=rr, rate_value=amount,
                   basis=weakest_basis(Basis.ASSUMED, rr.basis),
                   formula=f"1 order × {r.delivery_charge:g} {r.currency} delivery charge"
                           + (f" × {rr.money_factor:.4f}" if abs(rr.money_factor - 1) > 1e-12 else "")
                           + f" = {cur} {amount:.2f} [rate {r.rate_id}]",
                   notes="One delivery order per material assumed.")
        elif t == DeliveryTreatment.COLLECTION:
            st.notes.append(f"{ck}: rate '{r.rate_id}' is for collection; own transport is not priced separately.")
        elif t == DeliveryTreatment.UNKNOWN:
            st.warnings.append(f"{ck}: delivery treatment of rate '{r.rate_id}' is unknown; assumed included.")
    # ---- waste skips
    vol = 0.0
    no_data: list[str] = []
    for ln in priced_mat_lines:
        mat = mats.get(ln.material_id or "")
        v = _material_waste_volume(ln, mat) if mat is not None else None
        if v is None:
            if (ln.cutting_loss_qty or 0) + (ln.waste_qty or 0) > 0:
                no_data.append(ln.material_id or ln.line_id)
            continue
        vol += v
    if no_data:
        st.warnings.append("Waste volume not estimated for material(s) without volume/mass data: "
                           + ", ".join(sorted(set(no_data))))
    if vol > 0:
        bulk, skip_v = params.waste_bulking_factor, params.skip_volume_m3
        skips = math.ceil(vol * bulk / skip_v - 1e-9)
        rr, val, src = _log_rate(st, res, "log:skip", "nr", params.cost_per_skip, "cost_per_skip")
        amount = skips * val
        st.add(line_id="4:log.skips", layer=L4, description="Waste skips (cutting and waste losses)", amount=amount,
               cost_key="log:skip", quantity=float(skips), unit="nr", rr=rr, rate_value=val,
               basis=weakest_basis(Basis.ASSUMED, rr.basis if rr else Basis.ASSUMED),
               formula=f"ceil({vol:.3f} m3 waste × bulking {bulk:g} / {skip_v:g} m3 skip) = {skips} skips × "
                       f"{cur} {val:.2f} ({src}) = {cur} {amount:.2f}",
               notes="Waste volume from BoQ cutting + waste quantities via material volume per purchase unit.")
        if logistics is not None and logistics.skips and logistics.skips != skips:
            st.notes.append(f"Logistics plan reports {logistics.skips} skips; the cost engine priced {skips} skips "
                            "from the BoQ losses and CostParameters (bulking, skip volume).")


# =============================================================================
# Layers 5-9
# =============================================================================
def _prelims(st: _State, res: _Resolver, params: CostParameters, weeks: float, weeks_basis: Basis,
             weeks_src: str) -> None:
    cur = st.currency
    rr, val, src = _log_rate(st, res, "prelim:setup", "sum", params.prelims_fixed_setup, "prelims_fixed_setup")
    st.add(line_id="5:prelim.setup", layer=L5, description="Site set-up (fixed preliminaries)", amount=val,
           cost_key="prelim:setup", quantity=1.0, unit="sum", rr=rr, rate_value=val,
           basis=rr.basis if rr else Basis.ASSUMED, formula=f"1 sum × {cur} {val:.2f} ({src})")
    rr, val, src = _log_rate(st, res, "prelim:weekly", "week", params.prelims_weekly_cost, "prelims_weekly_cost")
    amount = weeks * val
    st.add(line_id="5:prelim.weekly", layer=L5, description="Time-related preliminaries", amount=amount,
           cost_key="prelim:weekly", quantity=weeks, unit="week", rr=rr, rate_value=val,
           basis=weakest_basis(weeks_basis, rr.basis if rr else Basis.ASSUMED),
           formula=f"{weeks:g} weeks ({weeks_src}) × {cur} {val:.2f}/week ({src}) = {cur} {amount:.2f}")


def _sum(st: _State, layers: list[CostLayer]) -> float:
    return sum(st.totals[layer] for layer in layers)


def _fees_to_margin(st: _State, params: CostParameters) -> None:
    cur = st.currency
    direct = _sum(st, [L1, L2, L3, L4])
    construction = direct + st.totals[L5]
    for i, fee in enumerate(params.fees):
        base, label = (direct, "layers 1-4") if fee.applies_to == "direct" else (construction, "layers 1-5")
        amount = fee.fraction * base
        st.add(line_id=f"6:fee.{i}.{_slug(fee.name)}", layer=L6, description=fee.name, amount=amount,
               quantity=base, unit=cur, rate_value=fee.fraction, basis=fee.basis,
               formula=f"{fee.fraction:.2%} × {cur} {base:.2f} ({label}) = {cur} {amount:.2f}", notes=fee.note)
    b7 = _sum(st, _LAYERS[:6])
    amount = params.contingency_fraction * b7
    st.add(line_id="7:contingency", layer=L7, description="Risk contingency", amount=amount, quantity=b7, unit=cur,
           rate_value=params.contingency_fraction, basis=Basis.ASSUMED,
           formula=f"{params.contingency_fraction:.2%} × {cur} {b7:.2f} (layers 1-6) = {cur} {amount:.2f}",
           notes=params.contingency_basis)
    b8 = _sum(st, _LAYERS[:7])
    oh = params.overhead_fraction * b8
    st.add(line_id="8:overhead", layer=L8, description="Contractor overhead", amount=oh, quantity=b8, unit=cur,
           rate_value=params.overhead_fraction, basis=Basis.ASSUMED,
           formula=f"{params.overhead_fraction:.2%} × {cur} {b8:.2f} (layers 1-7) = {cur} {oh:.2f}")
    mb = b8 + oh
    margin = params.margin_fraction * mb
    st.add(line_id="8:margin", layer=L8, description="Contractor margin", amount=margin, quantity=mb, unit=cur,
           rate_value=params.margin_fraction, basis=Basis.ASSUMED,
           formula=f"{params.margin_fraction:.2%} × {cur} {mb:.2f} (layers 1-7 + overhead) = {cur} {margin:.2f}")


def _layer9(st: _State, params: CostParameters, settings: ProjectSettings, rules: CostRules) -> bool:
    cur = st.currency
    contract = _sum(st, _LAYERS[:8])
    entered = False
    land = params.land_cost
    if land is not None:
        st.add(line_id="9:land", layer=L9, description="Land (as entered)", amount=land, quantity=1.0, unit="sum",
               rate_value=land, basis=Basis.USER_CONFIRMED, formula=f"{cur} {land:.2f} as entered")
        entered = True
    fr, fm = params.finance_rate_annual, params.finance_months
    if fr is not None and fm is not None:
        dd = rules.finance_drawdown_fraction
        base = (land or 0.0) + dd * contract
        amount = fr * fm / 12.0 * base
        st.add(line_id="9:finance", layer=L9, description="Development finance (indicative)", amount=amount,
               quantity=base, unit=cur, rate_value=fr, basis=Basis.ASSUMED,
               formula=f"{fr:.2%}/yr × {fm:g}/12 yr × ({cur} {land or 0.0:.2f} land + {dd:g} × {cur} {contract:.2f} "
                       f"contract sum) = {cur} {amount:.2f}",
               notes="Land drawn at start; build cost drawn evenly (average 50% outstanding) - assumption.")
        entered = True
    elif fr is not None or fm is not None:
        st.unresolved.append("finance: both finance_rate_annual and finance_months are needed; finance not priced")
    for name, amt in sorted(params.taxes.items()):
        if not math.isfinite(float(amt)):
            st.unresolved.append(f"tax '{name}': amount is not a finite number; not included")
            continue
        st.add(line_id=f"9:tax.{_slug(name)}", layer=L9, description=f"{name} (as entered)", amount=float(amt),
               quantity=1.0, unit="sum", rate_value=float(amt), basis=Basis.USER_CONFIRMED,
               formula=f"{cur} {float(amt):.2f} as entered", notes="Entered by the user; not computed or verified.")
        entered = True
    if settings.include_vat:
        vr = settings.vat_rate
        amount = vr * contract
        st.add(line_id="9:vat", layer=L9, description="VAT on contract sum (as entered - check applicable treatment)",
               amount=amount, quantity=contract, unit=cur, rate_value=vr, basis=Basis.ASSUMED,
               formula=f"{vr:.2%} × {cur} {contract:.2f} contract sum = {cur} {amount:.2f}",
               notes="VAT rate as entered in settings; the applicable treatment (standard / reduced / zero-rated) "
                     "is not determined here.")
        entered = True
    sf = params.sales_cost_fraction
    if sf is not None:
        if params.sales_value is None:
            st.unresolved.append("sales costs: sales_cost_fraction entered without a sales_value; not priced")
        else:
            amount = sf * params.sales_value
            st.add(line_id="9:sales_costs", layer=L9, description="Sales and marketing costs", amount=amount,
                   quantity=params.sales_value, unit=cur, rate_value=sf, basis=Basis.ASSUMED,
                   formula=f"{sf:.2%} × {cur} {params.sales_value:.2f} sales value = {cur} {amount:.2f}")
            entered = True
    return entered


# =============================================================================
# Public entry point
# =============================================================================
def estimate_construction_cost(boq: BillOfQuantities, rate_book: RateBook, params: CostParameters, *,
                               settings: ProjectSettings, programme_weeks: Optional[float] = None,
                               logistics: Optional[LogisticsResult] = None,
                               library: Optional[AssemblyLibrary] = None,
                               rules: CostRules = DEFAULT_COST_RULES) -> CostEstimate:
    """Price ``boq`` with ``rate_book`` into a nine-layer :class:`CostEstimate` (see module docstring).

    ``programme_weeks`` (e.g. from the programme module) drives time-related prelims and plant;
    without it ``params.default_programme_weeks`` is used and flagged.  ``logistics`` supplies
    delivery loads.  ``library`` supplies material masses / volumes for loads and waste (default:
    the bundled generic library).  Never raises for missing data: it is listed in
    ``unresolved_items``.
    """
    cur = settings.currency
    st = _State(currency=cur)
    idx = rate_index(rate_book)
    res = _Resolver(idx, settings)
    lib = library if library is not None else _default_library()
    mats = {m.material_id: m for m in lib.materials}
    if programme_weeks is not None and (not math.isfinite(programme_weeks) or programme_weeks < 0):
        st.warnings.append(f"programme_weeks {programme_weeks!r} is invalid; default used")
        programme_weeks = None
    if programme_weeks is None:
        weeks, weeks_basis = float(params.default_programme_weeks), Basis.ASSUMED
        weeks_src = "CostParameters.default_programme_weeks (assumed)"
        st.warnings.append(f"Programme length assumed at {weeks:g} weeks (no programme supplied); time-related "
                           "preliminaries and plant depend on it.")
    else:
        weeks, weeks_basis, weeks_src = float(programme_weeks), Basis.INFERRED, "indicative programme"

    agg = _price_quantity_lines(st, boq, res, rules)
    _derived_plant(st, boq, res, rules, weeks, weeks_basis, agg)
    _logistics(st, boq, res, params, rules, logistics, mats)
    _prelims(st, res, params, weeks, weeks_basis, weeks_src)
    # Missing rates are summarised before percentage layers so the user sees them grouped.
    for (ck, unit), refs in st.missing.items():
        rr = res.get(ck, unit)
        why = "; ".join(rr.warnings) or "no rate"
        shown = ", ".join(refs[:6]) + (f" (+{len(refs) - 6} more)" if len(refs) > 6 else "")
        st.unresolved.append(f"missing rate {ck} per {unit}: {len(refs)} item(s) not priced [{shown}] - {why}")
    _fees_to_margin(st, params)
    l9 = _layer9(st, params, settings, rules)

    # ---- warnings / notes from rate resolution (deduplicated)
    esc = sorted({rr.rate.rate_id for rr in st.used.values() if rr.escalation_factor != 1.0})
    reg = sorted({rr.rate.rate_id for rr in st.used.values() if rr.regional_factor != 1.0})
    for rr in st.used.values():
        st.warnings.extend(rr.warnings)
    if esc:
        st.notes.append(f"Escalation at {settings.annual_escalation_rate:+.1%}/yr applied to {len(esc)} rate(s) dated "
                        f"before the pricing date {settings.pricing_date.isoformat()} (assumption).")
    if settings.regional_cost_factor != 1.0:
        local = len({rr.rate.rate_id for rr in st.used.values()}) - len(reg)
        st.notes.append(f"Regional cost factor ×{settings.regional_cost_factor:g} applied to {len(reg)} rate(s) from "
                        f"other locations; {local} rate(s) located in the project area were not adjusted.")
    used_rates = {rr.rate.rate_id: rr.rate for rr in st.used.values()}
    fictional = sum(1 for r in used_rates.values() if _is_fictional(r))
    if fictional:
        st.warnings.append(f"{fictional} of {len(used_rates)} rates used are labelled FICTIONAL (demo data) - not "
                           "market prices.")
    st.warnings.extend(f"rate book: {w}" for w in rate_book.warnings[:20])
    _order_level_note(st, boq, lib, res)
    if params.sales_value is not None:
        st.notes.append(f"Sales value {cur} {params.sales_value:.2f} is reported separately; it is not a cost and is "
                        "not netted off any boundary.")

    # ---- boundaries
    boundaries: list[CostBoundary] = []
    for key, name, layers, definition, excludes in _BOUNDARY_DEFS:
        if key == "total_development_cost" and not l9:
            continue
        boundaries.append(CostBoundary(key=key, name=name, layers=list(layers), amount=_sum(st, layers),
                                       definition=definition, excludes=excludes))
    layer_totals = {layer.value: st.totals[layer] for layer in CostLayer}
    conventions = dict(COST_CONVENTIONS)
    conventions["programme_weeks"] = f"{weeks:g} weeks ({weeks_src})"
    conventions["layers"] = "; ".join(f"{layer.value}: {COST_LAYER_NAMES[layer]}" for layer in CostLayer)
    if library is None:
        conventions["material_data"] = "Material masses / volumes from the bundled generic library (none passed)."
    return CostEstimate(
        currency=cur, pricing_date=settings.pricing_date, location=settings.site_location,
        rate_book_name=rate_book.name, lines=st.lines, layer_totals=layer_totals, boundaries=boundaries,
        gia_m2=float(boq.geometry.gia_m2), unresolved_items=st.unresolved, warnings=_dedupe(st.warnings),
        sales_value=params.sales_value, programme_weeks=weeks, conventions=conventions, notes=_dedupe(st.notes),
    )


def _order_level_note(st: _State, boq: BillOfQuantities, lib: AssemblyLibrary, res: _Resolver) -> None:
    """Note how much ordering each material once (pack rounding on project totals) would save."""
    from ..quantities.procurement import procurement_schedule

    saving = 0.0
    for row in procurement_schedule(boq, lib):
        if row["rounding_saving"] <= 1e-9:
            continue
        rr = res.cache.get((f"mat:{row['material_id']}", row["purchase_unit"]))
        if rr is not None and rr.found:
            saving += row["rounding_saving"] * rr.value
    if saving > 0.5:
        st.notes.append(f"Materials are priced on per-line pack-rounded quantities; ordering each material once for "
                        f"the project (procurement_schedule) would reduce layer 1 by about {st.currency} "
                        f"{saving:.0f}.")


def _is_fictional(rate) -> bool:
    return (rate.source_type.value == "fictional_demo" or "fictional" in rate.source.lower()
            or "fictional" in rate.supplier.lower())


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for s in items:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


# =============================================================================
# Presentation helpers
# =============================================================================
def cost_lines_table(estimate: CostEstimate) -> list[dict]:
    """Flat rows for tables / CSV export (one per cost line)."""
    return [{
        "line_id": ln.line_id, "layer": ln.layer.value, "layer_name": COST_LAYER_NAMES[ln.layer],
        "description": ln.description, "cost_key": ln.cost_key, "quantity": ln.quantity, "unit": ln.unit,
        "rate": ln.rate_value, "rate_id": ln.rate_id, "amount": ln.amount, "currency": ln.currency,
        "basis": ln.basis.value, "uncertainty_low": ln.uncertainty_low, "uncertainty_high": ln.uncertainty_high,
        "quantity_line_id": ln.quantity_line_id, "formula": ln.formula, "notes": ln.notes,
    } for ln in estimate.lines]


def boundary_table(estimate: CostEstimate) -> list[dict]:
    """One row per cost boundary with amount, per-m2 GIA, definition and exclusions."""
    gia = estimate.gia_m2
    return [{
        "key": b.key, "name": b.name, "amount": b.amount,
        "per_m2_gia": b.amount / gia if gia > 0 else None, "layers": [layer.value for layer in b.layers],
        "definition": b.definition, "excludes": b.excludes,
    } for b in estimate.boundaries]
