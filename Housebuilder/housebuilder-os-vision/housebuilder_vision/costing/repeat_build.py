"""Repeat-build economics: total C(n), average C(n)/n and incremental C(n+1)-C(n).

``calculate_incremental_cost(estimate, scenario, ...)`` models the cost of building
``n`` copies of a house type as an explicit sum of components, each a closed-form
function of ``n`` (vectorised with NumPy for n = 1 .. max_n + 1):

One-off / reusable
    ``design`` (reusable design), ``tooling``, ``factory_setup`` - incurred once.
Capacity steps
    ``factory_lines`` = ``factory_line_cost x ceil(n / factory_units_per_line)``;
    ``site_establishment`` = ``site_establishment_per_site x ceil(n / houses_per_site)``;
    ``factory_steps`` / ``step_costs`` = sum over the factory / site :class:`StepCost` items
    (``StepCost.boundary``) of ``cost x ceil(max(0, n - starts_after) / every_n_units)``.
    These make C(n) jump when a threshold is crossed.
Materials with order-level pack rounding and procurement tiers
    The single-house estimate records one :class:`MaterialOrder` per material
    (``CostEstimate.material_orders``).  For n houses each order is re-rounded,
    ``ceil(n x need / pack) x pack x rate``, plus ``n x`` the other materials (allowances), so
    the single-house pack surplus is *not* multiplied by n: ``base(n)``.  A scenario that sets
    ``materials_per_house`` uses its own ``material_orders`` (else it is linear in n).  Tier
    discount ``d(k)`` = largest ``discount_fraction`` with ``min_units <= k``.
    ``discount_mode="all_units"`` (default): ``materials(n) = base(n) (1 - d(n))`` - the tier
    reached by n re-prices every unit, so the incremental cost at a tier crossing can be well
    below the per-house cost (even negative).  ``"incremental"``: house i is bought at ``d(i)``,
    ``materials(n) = sum_i (base(i) - base(i-1)) (1 - d(i))``.  Materials are split into
    ``materials_factory`` (share ``factory_material_fraction``) and ``materials_site``.
Labour with learning (``LearningCurve.model``)
    ``"unit"`` (default; unit-time model, Crawford-style): ``hours_i = h1 x max(floor, i ** b)``
    with ``b = log2(learning_rate)`` - each house's hours fall by ``1 - learning_rate`` per
    doubling of output.  ``"cumulative_average"`` (Wright): the *average* hours of the first n
    houses are ``h1 x n ** b``, so ``hours_i = h1 x max(floor, i ** (1+b) - (i-1) ** (1+b))``
    (faster learning for the same rate).  The floor always applies to unit hours.  Site labour
    hours ``h1`` come from the scenario or the estimate's labour lines and are valued at
    ``scenario.site_labour_rate`` (the estimate's blended rate is reported for comparison);
    factory labour from the scenario.  The labour scarcity premium multiplies the site labour
    of every house beyond ``labour_scarcity_threshold_units`` by ``1 + premium`` (costs can
    rise with volume).
Per-house linear items
    ``factory_overhead``, ``plant`` (scenario, else estimate layer 3), ``transport`` (loads x
    cost per load), ``site_logistics`` (scenario, else estimate layer 4 with its material
    deliveries, delivery charges and skips scaled by ``1 - factory_material_fraction`` - the
    factory receives and wastes that share), ``site_works``, ``infrastructure`` (per plot) and
    ``site_overhead`` - the time-related site overhead (supervision, welfare hire, cleaning):
    scenario value, else the estimate's time-related preliminaries (``prelim:weekly`` line) x
    ``site_overhead_share`` (labelled assumption for houses built concurrently on one site).

Boundaries
    ``factory_gate`` = tooling + factory_setup + factory_lines + factory_labour +
    factory_overhead + materials_factory + factory_steps.
    ``installed`` = factory_gate + design + transport + site_labour + materials_site + plant +
    site_logistics + site_works + site_establishment + site_overhead + infrastructure +
    step_costs.
    ``development`` = installed + fees + contingency + overhead + margin (see
    :data:`BOUNDARY_DEFINITIONS` for the fee base and the cascade).

Incremental vs underlying marginal
    ``incremental`` = C(n+1) - C(n) exactly (the headline definition).  Because it contains
    whatever step happens between house n and n+1, every row also carries ``step_events`` (the
    steps / tier crossings in that interval) and ``underlying_marginal_cost``: C*(n+1) - C*(n)
    where C* is the same model with the capacity steps removed, materials at the unrounded
    per-house need and each house priced at the tier in force for it (no re-pricing of earlier
    houses) - see :data:`UNDERLYING_MARGINAL_DEFINITION`.

Single house vs repeat build
    :func:`single_house_reconciliation` sets the single-house layers 1-5 next to the installed
    C(1) components (preliminaries -> site establishment + site overhead, etc.).  All inputs are
    labelled assumptions; learning rate, tiers, steps and shares are not calibrated against
    outturn data.
"""

from __future__ import annotations

import math
from typing import Any, Literal, Optional, Sequence

import numpy as np

from ..core.models import (
    CostEstimate,
    CostLayer,
    CostParameters,
    DiscountTier,
    LearningCurve,
    MaterialOrder,
    ProductionScenario,
    RepeatBuildResult,
    RepeatBuildRow,
    StepCost,
)

__all__ = [
    "BOUNDARY_DEFINITIONS",
    "BOUNDARY_COMPONENTS",
    "STEP_COMPONENTS",
    "METHOD_FACTORY_MATERIAL_FRACTION",
    "UNDERLYING_MARGINAL_DEFINITION",
    "LEARNING_MODEL_LABELS",
    "MAX_UNITS",
    "learning_factors",
    "tier_discount",
    "component_curves",
    "total_cost_curve",
    "calculate_incremental_cost",
    "factory_vs_installed",
    "comparison_table",
    "site_logistics_for",
    "single_house_reconciliation",
    "demo_production_scenarios",
]

