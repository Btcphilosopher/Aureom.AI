"""Repeat-build economics: total C(n), average C(n)/n and incremental C(n+1)-C(n).

``calculate_incremental_cost(estimate, scenario, ...)`` models the cost of building
``n`` copies of a house type as an explicit sum of components, each a closed-form
function of ``n`` (vectorised with NumPy for n = 1 .. max_n + 1):

One-off / reusable
    ``design`` (reusable design), ``tooling``, ``factory_setup`` - incurred once.
Capacity steps
    ``factory_lines`` = ``factory_line_cost x ceil(n / factory_units_per_line)``;
    ``site_establishment`` = ``site_establishment_per_site x ceil(n / houses_per_site)``;
    ``step_costs`` = sum over :class:`StepCost` of ``cost x ceil(max(0, n - starts_after) /
    every_n_units)``.  These make C(n) jump when a threshold is crossed.
Materials with procurement tiers
    base materials per house ``M`` (scenario, else the estimate's layer 1).  Tier discount
    ``d(k)`` = largest ``discount_fraction`` with ``min_units <= k``.
    ``discount_mode="all_units"`` (default): the tier reached by the order of ``n`` houses
    applies to every unit, ``materials(n) = n M (1 - d(n))`` - so the incremental cost at a
    tier crossing can be well below ``M`` (even negative).  ``"incremental"``: unit ``i``
    gets ``d(i)``, ``materials(n) = sum_i M (1 - d(i))``.  Materials are split into
    ``materials_factory`` (share ``factory_material_fraction``) and ``materials_site``.
Labour with Wright learning
    ``hours_i = h1 x max(floor_fraction, i ** log2(learning_rate))`` (cumulative-unit
    form; each unit's hours fall by ``1 - learning_rate`` per doubling of output, down to a
    floor).  Site labour hours ``h1`` come from the scenario or the estimate's labour lines and
    are valued at ``scenario.site_labour_rate`` (the estimate's blended rate is reported for
    comparison); factory labour from the scenario.  The labour scarcity premium multiplies the site
    labour of every house beyond ``labour_scarcity_threshold_units`` by ``1 + premium``
    (costs can rise with volume).
Per-house linear items
    ``factory_overhead``, ``plant`` (scenario, else estimate layer 3), ``transport``
    (loads x cost per load), ``site_logistics`` (scenario, else estimate layer 4),
    ``site_works``, ``infrastructure`` (per plot).

Boundaries
    ``factory_gate`` = tooling + factory_setup + factory_lines + factory_labour +
    factory_overhead + materials_factory.
    ``installed`` = factory_gate + design + transport + site_labour + materials_site + plant +
    site_logistics + site_works + site_establishment + infrastructure + step_costs.
    ``development`` = installed + fees + contingency + overhead + margin, applied in cascade
    with the fractions of ``cost_params`` (fees on installed, contingency on installed +
    fees, overhead on that, margin on that + overhead), mirroring the single-house engine.

The single-house layer 5 preliminaries are *not* carried: site establishment per started
site represents them.  All inputs are labelled assumptions; the learning rate, tiers and
steps are not calibrated against outturn data.
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
    ProductionScenario,
    RepeatBuildResult,
    RepeatBuildRow,
    StepCost,
)

__all__ = [
    "BOUNDARY_DEFINITIONS",
    "BOUNDARY_COMPONENTS",
    "METHOD_FACTORY_MATERIAL_FRACTION",
    "MAX_UNITS",
    "learning_factors",
    "tier_discount",
    "component_curves",
    "total_cost_curve",
    "calculate_incremental_cost",
    "factory_vs_installed",
    "comparison_table",
    "demo_production_scenarios",
]

Boundary = Literal["factory_gate", "installed", "development"]
MAX_UNITS = 100_000

FACTORY_GATE_COMPONENTS = ("tooling", "factory_setup", "factory_lines", "factory_labour", "factory_overhead",
                           "materials_factory")
INSTALLED_EXTRA = ("design", "transport", "site_labour", "materials_site", "plant", "site_logistics", "site_works",
                   "site_establishment", "infrastructure", "step_costs")
DEVELOPMENT_EXTRA = ("fees", "contingency", "overhead", "margin")

BOUNDARY_COMPONENTS: dict[str, tuple[str, ...]] = {
    "factory_gate": FACTORY_GATE_COMPONENTS,
    "installed": FACTORY_GATE_COMPONENTS + INSTALLED_EXTRA,
    "development": FACTORY_GATE_COMPONENTS + INSTALLED_EXTRA + DEVELOPMENT_EXTRA,
}

BOUNDARY_DEFINITIONS: dict[str, str] = {
    "factory_gate": "Factory production cost of components leaving the factory: tooling, factory setup and lines, "
                    "factory labour, factory overhead and the factory share of materials. Excludes transport, site "
                    "work, design, site establishment, infrastructure, fees, contingency and OH&P.",
    "installed": "Factory gate plus transport to site, site labour, remaining (site) materials, plant, site "
                 "logistics & waste, site works, site establishment per started site, infrastructure per plot and "
                 "step costs, and reusable design. Excludes fees, contingency, OH&P, land, finance, taxes, VAT and "
                 "sales costs.",
    "development": "Installed cost plus professional fees, risk contingency and contractor overhead & margin "
                   "(fractions from CostParameters, applied in cascade). Excludes land, finance, taxes, VAT and "
                   "sales costs.",
}

#: Assumed share of materials processed in the factory when the scenario gives none.
METHOD_FACTORY_MATERIAL_FRACTION: dict[str, float] = {"site_built": 0.0, "offsite_panelised": 0.35,
                                                      "volumetric": 0.70}


# =============================================================================
# Building blocks (pure, vectorised)
# =============================================================================
def learning_factors(n: int, curve: LearningCurve) -> np.ndarray:
    """Per-unit factor ``max(floor, i ** log2(rate))`` for units i = 1..n (array of length n)."""
    i = np.arange(1, n + 1, dtype=float)
    b = math.log2(curve.learning_rate)
    return np.maximum(curve.floor_fraction, i ** b)


def tier_discount(k: np.ndarray | int, tiers: Sequence[DiscountTier]) -> np.ndarray:
    """Discount fraction in force at cumulative quantity ``k`` (largest tier with min_units <= k)."""
    k = np.atleast_1d(np.asarray(k, dtype=float))
    d = np.zeros_like(k)
    for t in tiers:
        d = np.where(k >= t.min_units, np.maximum(d, t.discount_fraction), d)
    return d


def _ceil_div(n: np.ndarray, every: int) -> np.ndarray:
    return np.ceil(np.maximum(n, 0.0) / float(every) - 1e-12)


def _estimate_defaults(estimate: CostEstimate) -> dict[str, float]:
    lab_lines = [ln for ln in estimate.lines if ln.layer == CostLayer.LABOUR and ln.unit == "hr" and ln.quantity]
    hours = float(sum(ln.quantity for ln in lab_lines))
    labour = float(sum(ln.amount for ln in lab_lines))
    lt = estimate.layer_totals
    return {
        "materials": float(lt.get(CostLayer.MATERIALS.value, 0.0)),
        "site_labour_hours": hours,
        "blended_labour_rate": labour / hours if hours > 0 else 0.0,
        "plant": float(lt.get(CostLayer.PLANT.value, 0.0)),
        "site_logistics": float(lt.get(CostLayer.LOGISTICS_WASTE.value, 0.0)),
    }


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

    pick("materials_per_house", scenario.materials_per_house, "materials", "layer 1 materials")
    pick("site_labour_hours_per_house", scenario.site_labour_hours_per_house, "site_labour_hours",
         "sum of layer 2 labour hours")
    pick("plant_per_house", scenario.plant_per_house, "plant", "layer 3 plant")
    pick("site_logistics_per_house", scenario.site_logistics_per_house, "site_logistics",
         "layer 4 logistics & waste")
    # The labour rate always comes from the scenario (a plain field, stable across save / load);
    # the estimate's blended rate is reported alongside for comparison.
    v["site_labour_rate"], src["site_labour_rate"] = float(scenario.site_labour_rate), "scenario"
    v["estimate_blended_labour_rate"] = est["blended_labour_rate"]
    src["estimate_blended_labour_rate"] = "single-house estimate (layer 2 cost / hours; reference only)"
    if scenario.factory_material_fraction is not None:
        v["factory_material_fraction"] = scenario.factory_material_fraction
        src["factory_material_fraction"] = "scenario"
    else:
        v["factory_material_fraction"] = METHOD_FACTORY_MATERIAL_FRACTION[scenario.method]
        src["factory_material_fraction"] = f"assumed default for method '{scenario.method}'"
    for name in ("factory_labour_hours_per_house", "factory_labour_rate", "factory_overhead_per_house",
                 "transport_loads_per_house", "transport_cost_per_load", "site_works_per_house",
                 "infrastructure_per_plot", "site_establishment_per_site", "reusable_design_cost", "tooling_cost",
                 "factory_setup_cost", "factory_line_cost"):
        v[name] = float(getattr(scenario, name))
        src[name] = "scenario"
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


def component_curves(estimate: CostEstimate, scenario: ProductionScenario, n_max: int, *,
                     cost_params: Optional[CostParameters] = None) -> dict[str, np.ndarray]:
    """Cumulative cost of every component for n = 1..n_max (index ``n - 1``), all boundaries.

    The development components (fees, contingency, overhead, margin) are computed on the
    installed total with the fractions of ``cost_params`` (default ``CostParameters()``).
    """
    _validate(scenario, n_max)
    v, _ = _inputs(estimate, scenario)
    n = np.arange(1, n_max + 1, dtype=float)
    ones = np.ones_like(n)
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
    M = v["materials_per_house"]
    tiers = scenario.procurement_tiers
    if scenario.discount_mode == "all_units":
        materials = n * M * (1.0 - tier_discount(n, tiers))
    else:
        materials = np.cumsum(M * (1.0 - tier_discount(n, tiers)))
    phi = v["factory_material_fraction"]
    c: dict[str, np.ndarray] = {
        "tooling": v["tooling_cost"] * ones,
        "factory_setup": v["factory_setup_cost"] * ones,
        "factory_lines": (v["factory_line_cost"] * _ceil_div(n, scenario.factory_units_per_line)
                          if scenario.factory_units_per_line else 0.0 * ones),
        "factory_labour": np.cumsum(fac_lab_unit),
        "factory_overhead": v["factory_overhead_per_house"] * n,
        "materials_factory": phi * materials,
        "design": v["reusable_design_cost"] * ones,
        "transport": v["transport_loads_per_house"] * v["transport_cost_per_load"] * n,
        "site_labour": np.cumsum(site_lab_unit),
        "materials_site": (1.0 - phi) * materials,
        "plant": v["plant_per_house"] * n,
        "site_logistics": v["site_logistics_per_house"] * n,
        "site_works": v["site_works_per_house"] * n,
        "site_establishment": v["site_establishment_per_site"] * _ceil_div(n, scenario.houses_per_site),
        "infrastructure": v["infrastructure_per_plot"] * n,
        "step_costs": _step_total(n, scenario.step_costs),
    }
    installed = sum(c[k] for k in BOUNDARY_COMPONENTS["installed"])
    cp = cost_params or CostParameters()
    fee_frac = sum(f.fraction for f in cp.fees)
    c["fees"] = fee_frac * installed
    c["contingency"] = cp.contingency_fraction * (installed + c["fees"])
    b8 = installed + c["fees"] + c["contingency"]
    c["overhead"] = cp.overhead_fraction * b8
    c["margin"] = cp.margin_fraction * (b8 + c["overhead"])
    return c


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
# Main entry point
# =============================================================================
def calculate_incremental_cost(estimate: CostEstimate, scenario: ProductionScenario, *,
                               boundary: Boundary = "installed", max_n: int = 101,
                               comparison_ns: Sequence[int] = (1, 10, 25, 50, 100),
                               cost_params: Optional[CostParameters] = None) -> RepeatBuildResult:
    """Rows n = 1..max_n with C(n), C(n)/n, C(n+1)-C(n) and the component breakdown of C(n).

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
    curves = component_curves(estimate, scenario, max_n + 1, cost_params=cost_params)
    comps = BOUNDARY_COMPONENTS[boundary]
    C = _boundary_total(curves, boundary)
    inc = np.diff(C)
    rows = []
    for k in range(max_n):
        nn = k + 1
        rows.append(RepeatBuildRow.model_construct(
            n=nn, total_cost=float(C[k]), average_cost=float(C[k] / nn), incremental_cost=float(inc[k]),
            components={name: float(curves[name][k]) for name in comps}))
    v, src = _inputs(estimate, scenario)
    lc = scenario.learning
    assumptions: dict[str, Any] = {
        "boundary": boundary,
        "boundary_definition": BOUNDARY_DEFINITIONS[boundary],
        "components": list(comps),
        "cost_model": "C(n) = sum of components; average = C(n)/n; incremental = C(n+1) - C(n).",
        "learning_curve": {
            "model": "Wright cumulative-unit: hours_i = h1 × max(floor_fraction, i ** log2(learning_rate))",
            "learning_rate": lc.learning_rate, "exponent": math.log2(lc.learning_rate),
            "floor_fraction": lc.floor_fraction, "applies_to": list(lc.applies_to), "basis": lc.basis.value,
            "note": lc.note,
            "unit_factor_at": {str(i): float(f) for i, f in zip(
                (1, 2, 10, 50, 100), learning_factors(100, lc)[[0, 1, 9, 49, 99]], strict=True)},
        },
        "procurement_tiers": [t.model_dump() for t in sorted(scenario.procurement_tiers, key=lambda t: t.min_units)],
        "discount_mode": scenario.discount_mode,
        "discount_mode_definition": (
            "all_units: the tier reached by n applies to all n units (incremental cost can drop at a tier "
            "crossing)" if scenario.discount_mode == "all_units" else
            "incremental: each unit is discounted at the tier in force when it is bought"),
        "steps": [
            {"name": "factory lines", "every_n_units": scenario.factory_units_per_line,
             "cost": scenario.factory_line_cost, "starts_after_units": 0}
            if scenario.factory_units_per_line else None,
            {"name": "site establishment", "every_n_units": scenario.houses_per_site,
             "cost": scenario.site_establishment_per_site, "starts_after_units": 0},
            *[s.model_dump() for s in scenario.step_costs],
        ],
        "labour_scarcity": {
            "threshold_units": scenario.labour_scarcity_threshold_units,
            "premium": scenario.labour_scarcity_premium,
            "rule": "site labour of each house beyond the threshold × (1 + premium)",
        },
        "per_house_inputs": {k: {"value": v[k], "source": src[k]} for k in sorted(v)},
        "single_house_estimate": {
            "rate_book": estimate.rate_book_name, "pricing_date": estimate.pricing_date.isoformat(),
            "currency": estimate.currency, "layer_totals": dict(estimate.layer_totals),
        },
        "not_carried": "Single-house layer 5 preliminaries (replaced by site establishment per started site) and "
                       "layers 6-9 (development boundary uses CostParameters fractions instead).",
        "basis": "All repeat-build inputs are labelled assumptions; not calibrated against outturn data.",
    }
    assumptions["steps"] = [s for s in assumptions["steps"] if s is not None]
    if boundary == "development":
        cp = cost_params or CostParameters()
        assumptions["development_fractions"] = {
            "fees": sum(f.fraction for f in cp.fees), "contingency": cp.contingency_fraction,
            "overhead": cp.overhead_fraction, "margin": cp.margin_fraction,
            "source": "cost_params" if cost_params is not None else "CostParameters() defaults",
        }
    notes.append("Average cost C(n)/n spreads one-off and step costs over n houses; the incremental cost "
                 "C(n+1)-C(n) is the cost of one more house and only includes a step cost when a threshold is "
                 "crossed.")
    if scenario.procurement_tiers and scenario.discount_mode == "all_units":
        notes.append("All-units discounts re-price every unit at a tier crossing, so the incremental cost there can be "
                     "below the per-house material cost (or negative).")
    if v["site_labour_hours_per_house"] == 0 and src["site_labour_hours_per_house"] != "scenario":
        notes.append("The single-house estimate has no priced labour hours; site labour is zero.")
    blended = v["estimate_blended_labour_rate"]
    if blended > 0 and abs(v["site_labour_rate"] - blended) > 0.01 * blended:
        notes.append(f"Site labour is valued at the scenario rate {v['site_labour_rate']:.2f}/hr; the single-house "
                     f"estimate's blended labour rate is {blended:.2f}/hr, so C(1) labour differs from the estimate.")
    if estimate.unresolved_items:
        notes.append(f"The single-house estimate has {len(estimate.unresolved_items)} unresolved item(s); repeat-build "
                     "defaults taken from it are incomplete.")
    return RepeatBuildResult(scenario_id=scenario.scenario_id, boundary=boundary,
                             boundary_definition=BOUNDARY_DEFINITIONS[boundary], currency=estimate.currency,
                             rows=rows, comparison_ns=cns, assumptions=assumptions, notes=notes)


def comparison_table(result: RepeatBuildResult) -> list[dict[str, float]]:
    """Rows of ``result`` at its comparison quantities (n, total, average, incremental)."""
    by_n = {r.n: r for r in result.rows}
    return [{"n": n, "total_cost": by_n[n].total_cost, "average_cost": by_n[n].average_cost,
             "incremental_cost": by_n[n].incremental_cost} for n in result.comparison_ns if n in by_n]


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
        infrastructure_per_plot=6500.0, procurement_tiers=tiers,
        learning=LearningCurve(learning_rate=0.95, floor_fraction=0.80, applies_to=["site_labour"]),
        labour_scarcity_threshold_units=60, labour_scarcity_premium=0.08,
        notes="Fictional demo assumptions; learning, tiers and scarcity premium are not calibrated.")
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
        procurement_tiers=tiers, factory_material_fraction=0.35,
        learning=LearningCurve(learning_rate=0.90, floor_fraction=0.65),
        labour_scarcity_threshold_units=60, labour_scarcity_premium=0.04,
        notes="Fictional demo assumptions: 45% of site hours move to the factory at 70% of the hours; factory "
              "line capacity 40 houses.")
    return [site, panel]