Boundary = Literal["factory_gate", "installed", "development"]
MAX_UNITS = 100_000
_PACK_TOL = 1e-9

FACTORY_GATE_COMPONENTS = ("tooling", "factory_setup", "factory_lines", "factory_labour", "factory_overhead",
                           "materials_factory", "factory_steps")
INSTALLED_EXTRA = ("design", "transport", "site_labour", "materials_site", "plant", "site_logistics", "site_works",
                   "site_establishment", "site_overhead", "infrastructure", "step_costs")
DEVELOPMENT_EXTRA = ("fees", "contingency", "overhead", "margin")
#: Capacity-step components (jump when a threshold is crossed); excluded from the underlying marginal.
STEP_COMPONENTS = ("factory_lines", "factory_steps", "site_establishment", "step_costs")
#: Factory capital items excluded from the fee base.
FACTORY_CAPEX = ("tooling", "factory_setup", "factory_lines")
#: Repeat-build analogue of the single-house preliminaries (excluded from the base of 'direct' fees).
PRELIM_ANALOGUE = ("site_establishment", "site_overhead")

BOUNDARY_COMPONENTS: dict[str, tuple[str, ...]] = {
    "factory_gate": FACTORY_GATE_COMPONENTS,
    "installed": FACTORY_GATE_COMPONENTS + INSTALLED_EXTRA,
    "development": FACTORY_GATE_COMPONENTS + INSTALLED_EXTRA + DEVELOPMENT_EXTRA,
}

BOUNDARY_DEFINITIONS: dict[str, str] = {
    "factory_gate": "Factory production cost of components leaving the factory: tooling, factory setup and lines, "
                    "factory labour, factory overhead, factory capacity steps (StepCost boundary 'factory') and the "
                    "factory share of materials. Excludes transport, site work, design, site establishment and "
                    "overhead, infrastructure, site step costs, fees, contingency and OH&P.",
    "installed": "Factory gate plus transport to site, site labour, remaining (site) materials, plant, site "
                 "logistics & waste, site works, site establishment per started site, time-related site overhead "
                 "per house, infrastructure per plot, site step costs and reusable design. Excludes fees, "
                 "contingency, OH&P, land, finance, taxes, VAT and sales costs.",
    "development": "Installed cost plus professional fees, risk contingency and contractor overhead & margin "
                   "(fractions from CostParameters, in cascade). Recurring fees (recurs_per_house) = fraction x fee "
                   "base, where the fee base is installed minus reusable design minus factory capex (tooling, "
                   "factory set-up, factory lines) for 'construction' fees, and additionally minus site "
                   "establishment and site overhead (the preliminaries analogue) for 'direct' fees. One-off fees "
                   "(recurs_per_house=False, e.g. architectural & design) are covered by the scenario's reusable "
                   "design cost when it has one, else charged once on the single-house base. Contingency on installed "
                   "+ fees, overhead on that, margin on that + overhead. Excludes land, finance, taxes, VAT and "
                   "sales costs.",
}

UNDERLYING_MARGINAL_DEFINITION = (
    "Underlying marginal cost of house n+1 = C*(n+1) - C*(n), where C* is the same cost model without (a) capacity "
    "steps (factory lines, site establishment, factory and site step costs), (b) pack-rounding steps (materials at the "
    "unrounded per-house need) and (c) the all-units re-pricing of earlier houses at a procurement tier crossing "
    "(house n+1 is priced at the tier in force for it). It keeps learning, labour scarcity, the tier discount of house "
    "n+1 and every per-house item; in the development boundary the fee / contingency / OH&P cascade is applied to it. "
    "The headline incremental cost C(n+1) - C(n) is unchanged; step_events lists what it contains beyond this.")

LEARNING_MODEL_LABELS: dict[str, str] = {
    "unit": "unit-time model (Crawford-style): hours_i = h1 × max(floor_fraction, i ** log2(learning_rate))",
    "cumulative_average": "cumulative-average model (Wright): average hours of the first n units = h1 × n ** b, "
                          "b = log2(learning_rate); hours_i = h1 × max(floor_fraction, i ** (1+b) - (i-1) ** (1+b))",
}

#: Assumed share of materials processed in the factory when the scenario gives none.
METHOD_FACTORY_MATERIAL_FRACTION: dict[str, float] = {"site_built": 0.0, "offsite_panelised": 0.35,
                                                      "volumetric": 0.70}


# =============================================================================
# Building blocks (pure, vectorised)
# =============================================================================
def learning_factors(n: int, curve: LearningCurve) -> np.ndarray:
    """Per-unit labour-hours factor for units i = 1..n (array of length n), floored at ``floor_fraction``.

    ``curve.model == "unit"``: ``i ** b``; ``"cumulative_average"`` (Wright): ``i ** (1+b) - (i-1) ** (1+b)``
    (so the cumulative average of the first n units is ``n ** b`` before the floor); ``b = log2(rate)``.
    """
    i = np.arange(1, n + 1, dtype=float)
    b = math.log2(curve.learning_rate)
    if getattr(curve, "model", "unit") == "cumulative_average":
        unit = i ** (1.0 + b) - (i - 1.0) ** (1.0 + b)
    else:
        unit = i ** b
    return np.maximum(curve.floor_fraction, unit)


def tier_discount(k: np.ndarray | int, tiers: Sequence[DiscountTier]) -> np.ndarray:
    """Discount fraction in force at cumulative quantity ``k`` (largest tier with min_units <= k)."""
    k = np.atleast_1d(np.asarray(k, dtype=float))
    d = np.zeros_like(k)
    for t in tiers:
        d = np.where(k >= t.min_units, np.maximum(d, t.discount_fraction), d)
    return d


def _ceil_div(n: np.ndarray, every: int) -> np.ndarray:
    return np.ceil(np.maximum(n, 0.0) / float(every) - 1e-12)


def _layer_lines(estimate: CostEstimate, layer: CostLayer):
    return [ln for ln in estimate.lines if ln.layer == layer]


def _is_material_logistics(ln) -> bool:
    """Layer-4 lines that move or dispose of materials (site receipt loads, skips, material delivery charges)."""
    ck = ln.cost_key or ""
    return ck in ("log:delivery_load", "log:skip") or (ln.line_id.startswith("4:log.delivery_charge.")
                                                      and ck.startswith("mat:"))


def _estimate_defaults(estimate: CostEstimate) -> dict[str, float]:
    lab_lines = [ln for ln in estimate.lines if ln.layer == CostLayer.LABOUR and ln.unit == "hr" and ln.quantity]
    hours = float(sum(ln.quantity for ln in lab_lines))
    labour = float(sum(ln.amount for ln in lab_lines))
    lt = estimate.layer_totals
    l4 = float(lt.get(CostLayer.LOGISTICS_WASTE.value, 0.0))
    l4_mat = float(sum(ln.amount for ln in _layer_lines(estimate, CostLayer.LOGISTICS_WASTE)
                       if _is_material_logistics(ln)))
    prelim_time = float(sum(ln.amount for ln in _layer_lines(estimate, CostLayer.PRELIMINARIES)
                            if ln.cost_key == "prelim:weekly"))
    return {
        "materials": float(lt.get(CostLayer.MATERIALS.value, 0.0)),
        "site_labour_hours": hours,
        "blended_labour_rate": labour / hours if hours > 0 else 0.0,
        "plant": float(lt.get(CostLayer.PLANT.value, 0.0)),
        "site_logistics": l4,
        "site_logistics_materials": l4_mat,
        "site_logistics_other": l4 - l4_mat,
        "time_related_prelims": prelim_time,
        "l1_l5": float(sum(lt.get(layer.value, 0.0) for layer in list(CostLayer)[:5])),
    }


def site_logistics_for(estimate: CostEstimate, factory_material_fraction: float) -> float:
    """Site logistics & waste per house from a single-house estimate when ``factory_material_fraction`` of the
    materials is received and processed in the factory: other layer-4 items (e.g. spoil disposal) in full, the
    material deliveries, material delivery charges and skips x ``(1 - factory_material_fraction)``."""
    d = _estimate_defaults(estimate)
    return d["site_logistics_other"] + (1.0 - float(factory_material_fraction)) * d["site_logistics_materials"]


def _factory_fraction(scenario: ProductionScenario) -> tuple[float, str]:
    if scenario.factory_material_fraction is not None:
        return float(scenario.factory_material_fraction), "scenario"
    return METHOD_FACTORY_MATERIAL_FRACTION[scenario.method], f"assumed default for method '{scenario.method}'"


def _inputs(estimate: CostEstimate, scenario: ProductionScenario) -> tuple[dict[str, float], dict[str, str]]:
    """Resolved per-house base values and where each came from."""
    est = _estimate_defaults(estimate)
    v: dict[str, float] = {}
    src: dict[str, str] = {}

    def pick(name: str, scen_val: Optional[float], est_key: str, est_label: str) -> None:
        if scen_val is not None:
            v[name], src[name] = float(scen_val), "scenario"
        else:
            v[name], src[name] = est[est_key], f"single-house estimate ({est_label})"

    phi, phi_src = _factory_fraction(scenario)
    v["factory_material_fraction"], src["factory_material_fraction"] = phi, phi_src
    pick("materials_per_house", scenario.materials_per_house, "materials", "layer 1 materials")
    pick("site_labour_hours_per_house", scenario.site_labour_hours_per_house, "site_labour_hours",
         "sum of layer 2 labour hours")
    pick("plant_per_house", scenario.plant_per_house, "plant", "layer 3 plant")
    if scenario.site_logistics_per_house is not None:
        v["site_logistics_per_house"], src["site_logistics_per_house"] = \
            float(scenario.site_logistics_per_house), "scenario"
    else:
        v["site_logistics_per_house"] = est["site_logistics_other"] + (1.0 - phi) * est["site_logistics_materials"]
        src["site_logistics_per_house"] = (
            "single-house estimate (layer 4 logistics & waste)" if phi == 0 else
            f"single-house estimate (layer 4: other items + (1 - {phi:g}) x material deliveries, delivery charges "
            "and skips - the factory share is received and wasted in the factory)")
    if scenario.site_overhead_per_house is not None:
        v["site_overhead_per_house"], src["site_overhead_per_house"] = \
            float(scenario.site_overhead_per_house), "scenario"
    else:
        v["site_overhead_per_house"] = est["time_related_prelims"] * float(scenario.site_overhead_share)
        src["site_overhead_per_house"] = (
            f"single-house estimate time-related preliminaries ({est['time_related_prelims']:.0f}) x "
            f"site_overhead_share {scenario.site_overhead_share:g} (assumed share per concurrently built house)")
    v["time_related_prelims_single_house"] = est["time_related_prelims"]
    src["time_related_prelims_single_house"] = "single-house estimate (prelim:weekly line; reference)"
    # The labour rate always comes from the scenario (a plain field, stable across save / load);
    # the estimate's blended rate is reported alongside for comparison.
    v["site_labour_rate"], src["site_labour_rate"] = float(scenario.site_labour_rate), "scenario"
    v["estimate_blended_labour_rate"] = est["blended_labour_rate"]
    src["estimate_blended_labour_rate"] = "single-house estimate (layer 2 cost / hours; reference only)"
    for name in ("factory_labour_hours_per_house", "factory_labour_rate", "factory_overhead_per_house",
                 "transport_loads_per_house", "transport_cost_per_load", "site_works_per_house",
                 "infrastructure_per_plot", "site_establishment_per_site", "reusable_design_cost", "tooling_cost",
                 "factory_setup_cost", "factory_line_cost"):
        v[name] = float(getattr(scenario, name))
        src[name] = "scenario"
    orders, other, unrounded, msrc = _material_model(estimate, scenario, v["materials_per_house"])
    v["materials_other_per_house"], src["materials_other_per_house"] = other, (
        f"materials per house minus {len(orders)} order-level material order(s) (allowances and other supply items)"
        if orders else "materials per house (no order-level data: linear in n)")
    v["materials_unrounded_per_house"], src["materials_unrounded_per_house"] = unrounded, (
        "sum of order needs x rate + other materials (no pack rounding; used by the underlying marginal)")
    src["materials_per_house"] += f"; packs: {msrc}"
    return v, src


def _validate(scenario: ProductionScenario, n: int) -> None:
    if n < 1:
        raise ValueError("max_n must be at least 1")
    if n > MAX_UNITS:
        raise ValueError(f"n is limited to {MAX_UNITS} units")
    if scenario.houses_per_site < 1:
        raise ValueError("houses_per_site must be at least 1")
    if scenario.factory_units_per_line is not None and scenario.factory_units_per_line < 1:
        raise ValueError("factory_units_per_line must be at least 1 (or None for no line steps)")
    if scenario.labour_scarcity_threshold_units is not None and scenario.labour_scarcity_threshold_units < 0:
        raise ValueError("labour_scarcity_threshold_units must be >= 0")
    if scenario.labour_scarcity_premium < -1.0:
        raise ValueError("labour_scarcity_premium must be >= -1")


# =============================================================================
# Materials: order-level re-rounding for n houses
# =============================================================================
def _material_model(estimate: CostEstimate, scenario: ProductionScenario, m1: float
                    ) -> tuple[list[MaterialOrder], float, float, str]:
    """(orders, other materials per house, unrounded materials per house, source text).

    Orders come from the estimate when the scenario takes its materials from it, else from
    ``scenario.material_orders`` (None -> no orders: materials linear in n).
    """
    if scenario.materials_per_house is None:
        orders, msrc = list(estimate.material_orders), "re-rounded from the estimate's material orders"
    elif scenario.material_orders:
        orders, msrc = list(scenario.material_orders), "re-rounded from the scenario's material orders"
    else:
        orders, msrc = [], "scenario value x n (no order-level data)"
    other = m1 - sum(_order_cost(o, 1.0) for o in orders)
    unrounded = other + sum(o.purchase_required * o.rate_value for o in orders)
    return orders, float(other), float(unrounded), msrc


def _order_cost(o: MaterialOrder, n: np.ndarray | float) -> np.ndarray | float:
    """Cost of ordering ``n`` houses' need of ``o`` in whole packs."""
    need = np.asarray(n, dtype=float) * o.purchase_required
    if o.pack_size > 0:
        bought = np.ceil(need / o.pack_size - _PACK_TOL) * o.pack_size
    else:
        bought = need
    return bought * o.rate_value


def _materials_base(n: np.ndarray, orders: Sequence[MaterialOrder], other: float) -> np.ndarray:
    """Materials for n houses before tier discounts: orders re-rounded for n houses + n x other materials."""
    base = n * other
    for o in orders:
        base = base + _order_cost(o, n)
    return base


# =============================================================================
# Component curves
# =============================================================================
def _curves(estimate: CostEstimate, scenario: ProductionScenario, n_max: int,
            cost_params: Optional[CostParameters], *, smooth: bool = False) -> dict[str, np.ndarray]:
    """Cumulative cost of every component for n = 1..n_max (index n - 1).

    ``smooth=True`` gives the C* model of the underlying marginal: no capacity steps, materials at
    the unrounded per-house need, each house at the tier in force for it.
    """
    _validate(scenario, n_max)
    v, _ = _inputs(estimate, scenario)
    n = np.arange(1, n_max + 1, dtype=float)
    ones = np.ones_like(n)
    zeros = 0.0 * ones
    lc = scenario.learning
    lf = learning_factors(n_max, lc)
    site_lf = lf if "site_labour" in lc.applies_to else ones
    fac_lf = lf if "factory_labour" in lc.applies_to else ones
    scarcity = ones.copy()
    thr = scenario.labour_scarcity_threshold_units
    if thr is not None and scenario.labour_scarcity_premium:
        scarcity = np.where(n > thr, 1.0 + scenario.labour_scarcity_premium, 1.0)
    site_lab_unit = v["site_labour_hours_per_house"] * site_lf * v["site_labour_rate"] * scarcity
    fac_lab_unit = v["factory_labour_hours_per_house"] * fac_lf * v["factory_labour_rate"]
    tiers = scenario.procurement_tiers
    disc = tier_discount(n, tiers)
    if smooth:
        materials = np.cumsum(v["materials_unrounded_per_house"] * (1.0 - disc))
    else:
        orders, other, _, _ = _material_model(estimate, scenario, v["materials_per_house"])
        base = _materials_base(n, orders, other)
        if scenario.discount_mode == "all_units":
            materials = base * (1.0 - disc)
        else:
            materials = np.cumsum(np.diff(np.concatenate([[0.0], base])) * (1.0 - disc))
    phi = v["factory_material_fraction"]
    fac_steps = [s for s in scenario.step_costs if s.boundary == "factory"]
    site_steps = [s for s in scenario.step_costs if s.boundary != "factory"]
    c: dict[str, np.ndarray] = {
        "tooling": v["tooling_cost"] * ones,
        "factory_setup": v["factory_setup_cost"] * ones,
        "factory_lines": (v["factory_line_cost"] * _ceil_div(n, scenario.factory_units_per_line)
                          if scenario.factory_units_per_line and not smooth else zeros.copy()),
        "factory_labour": np.cumsum(fac_lab_unit),
        "factory_overhead": v["factory_overhead_per_house"] * n,
        "materials_factory": phi * materials,
        "factory_steps": zeros.copy() if smooth else _step_total(n, fac_steps),
        "design": v["reusable_design_cost"] * ones,
        "transport": v["transport_loads_per_house"] * v["transport_cost_per_load"] * n,
        "site_labour": np.cumsum(site_lab_unit),
        "materials_site": (1.0 - phi) * materials,
        "plant": v["plant_per_house"] * n,
        "site_logistics": v["site_logistics_per_house"] * n,
        "site_works": v["site_works_per_house"] * n,
        "site_establishment": (zeros.copy() if smooth else
                               v["site_establishment_per_site"] * _ceil_div(n, scenario.houses_per_site)),
        "site_overhead": v["site_overhead_per_house"] * n,
        "infrastructure": v["infrastructure_per_plot"] * n,
        "step_costs": zeros.copy() if smooth else _step_total(n, site_steps),
    }
    installed = sum(c[k] for k in BOUNDARY_COMPONENTS["installed"])
    cp = cost_params or CostParameters()
    base_construction = installed - c["design"] - sum(c[k] for k in FACTORY_CAPEX)
    base_direct = base_construction - sum(c[k] for k in PRELIM_ANALOGUE)
    fees = zeros.copy()
    for f in cp.fees:
        fb = base_direct if f.applies_to == "direct" else base_construction
        if getattr(f, "recurs_per_house", True):
            fees = fees + f.fraction * fb
        elif v["reusable_design_cost"] <= 0:
            fees = fees + f.fraction * fb[0] * ones  # one-off fee, charged once on the single-house base
        # else: one-off fee covered by the scenario's reusable design cost
    c["fees"] = fees
    c["contingency"] = cp.contingency_fraction * (installed + c["fees"])
    b8 = installed + c["fees"] + c["contingency"]
    c["overhead"] = cp.overhead_fraction * b8
    c["margin"] = cp.margin_fraction * (b8 + c["overhead"])
    return c


def component_curves(estimate: CostEstimate, scenario: ProductionScenario, n_max: int, *,
                     cost_params: Optional[CostParameters] = None) -> dict[str, np.ndarray]:
    """Cumulative cost of every component for n = 1..n_max (index ``n - 1``), all boundaries.

    The development components (fees, contingency, overhead, margin) use the fractions of
    ``cost_params`` (default ``CostParameters()``) on the fee bases of :data:`BOUNDARY_DEFINITIONS`.
    """
    return _curves(estimate, scenario, n_max, cost_params)


def _step_total(n: np.ndarray, steps: Sequence[StepCost]) -> np.ndarray:
    total = np.zeros_like(n)
    for s in steps:
        total = total + s.cost * _ceil_div(n - s.starts_after_units, s.every_n_units)
    return total


def _boundary_total(curves: dict[str, np.ndarray], boundary: str) -> np.ndarray:
    if boundary not in BOUNDARY_COMPONENTS:
        raise ValueError(f"boundary must be one of {sorted(BOUNDARY_COMPONENTS)}, got {boundary!r}")
    return sum(curves[k] for k in BOUNDARY_COMPONENTS[boundary])


def total_cost_curve(estimate: CostEstimate, scenario: ProductionScenario, *, boundary: Boundary = "installed",
                     max_n: int = 101, cost_params: Optional[CostParameters] = None) -> list[float]:
    """C(n) for n = 1..max_n at ``boundary``."""
    curves = component_curves(estimate, scenario, max_n, cost_params=cost_params)
    return [float(x) for x in _boundary_total(curves, boundary)]


# =============================================================================
# Step events between n and n+1
# =============================================================================
def _money(x: float, cur: str) -> str:
    return f"{'+' if x >= 0 else '-'}{cur} {abs(x):,.0f}"


def _step_events(curves: dict[str, np.ndarray], scenario: ProductionScenario, boundary: str, n_max: int,
                 phi: float, cur: str) -> list[list[str]]:
    """For k = 0..n_max-1: the steps / tier crossings that occur between house k+1 and house k+2."""
    comps = set(BOUNDARY_COMPONENTS[boundary])
    n = np.arange(1, n_max + 2, dtype=float)
    out: list[list[str]] = [[] for _ in range(n_max)]

    def jumps(arr: np.ndarray) -> np.ndarray:
        return np.flatnonzero(np.diff(arr) > 1e-9)

    def add(k: int, text: str) -> None:
        if k < n_max:
            out[k].append(text)

    if "factory_lines" in comps and scenario.factory_units_per_line:
        cnt = _ceil_div(n, scenario.factory_units_per_line)
        for k in jumps(cnt):
            add(int(k), f"factory line {int(cnt[k + 1])} for house {k + 2} "
                        f"({_money(scenario.factory_line_cost, cur)})")
    if "site_establishment" in comps:
        cnt = _ceil_div(n, scenario.houses_per_site)
        for k in jumps(cnt):
            add(int(k), f"site {int(cnt[k + 1])} established for house {k + 2} "
                        f"({_money(scenario.site_establishment_per_site, cur)})")
    for s in scenario.step_costs:
        comp = "factory_steps" if s.boundary == "factory" else "step_costs"
        if comp not in comps:
            continue
        cnt = _ceil_div(n - s.starts_after_units, s.every_n_units)
        for k in jumps(cnt):
            add(int(k), f"{s.name} ({s.boundary} step) for house {k + 2} ({_money(s.cost, cur)})")
    mat_share = (phi if "materials_factory" in comps else 0.0) + ((1.0 - phi) if "materials_site" in comps else 0.0)
    if scenario.procurement_tiers and mat_share > 0:
        d = tier_discount(n, scenario.procurement_tiers)
        mats = curves["materials_factory"] + curves["materials_site"]
        for k in np.flatnonzero(np.abs(np.diff(d)) > 1e-12):
            k = int(k)
            if k >= n_max:
                continue
            if scenario.discount_mode == "all_units":
                base_k = mats[k] / (1.0 - d[k]) if d[k] < 1 else 0.0
                reprice = -base_k * (d[k + 1] - d[k]) * mat_share
                add(k, f"procurement tier {d[k]:.0%} -> {d[k + 1]:.0%} at {k + 2} units: the first {k + 1} houses' "
                       f"materials re-priced ({_money(reprice, cur)})")
            else:
                add(k, f"procurement tier {d[k]:.0%} -> {d[k + 1]:.0%} from house {k + 2} (earlier houses not "
                       "re-priced)")
    return out


# =============================================================================
# Single house vs repeat build
# =============================================================================
def single_house_reconciliation(estimate: CostEstimate, scenario: ProductionScenario, *,
                                cost_params: Optional[CostParameters] = None) -> dict[str, Any]:
    """Single-house layers 1-5 next to the installed C(1) components, item by item.

    Returns ``{"rows": [{item, single_house, installed_c1, difference, note}], "single_house_l1_l5",
    "installed_c1", "difference", "note"}``.  The repeat build replaces the single-house preliminaries
    by site establishment per started site + time-related site overhead, values site labour at the
    scenario rate and adds items the single-house estimate does not carry (design, factory, site works,
    infrastructure, steps).
    """
    c = component_curves(estimate, scenario, 1, cost_params=cost_params)
    one = {k: float(v[0]) for k, v in c.items()}
    lt = estimate.layer_totals
    L = {i + 1: float(lt.get(layer.value, 0.0)) for i, layer in enumerate(list(CostLayer)[:5])}
    v, _ = _inputs(estimate, scenario)
    rows = [
        ("Materials (L1)", L[1], one["materials_factory"] + one["materials_site"],
         "same orders; scenario value when it sets materials_per_house"),
        ("Labour (L2)", L[2], one["site_labour"] + one["factory_labour"],
         f"site hours at the scenario rate {v['site_labour_rate']:.2f}/hr (estimate blended "
         f"{v['estimate_blended_labour_rate']:.2f}/hr); factory labour from the scenario"),
        ("Plant (L3)", L[3], one["plant"], ""),
        ("Logistics & waste (L4)", L[4], one["site_logistics"] + one["transport"],
         "site logistics (factory share of material deliveries / skips removed) + transport to site"),
        ("Preliminaries (L5)", L[5], one["site_establishment"] + one["site_overhead"],
         "set-up -> site establishment per started site; time-related -> site overhead share per house"),
        ("Design (reusable)", 0.0, one["design"], "not in the single-house estimate (fees are layer 6)"),
        ("Factory set-up, tooling, lines, overhead, steps", 0.0,
         sum(one[k] for k in ("tooling", "factory_setup", "factory_lines", "factory_overhead", "factory_steps")),
         "repeat-build only"),
        ("Site works, infrastructure, site steps", 0.0,
         sum(one[k] for k in ("site_works", "infrastructure", "step_costs")), "repeat-build only"),
    ]
    out_rows = [{"item": a, "single_house": b, "installed_c1": c1, "difference": c1 - b, "note": note}
                for a, b, c1, note in rows]
    l15 = sum(L.values())
    inst = float(_boundary_total(c, "installed")[0])
    return {
        "rows": out_rows, "single_house_l1_l5": l15, "installed_c1": inst, "difference": inst - l15,
        "note": "Single-house layers 1-5 (direct works + preliminaries) vs installed C(1) of the repeat build; the "
                "rows sum to the totals. Averages C(n)/n compare with installed C(1), not with the contract sum.",
    }


# =============================================================================
# Main entry point
# =============================================================================
def calculate_incremental_cost(estimate: CostEstimate, scenario: ProductionScenario, *,
                               boundary: Boundary = "installed", max_n: int = 101,
                               comparison_ns: Sequence[int] = (1, 10, 25, 50, 100),
                               cost_params: Optional[CostParameters] = None) -> RepeatBuildResult:
    """Rows n = 1..max_n with C(n), C(n)/n, C(n+1)-C(n), the underlying marginal, the step events between
    n and n+1 and the component breakdown of C(n).

    ``max_n`` is raised to the largest ``comparison_ns`` value if needed (noted).  C is computed
    up to ``max_n + 1`` so the incremental cost of the last row is defined.
    """
    if boundary not in BOUNDARY_COMPONENTS:
        raise ValueError(f"boundary must be one of {sorted(BOUNDARY_COMPONENTS)}, got {boundary!r}")
    cns = sorted({int(x) for x in comparison_ns})
    if any(x < 1 for x in cns):
        raise ValueError("comparison_ns must be positive integers")
    notes: list[str] = []
    if cns and cns[-1] > max_n:
        notes.append(f"max_n raised from {max_n} to {cns[-1]} to cover the comparison quantities.")
        max_n = cns[-1]
    curves = _curves(estimate, scenario, max_n + 1, cost_params)
    smooth = _curves(estimate, scenario, max_n + 1, cost_params, smooth=True)
    comps = BOUNDARY_COMPONENTS[boundary]
    C = _boundary_total(curves, boundary)
    inc = np.diff(C)
    und = np.diff(_boundary_total(smooth, boundary))
    v, src = _inputs(estimate, scenario)
    events = _step_events(curves, scenario, boundary, max_n, v["factory_material_fraction"], estimate.currency)
    rows = []
    for k in range(max_n):
        nn = k + 1
        rows.append(RepeatBuildRow.model_construct(
            n=nn, total_cost=float(C[k]), average_cost=float(C[k] / nn), incremental_cost=float(inc[k]),
            components={name: float(curves[name][k]) for name in comps},
            underlying_marginal_cost=float(und[k]), step_events=events[k]))
    lc = scenario.learning
    cp = cost_params or CostParameters()
    assumptions: dict[str, Any] = {
        "boundary": boundary,
        "boundary_definition": BOUNDARY_DEFINITIONS[boundary],
        "components": list(comps),
        "cost_model": "C(n) = sum of components; average = C(n)/n; incremental = C(n+1) - C(n).",
        "underlying_marginal_definition": UNDERLYING_MARGINAL_DEFINITION,
        "learning_curve": {
            "model": LEARNING_MODEL_LABELS[lc.model], "model_key": lc.model,
            "learning_rate": lc.learning_rate, "exponent": math.log2(lc.learning_rate),
            "floor_fraction": lc.floor_fraction, "applies_to": list(lc.applies_to), "basis": lc.basis.value,
            "note": lc.note,
            "unit_factor_at": {str(i): float(f) for i, f in zip(
                (1, 2, 10, 50, 100), learning_factors(100, lc)[[0, 1, 9, 49, 99]], strict=True)},
        },
        "materials_model": ("Each material order of the single-house estimate is re-rounded to whole packs for the "
                            "order of n houses (ceil(n x need / pack) x pack x rate) plus n x the other materials; "
                            "the single-house pack surplus is not multiplied by n."),
        "procurement_tiers": [t.model_dump() for t in sorted(scenario.procurement_tiers, key=lambda t: t.min_units)],
        "discount_mode": scenario.discount_mode,
        "discount_mode_definition": (
            "all_units: the tier reached by n applies to all n units (incremental cost can drop at a tier "
            "crossing)" if scenario.discount_mode == "all_units" else
            "incremental: each unit is discounted at the tier in force when it is bought"),
        "steps": [
            {"name": "factory lines", "every_n_units": scenario.factory_units_per_line,
             "cost": scenario.factory_line_cost, "starts_after_units": 0, "boundary": "factory"}
            if scenario.factory_units_per_line else None,
            {"name": "site establishment", "every_n_units": scenario.houses_per_site,
             "cost": scenario.site_establishment_per_site, "starts_after_units": 0, "boundary": "site"},
            *[s.model_dump() for s in scenario.step_costs],
        ],
        "labour_scarcity": {
            "threshold_units": scenario.labour_scarcity_threshold_units,
            "premium": scenario.labour_scarcity_premium,
            "rule": "site labour of each house beyond the threshold × (1 + premium)",
        },
        "site_overhead": {"per_house": v["site_overhead_per_house"], "source": src["site_overhead_per_house"],
                          "share": scenario.site_overhead_share},
        "per_house_inputs": {k: {"value": v[k], "source": src[k]} for k in sorted(v)},
        "single_house_estimate": {
            "rate_book": estimate.rate_book_name, "pricing_date": estimate.pricing_date.isoformat(),
            "currency": estimate.currency, "layer_totals": dict(estimate.layer_totals),
            "material_orders": len(estimate.material_orders),
        },
        "not_carried": "Single-house layer 5 preliminaries are represented by site establishment per started site "
                       "(set-up) and the time-related site overhead per house; layers 6-9 are not carried (the "
                       "development boundary uses CostParameters fractions instead).",
        "basis": "All repeat-build inputs are labelled assumptions; not calibrated against outturn data.",
    }
    assumptions["steps"] = [s for s in assumptions["steps"] if s is not None]
    if boundary in ("installed", "development"):
        assumptions["single_house_reconciliation"] = single_house_reconciliation(estimate, scenario,
                                                                                 cost_params=cost_params)
    if boundary == "development":
        covered = v["reusable_design_cost"] > 0
        assumptions["development_fractions"] = {
            "fees": sum(f.fraction for f in cp.fees),
            "recurring_fees": sum(f.fraction for f in cp.fees if f.recurs_per_house),
            "contingency": cp.contingency_fraction, "overhead": cp.overhead_fraction, "margin": cp.margin_fraction,
            "source": "cost_params" if cost_params is not None else "CostParameters() defaults",
        }
        assumptions["fees"] = [{
            "name": f.name, "fraction": f.fraction, "applies_to": f.applies_to, "recurs_per_house": f.recurs_per_house,
            "treatment": ("recurring: fraction x fee base of every house" if f.recurs_per_house else
                          "one-off: covered by the reusable design cost" if covered else
                          "one-off: charged once on the single-house fee base"),
        } for f in cp.fees]
        one_off = [f.name for f in cp.fees if not f.recurs_per_house]
        if one_off:
            notes.append(f"One-off fee(s) {', '.join(one_off)} "
                         + (f"are covered by the reusable design cost ({estimate.currency} "
                            f"{v['reusable_design_cost']:,.0f}) and not charged per house." if covered else
                            "are charged once (the scenario has no reusable design cost)."))
    notes.append("Average cost C(n)/n spreads one-off and step costs over n houses; the incremental cost "
                 "C(n+1)-C(n) is the cost of one more house and only includes a step cost when a threshold is "
                 "crossed - step_events lists them and the underlying marginal excludes them.")
    stepped = [f"n={r.n}" for r in rows if r.n in cns and r.step_events]
    if stepped:
        notes.append(f"At {', '.join(stepped)} the incremental cost C(n+1)-C(n) contains a capacity step or tier "
                     "crossing (house n+1 starts a site / line / step or reaches a tier); compare the underlying "
                     "marginal for the cost of one more house without the step.")
    if scenario.procurement_tiers and scenario.discount_mode == "all_units":
        notes.append("All-units discounts re-price every unit at a tier crossing, so the incremental cost there can be "
                     "below the per-house material cost (or negative).")
    if v["site_labour_hours_per_house"] == 0 and src["site_labour_hours_per_house"] != "scenario":
        notes.append("The single-house estimate has no priced labour hours; site labour is zero.")
    blended = v["estimate_blended_labour_rate"]
    if blended > 0 and abs(v["site_labour_rate"] - blended) > 0.01 * blended:
        notes.append(f"Site labour is valued at the scenario rate {v['site_labour_rate']:.2f}/hr; the single-house "
                     f"estimate's blended labour rate is {blended:.2f}/hr, so C(1) labour differs from the estimate.")
    if v["materials_other_per_house"] < -0.01:
        notes.append("The material orders cost more than materials_per_house; the other-materials share is negative "
                     "- check the scenario's material_orders.")
    if estimate.unresolved_items:
        notes.append(f"The single-house estimate has {len(estimate.unresolved_items)} unresolved item(s); repeat-build "
                     "defaults taken from it are incomplete.")
    return RepeatBuildResult(scenario_id=scenario.scenario_id, boundary=boundary,
                             boundary_definition=BOUNDARY_DEFINITIONS[boundary], currency=estimate.currency,
                             rows=rows, comparison_ns=cns, assumptions=assumptions, notes=notes)


def comparison_table(result: RepeatBuildResult) -> list[dict[str, Any]]:
    """Rows of ``result`` at its comparison quantities (n, total, average, incremental, underlying marginal,
    step events between n and n+1)."""
    by_n = {r.n: r for r in result.rows}
    return [{"n": n, "total_cost": by_n[n].total_cost, "average_cost": by_n[n].average_cost,
             "incremental_cost": by_n[n].incremental_cost,
             "underlying_marginal_cost": by_n[n].underlying_marginal_cost,
             "step_events": list(by_n[n].step_events)} for n in result.comparison_ns if n in by_n]


def factory_vs_installed(estimate: CostEstimate, scenario: ProductionScenario, *, max_n: int = 101,
                         comparison_ns: Sequence[int] = (1, 10, 25, 50, 100),
                         cost_params: Optional[CostParameters] = None) -> dict[str, Any]:
    """Factory-gate and installed results side by side, with a comparison at ``comparison_ns``.

    Returns ``{"factory_gate": RepeatBuildResult, "installed": RepeatBuildResult,
    "comparison": [ {n, factory_gate_*, installed_*, factory_share_of_installed} ... ]}``.
    """
    fg = calculate_incremental_cost(estimate, scenario, boundary="factory_gate", max_n=max_n,
                                    comparison_ns=comparison_ns, cost_params=cost_params)
    ins = calculate_incremental_cost(estimate, scenario, boundary="installed", max_n=max_n,
                                     comparison_ns=comparison_ns, cost_params=cost_params)
    fg_by, in_by = {r.n: r for r in fg.rows}, {r.n: r for r in ins.rows}
    comp = []
    for n in ins.comparison_ns:
        a, b = fg_by[n], in_by[n]
        comp.append({
            "n": n,
            "factory_gate_total": a.total_cost, "installed_total": b.total_cost,
            "factory_gate_average": a.average_cost, "installed_average": b.average_cost,
            "factory_gate_incremental": a.incremental_cost, "installed_incremental": b.incremental_cost,
            "factory_gate_underlying_marginal": a.underlying_marginal_cost,
            "installed_underlying_marginal": b.underlying_marginal_cost,
            "installed_step_events": list(b.step_events),
            "factory_share_of_installed": a.total_cost / b.total_cost if b.total_cost else None,
        })
    return {"factory_gate": fg, "installed": ins, "comparison": comp}


# =============================================================================
# Demo scenarios (fictional, labelled assumptions)
# =============================================================================
def demo_production_scenarios(estimate: CostEstimate) -> list[ProductionScenario]:
    """Two illustrative scenarios for the demo: site-built vs off-site panelised timber frame.

    Per-house values are derived from the single-house estimate with *assumed* ratios (e.g. the
    panelised route moves 45 % of site labour hours into the factory at 70 % of the hours).  All
    figures are fictional demonstration assumptions.
    """
    d = _estimate_defaults(estimate)
    tiers = [DiscountTier(min_units=10, discount_fraction=0.03), DiscountTier(min_units=25, discount_fraction=0.06),
             DiscountTier(min_units=50, discount_fraction=0.09)]
    site = ProductionScenario(
        scenario_id="site_built", name="Site-built (traditional)", method="site_built",
        site_labour_rate=d["blended_labour_rate"] or 36.0,
        reusable_design_cost=18000.0, houses_per_site=25, site_establishment_per_site=45000.0,
        infrastructure_per_plot=6500.0, procurement_tiers=tiers, site_overhead_share=0.5,
        learning=LearningCurve(learning_rate=0.95, floor_fraction=0.80, applies_to=["site_labour"]),
        labour_scarcity_threshold_units=60, labour_scarcity_premium=0.08,
        notes="Fictional demo assumptions; learning (unit-time model), tiers, scarcity premium and the 50% "
              "time-related site overhead share are not calibrated.")
    moved = 0.45
    panel = ProductionScenario(
        scenario_id="offsite_panelised", name="Off-site panelised timber frame", method="offsite_panelised",
        reusable_design_cost=26000.0, tooling_cost=60000.0, factory_setup_cost=120000.0,
        factory_units_per_line=40, factory_line_cost=85000.0,
        site_labour_hours_per_house=d["site_labour_hours"] * (1.0 - moved),
        site_labour_rate=d["blended_labour_rate"] or 36.0,
        factory_labour_hours_per_house=d["site_labour_hours"] * moved * 0.70, factory_labour_rate=29.0,
        factory_overhead_per_house=1800.0, transport_loads_per_house=3.0, transport_cost_per_load=650.0,
        houses_per_site=25, site_establishment_per_site=38000.0, infrastructure_per_plot=6500.0,
        procurement_tiers=tiers, factory_material_fraction=0.35, site_overhead_share=0.35,
        learning=LearningCurve(learning_rate=0.90, floor_fraction=0.65),
        labour_scarcity_threshold_units=60, labour_scarcity_premium=0.04,
        notes="Fictional demo assumptions: 45% of site hours move to the factory at 70% of the hours; factory "
              "line capacity 40 houses; 35% time-related site overhead share (shorter on-site programme).")
    return [site, panel]
