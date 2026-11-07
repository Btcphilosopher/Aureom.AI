"""Build-scenario comparison: each scenario is one coherent house, evaluated end to end.

:func:`compare_build_scenarios` evaluates every :class:`BuildScenario` as a complete,
internally consistent house and reports one :class:`ScenarioOutcome` per scenario::

    twin   = the base twin (same hypothesis)  or  build_parametric_twin(scenario hypothesis,
             selection = base twin's assembly selection, same settings / visual finishes)
    twin   = apply_construction_assemblies(twin, assembly overrides [+ foundation option],
                                           actor="scenario")      # basis ASSUMED: a hypothesis
    boq    = calculate_quantities(twin)            # wall thickness -> GIA, areas, layers
    prog   = build_programme(boq)                  # indicative CPM
    logi   = plan_deliveries(boq, prog)
    cost   = estimate_construction_cost(boq, rate book [x rate_multiplier], cost parameters
                                        [money fallbacks x rate_multiplier],
                                        programme_weeks=prog weeks, logistics=logi)
    carbon = embodied_carbon(boq, logistics=logi); heat = heat_loss(twin, boq.geometry)
    [P10/P50/P90 = simulate_uncertainty(twin, ...) with a smaller sample when simulate=True]

Rules
-----
* **No averaging.**  Outcomes are never averaged across geometry hypotheses or
  construction assemblies; hypothesis plausibility weights are subjective priors and
  are only reported.  Each P10/P50/P90 comes from a simulation of that one scenario.
* When a scenario names no hypothesis, or the base twin's own hypothesis, the base twin
  itself is used, so the user's edits are kept.  Another hypothesis is rebuilt from
  the hypothesis with the base twin's assembly selection; edits made to the base twin
  do not carry over (stated in the outcome's key assumptions).
* Scenario assembly choices are recorded with ``actor="scenario"`` (basis ASSUMED).
* A scenario's ``foundation_option`` is part of the house: its simulation holds that
  foundation (``simulate_uncertainty(fixed_foundation=...)``; ground classes are not
  sampled), so its P10/P50/P90 describe that scenario only.
* ``rate_multiplier`` scales every rate of the rate book for that scenario - values and
  per-order delivery charges - and the money fallbacks of the cost parameters
  (``COST_PARAMETER_FALLBACKS``: prelims weekly / set-up, delivery load, skip), a labelled
  price-level assumption.  Fractions (fees, contingency, overhead, margin) scale with
  their base; land, taxes and sales value are not construction prices and are unchanged.
* Simulated scenarios share the seed *and* the random numbers of every input they have
  in common (one stream per input, ``simulation.uncertainty``), so differences between
  their P-values are paired comparisons rather than independent noise.
* Hypothesis and assembly-selection uncertainty is never sampled into one house: it stays
  in separate scenarios.  :func:`scenario_spread_entries` reports the spread between them
  (per hypothesis, construction method, foundation and price level) as information-value
  entries, and :func:`combined_information_value` ranks those together with the
  within-scenario groups of a simulation.

Boundaries: indicative concept-stage comparison.  Heat loss is a simplified
steady-state coefficient (not SAP/SBEM/PHPP), carbon uses illustrative factors, the
programme is an indicative critical path; nothing here is a compliance, structural or
energy-performance claim.  Bundled demo prices are fictional.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence, Union

from ..core.models import (
    AssemblySelection,
    AssemblyLibrary,
    BillOfQuantities,
    BuildingTwin,
    BuildScenario,
    CarbonResult,
    CostEstimate,
    CostParameters,
    GeometryHypothesis,
    HeatLossResult,
    LogisticsResult,
    ProgrammeResult,
    RateBook,
    ScaleCalibration,
    ScenarioComparison,
    ScenarioOutcome,
    SimulationConfig,
    SimulationResult,
)
from ..core.settings import AssumptionLibrary, ProjectSettings
from ..costing.engine import COST_PARAMETER_FALLBACKS, estimate_construction_cost
from ..quantities.measures import TakeoffAssumptions
from ..quantities.takeoff import apply_construction_assemblies, calculate_quantities, wall_thicknesses
from .carbon import embodied_carbon
from .logistics import plan_deliveries
from .programme import build_programme
from .thermal import heat_loss
from .uncertainty import COST_METRIC, simulate_uncertainty

__all__ = ["ScenarioEvaluation", "evaluate_build_scenario", "compare_build_scenarios", "scale_rate_book",
           "scale_cost_parameters", "scenario_spread_entries", "combined_information_value",
           "SCENARIO_SPREAD_ACTIONS", "SCENARIO_SPREAD_LABELS", "DEFAULT_SCENARIO_SAMPLES", "COMPARISON_NOTES"]

#: Sample count of the per-scenario simulation when ``simulate=True`` and no config is given.
DEFAULT_SCENARIO_SAMPLES = 200

COMPARISON_NOTES: tuple[str, ...] = (
    "Each outcome is one coherent house: one geometry hypothesis, one assembly set, one foundation option. "
    "Results are never averaged across hypotheses or construction assemblies.",
    "Hypothesis plausibility weights are subjective priors (not calibrated probabilities) and are reported only; "
    "they are not used to weight or average outcomes.",
    "Construction cost = boundary 'construction_incl_contingency' (layers 1-7); contract sum adds overhead & "
    "margin (layer 8). Cost per m2 uses total GIA (garages included).",
    "Heat loss: simplified steady-state coefficient (not SAP/SBEM/PHPP, no compliance claim). Embodied carbon: "
    "A1-A3 + A5 waste share (+A4 when configured) with illustrative factors. Programme: indicative critical path.",
    "Assembly choices in a scenario are hypotheses (basis ASSUMED); appearance never establishes structure - a "
    "brick-like facade is compatible with masonry cavity and timber frame with brick outer leaf.",
)

#: Resolving action of each between-scenario dimension (see :func:`scenario_spread_entries`).
SCENARIO_SPREAD_ACTIONS: dict[str, str] = {
    # a dimensioned floor plan collapses the hypotheses (H-B only when the plan outlines an extension block);
    # a linked side elevation observes the main depth; a twin edit enters it
    "hypothesis": ("Confirm the footprint: upload a floor plan with the building outline (one box per block) and "
                   "one measured dimension, or a side elevation, or enter the measured depth"),
    "construction": "Confirm the construction method / specification with the designer",
    "foundation": "Commission a site/ground investigation and have the foundation designed by an engineer",
    "price_level": "Obtain supplier quotations / agree the price level",
}
#: What each between-scenario dimension is (labels; alternatives are kept apart, never averaged).
SCENARIO_SPREAD_LABELS: dict[str, str] = {
    "hypothesis": "hidden footprint - geometry hypothesis (not averaged)",
    "construction": "construction system choice (not averaged)",
    "foundation": "foundation choice (not averaged)",
    "price_level": "scenario price level (not averaged)",
}


@dataclass
class ScenarioEvaluation:
    """Everything computed for one scenario (the outcome plus the objects behind it)."""

    scenario: BuildScenario
    twin: BuildingTwin
    boq: BillOfQuantities
    programme: ProgrammeResult
    logistics: LogisticsResult
    estimate: CostEstimate
    carbon: CarbonResult
    heat_loss: HeatLossResult
    simulation: Optional[SimulationResult]
    outcome: ScenarioOutcome


def _multiplier(multiplier: float) -> float:
    m = float(multiplier)
    if not (m > 0.0) or m != m or m == float("inf"):
        raise ValueError(f"rate_multiplier must be a positive number, got {multiplier!r}")
    return m


def scale_rate_book(rate_book: RateBook, multiplier: float) -> RateBook:
    """A copy of ``rate_book`` with every price multiplied (labelled scenario price level).

    Scales each rate's ``value`` and its per-order ``delivery_charge`` (when set).
    """
    m = _multiplier(multiplier)
    if m == 1.0:
        return rate_book

    def scaled(r):
        upd: dict[str, Any] = {"value": r.value * m}
        if r.delivery_charge is not None:
            upd["delivery_charge"] = r.delivery_charge * m
        return r.model_copy(update=upd)

    return rate_book.model_copy(update={
        "name": f"{rate_book.name} x{m:g} (scenario price level)",
        "rates": [scaled(r) for r in rate_book.rates],
        "notes": (rate_book.notes + " " if rate_book.notes else "")
                 + f"All rates and delivery charges x{m:g} for a build scenario.",
    })


def scale_cost_parameters(cost_params: CostParameters, multiplier: float) -> CostParameters:
    """A copy of ``cost_params`` with the money fallbacks (``COST_PARAMETER_FALLBACKS``) multiplied.

    These amounts price preliminaries and logistics when the rate book has no ``prelim:`` / ``log:``
    rate, so a scenario price level must scale them like the rates.  Fractions and the layer-9 items
    (land, taxes, sales value) are unchanged.
    """
    m = _multiplier(multiplier)
    if m == 1.0:
        return cost_params
    upd = {k: float(getattr(cost_params, k)) * m for k in COST_PARAMETER_FALLBACKS}
    note = f"Money fallbacks ({', '.join(COST_PARAMETER_FALLBACKS)}) x{m:g} for a build scenario price level."
    upd["notes"] = (cost_params.notes + " " if cost_params.notes else "") + note
    return cost_params.model_copy(update=upd)


def _assembly_ids(sel: AssemblySelection) -> dict[str, str]:
    out = {k: str(v) for k, v in sel.model_dump(exclude={"block_overrides", "basis"}).items() if isinstance(v, str)}
    for bid, ov in sorted(sel.block_overrides.items()):
        for el, aid in sorted(ov.items()):
            out[f"{el}@{bid}"] = aid
    return out


def _scenario_twin(base_twin: BuildingTwin, hypotheses: Sequence[GeometryHypothesis], scenario: BuildScenario,
                   library: AssemblyLibrary) -> tuple[BuildingTwin, Optional[GeometryHypothesis], list[str]]:
    from ..twin.builder import build_parametric_twin  # local import: twin is only needed here

    notes: list[str] = []
    hid = scenario.hypothesis_id or base_twin.source_hypothesis_id
    hyp = next((h for h in hypotheses if h.hypothesis_id == hid), None) if hid else None
    if hid is None or hid == base_twin.source_hypothesis_id:
        twin = base_twin
        if base_twin.edit_log:
            notes.append(f"Base twin v{base_twin.version} used as is (its {len(base_twin.edit_log)} edit(s) kept).")
    else:
        if hyp is None:
            raise ValueError(f"scenario '{scenario.scenario_id}' references unknown hypothesis '{hid}'")
        twin = build_parametric_twin(hyp, selection=base_twin.assemblies, settings=base_twin.settings,
                                     visual_finishes=base_twin.visual_finishes,
                                     twin_id=f"twin-{scenario.scenario_id}-{hyp.hypothesis_id}"[:80])
        notes.append(f"Twin rebuilt from hypothesis {hyp.hypothesis_id} with the base assembly selection; edits made "
                     "to the base twin are not carried over.")
    changes = dict(scenario.assembly_overrides)
    if scenario.foundation_option:
        changes["foundation"] = scenario.foundation_option
    if changes:
        twin = apply_construction_assemblies(twin, changes, library, actor="scenario",
                                             reason=f"build scenario {scenario.scenario_id}: {scenario.name}"[:200])
    return twin, hyp, notes


def evaluate_build_scenario(base_twin: BuildingTwin, hypotheses: Sequence[GeometryHypothesis],
                            scenario: BuildScenario, library: AssemblyLibrary, rate_book: RateBook,
                            cost_params: CostParameters, settings: ProjectSettings, *, simulate: bool = False,
                            config: Optional[SimulationConfig] = None,
                            calibration: Optional[ScaleCalibration] = None,
                            assumptions: Union[AssumptionLibrary, TakeoffAssumptions, None] = None,
                            crew_sizes: Optional[Mapping[str, float]] = None) -> ScenarioEvaluation:
    """Evaluate one scenario as a coherent house (see module docstring)."""
    twin, hyp, notes = _scenario_twin(base_twin, hypotheses, scenario, library)
    book = scale_rate_book(rate_book, scenario.rate_multiplier)
    params = scale_cost_parameters(cost_params, scenario.rate_multiplier)
    boq = calculate_quantities(twin, library, assumptions=assumptions)
    prog = build_programme(boq, library, crew_sizes=crew_sizes)
    logi = plan_deliveries(boq, library, prog, waste_bulking_factor=params.waste_bulking_factor,
                           skip_volume_m3=params.skip_volume_m3)
    est = estimate_construction_cost(boq, book, params, settings=settings, programme_weeks=prog.duration_weeks,
                                     logistics=logi, library=library)
    carbon = embodied_carbon(boq, library, logistics=logi)
    heat = heat_loss(twin, boq.geometry, library, settings)
    sim: Optional[SimulationResult] = None
    fixed_fdn = f"build scenario {scenario.scenario_id}" if scenario.foundation_option else None
    if simulate:
        cfg = config if config is not None else SimulationConfig(n_samples=DEFAULT_SCENARIO_SAMPLES)
        sim = simulate_uncertainty(twin, library, book, params, settings, config=cfg, calibration=calibration,
                                   assumptions=assumptions, scenario_id=scenario.scenario_id, crew_sizes=crew_sizes,
                                   fixed_foundation=fixed_fdn)
    bnd = {b.key: b.amount for b in est.boundaries}
    construction = bnd.get("construction_incl_contingency", float("nan"))
    gia = float(boq.geometry.gia_m2)
    t_ext, _ = wall_thicknesses(twin, library)
    labour = sum(float(ln.labour_hours or 0.0) for ln in boq.lines)
    sel = twin.assemblies
    ext = library.assembly(sel.external_wall)
    fdn = library.foundation(sel.foundation)
    key: list[str] = []
    if hyp is not None:
        key.append(f"Geometry hypothesis {hyp.hypothesis_id} '{hyp.name}' (subjective plausibility "
                   f"{hyp.plausibility:.2f}, not a probability).")
    else:
        key.append(f"Geometry: base twin '{twin.twin_id}' (hypothesis {twin.source_hypothesis_id or 'n/a'}).")
    key.append(f"External wall: {ext.name} ({ext.total_thickness_m:.3f} m, structural system "
               f"'{ext.structural_system}') - an assumed construction, not identified from appearance.")
    key.append(f"Foundation: {fdn.name} (indicative; requires site investigation and engineer's design).")
    if scenario.rate_multiplier != 1.0:
        key.append(f"All rates, delivery charges and money fallbacks (prelims, delivery load, skip) "
                   f"x{scenario.rate_multiplier:g} (scenario price-level assumption).")
    if scenario.production_scenario_id:
        key.append(f"Linked production scenario: {scenario.production_scenario_id} (repeat-build economics are "
                   "reported separately).")
    key.append(f"Programme {prog.duration_weeks:.1f} weeks (indicative critical path) drives time-related "
               "preliminaries.")
    if est.unresolved_items:
        key.append(f"{len(est.unresolved_items)} unresolved cost item(s) are excluded from the totals.")
    if sim is not None:
        held = (f"; foundation held at '{sel.foundation}' - ground classes not sampled" if fixed_fdn else "")
        key.append(f"P10/P50/P90 from {sim.n_samples} samples of this scenario only (assumed scenario uncertainty"
                   f"{held}).")
    key.extend(notes)
    outcome = ScenarioOutcome(
        scenario_id=scenario.scenario_id, name=scenario.name, hypothesis_id=twin.source_hypothesis_id,
        gia_m2=gia, external_wall_thickness_m=float(t_ext), construction_cost=construction,
        contract_sum=bnd.get("contract_sum", float("nan")),
        cost_per_m2_gia=construction / gia if gia > 0 else float("nan"), labour_hours=labour,
        programme_weeks=float(prog.duration_weeks), embodied_carbon_kgco2e=float(carbon.total_kgco2e),
        heat_loss_coefficient_w_k=float(heat.heat_loss_coefficient_w_k), peak_heat_load_kw=float(heat.peak_heat_load_kw),
        cost_p10=_p(sim, "p10"), cost_p50=_p(sim, "p50"), cost_p90=_p(sim, "p90"), key_assumptions=key,
        assemblies=_assembly_ids(sel), rate_multiplier=float(scenario.rate_multiplier))
    return ScenarioEvaluation(scenario=scenario, twin=twin, boq=boq, programme=prog, logistics=logi, estimate=est,
                              carbon=carbon, heat_loss=heat, simulation=sim, outcome=outcome)


def _p(sim: Optional[SimulationResult], attr: str) -> Optional[float]:
    if sim is None:
        return None
    for m in sim.metrics:
        if m.metric == COST_METRIC:
            return float(getattr(m, attr))
    return None


def compare_build_scenarios(base_twin: BuildingTwin, hypotheses: Sequence[GeometryHypothesis],
                            scenarios: Sequence[BuildScenario], library: AssemblyLibrary, rate_book: RateBook,
                            cost_params: CostParameters, settings: ProjectSettings, *, simulate: bool = False,
                            config: Optional[SimulationConfig] = None,
                            calibration: Optional[ScaleCalibration] = None,
                            assumptions: Union[AssumptionLibrary, TakeoffAssumptions, None] = None,
                            crew_sizes: Optional[Mapping[str, float]] = None) -> ScenarioComparison:
    """Evaluate each scenario as one coherent house and return the side-by-side outcomes.

    ``simulate=True`` adds cost P10/P50/P90 per scenario from :func:`simulate_uncertainty` with
    ``config`` (default ``SimulationConfig(n_samples=200)``, same seed for every scenario).  The
    simulations use common random numbers: every input shared by two scenarios (a rate, a trade's
    productivity, the image scale, an assumed prior ...) gets the same draws in both, so their samples
    are paired and P-value differences reflect the scenarios rather than sampling noise; each P-value is
    still a marginal estimate with its own sampling error (use >= 200 samples per scenario).
    Raises ``ValueError`` for duplicate scenario ids, unknown hypotheses or invalid assembly ids.
    """
    ids = [s.scenario_id for s in scenarios]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate scenario ids")
    evals = [evaluate_build_scenario(base_twin, hypotheses, s, library, rate_book, cost_params, settings,
                                     simulate=simulate, config=config, calibration=calibration,
                                     assumptions=assumptions, crew_sizes=crew_sizes) for s in scenarios]
    notes = list(COMPARISON_NOTES)
    if simulate and evals:
        n = evals[0].simulation.n_samples if evals[0].simulation is not None else 0
        notes.append(f"Cost P10/P50/P90 per scenario from {n} samples each (assumed scenario uncertainty; not "
                     "statistically calibrated). Common random numbers: inputs shared by two scenarios get the same "
                     "draws, so the samples are paired across scenarios.")
        if n and n < DEFAULT_SCENARIO_SAMPLES:
            notes.append(f"Only {n} samples per scenario: each P-value has a sampling error of a few percent; small "
                         f"P-value differences between scenarios are not meaningful (use >= {DEFAULT_SCENARIO_SAMPLES}).")
    if any(r.source_type.value == "fictional_demo" for r in rate_book.rates):
        notes.append("Rate book contains FICTIONAL demo prices - comparisons illustrate the method, not market costs.")
    return ScenarioComparison(outcomes=[e.outcome for e in evals], notes=notes)


# =============================================================================
# Between-scenario spread as information value (hypotheses and assemblies stay separate scenarios)
# =============================================================================
_SPREAD_DIMS = ("hypothesis", "construction", "foundation", "price_level")


def _legacy_line(o: ScenarioOutcome, prefix: str) -> str:
    return next((k for k in o.key_assumptions if k.startswith(prefix)), "")


def _scenario_dims(o: ScenarioOutcome) -> dict[str, Any]:
    """What makes a scenario distinct: hypothesis, construction assemblies, foundation, price level."""
    if o.assemblies:
        asm = dict(o.assemblies)
        fdn = asm.pop("foundation", "")
        construction: Any = tuple(sorted(asm.items()))
    else:  # outcomes saved before ScenarioOutcome.assemblies existed: use the key-assumption lines
        construction, fdn = _legacy_line(o, "External wall:"), _legacy_line(o, "Foundation:")
    return {"hypothesis": o.hypothesis_id or "", "construction": construction, "foundation": fdn,
            "price_level": round(float(o.rate_multiplier), 9)}


def _describe(dim: str, o: ScenarioOutcome, other: ScenarioOutcome) -> str:
    if dim == "hypothesis":
        return f"hypothesis {o.hypothesis_id or 'n/a'}"
    if dim == "price_level":
        return f"rates x{o.rate_multiplier:g}"
    if dim == "foundation":
        return o.assemblies.get("foundation") or _legacy_line(o, "Foundation:")[:80]
    if o.assemblies and other.assemblies:
        diff = [f"{k}={v}" for k, v in sorted(o.assemblies.items()) if k != "foundation" and other.assemblies.get(k) != v]
        return ", ".join(diff) or "same assemblies"
    return _legacy_line(o, "External wall:")[:80]


def scenario_spread_entries(comparison: ScenarioComparison, *, currency: Optional[str] = None
                            ) -> list[dict[str, Any]]:
    """The cost spread between build scenarios, as information-value entries (largest first).

    Hypothesis and assembly-selection uncertainty is deliberately kept as separate scenarios - never
    sampled or averaged into one house - so it never appears among a simulation's within-scenario groups.
    This reports it: for each dimension (``hypothesis``, ``construction`` = the non-foundation assemblies,
    ``foundation``, ``price_level``) the scenarios that differ *only* in that dimension are compared and
    the largest spread of their cost is reported - the cost range that resolving that question would
    settle.  The cost is each scenario's simulated P50 when every outcome has one, else its
    deterministic ``construction_incl_contingency``.  Scenarios that differ in several dimensions at
    once are not used (the spread could not be attributed).

    Entry keys: ``group`` (``"scenario:<dimension>"``), ``kind`` = ``"scenario_spread"``, ``dimension``,
    ``label``, ``resolving_action`` (:data:`SCENARIO_SPREAD_ACTIONS`), ``spread`` and ``measure``,
    ``low`` / ``high`` (scenario id, name, cost, what distinguishes it), ``scenarios`` (the compared ids),
    ``n_alternatives``, ``currency`` and ``note``.  ``variance_share`` is ``None``: a spread between
    alternatives is not a share of one house's sampled variance.
    """
    outs = list(comparison.outcomes)
    if len(outs) < 2:
        return []
    use_p50 = all(o.cost_p50 is not None for o in outs)
    measure = "cost P50" if use_p50 else "deterministic construction cost"

    def value(o: ScenarioOutcome) -> float:
        return float(o.cost_p50 if use_p50 else o.construction_cost)

    dims = [_scenario_dims(o) for o in outs]
    entries: list[dict[str, Any]] = []
    for dim in _SPREAD_DIMS:
        classes: dict[tuple, list[int]] = {}
        for i, d in enumerate(dims):
            classes.setdefault(tuple(repr(d[k]) for k in _SPREAD_DIMS if k != dim), []).append(i)
        best: Optional[tuple[float, int, int, list[int]]] = None
        for members in classes.values():
            if len({repr(dims[i][dim]) for i in members}) < 2:
                continue
            vals = [(value(outs[i]), i) for i in members if value(outs[i]) == value(outs[i])]  # skip NaN
            if len(vals) < 2:
                continue
            lo, hi = min(vals), max(vals)
            if best is None or hi[0] - lo[0] > best[0]:
                best = (hi[0] - lo[0], lo[1], hi[1], members)
        if best is None:
            continue
        spread, i_lo, i_hi, members = best
        o_lo, o_hi = outs[i_lo], outs[i_hi]
        entries.append({
            "group": f"scenario:{dim}",
            "kind": "scenario_spread",
            "dimension": dim,
            "label": SCENARIO_SPREAD_LABELS[dim],
            "resolving_action": SCENARIO_SPREAD_ACTIONS[dim],
            "spread": float(spread),
            "measure": measure,
            "low": {"scenario_id": o_lo.scenario_id, "name": o_lo.name, "cost": value(o_lo),
                    "alternative": _describe(dim, o_lo, o_hi)},
            "high": {"scenario_id": o_hi.scenario_id, "name": o_hi.name, "cost": value(o_hi),
                     "alternative": _describe(dim, o_hi, o_lo)},
            "scenarios": [outs[i].scenario_id for i in members],
            "n_alternatives": len({repr(dims[i][dim]) for i in members}),
            "currency": currency,
            "variance_share": None,
            "note": ("Kept as separate build scenarios - not sampled or averaged into one house; resolving it "
                     f"selects one of them. Spread of the {measure} between scenarios that differ only in this "
                     "respect."),
        })
    entries.sort(key=lambda e: (-e["spread"], e["group"]))
    return entries


def combined_information_value(simulation: Optional[SimulationResult],
                               comparison: Optional[ScenarioComparison]) -> list[dict[str, Any]]:
    """Within-scenario groups of ``simulation`` and between-scenario spreads of ``comparison``, ranked together.

    UI / pipeline hook: the within-scenario entries are copies of ``simulation.information_value``
    (their own ``rank`` kept); the scenario entries come from :func:`scenario_spread_entries`.  Every
    entry gets ``impact`` (currency) and ``impact_measure``: for a within-scenario group the P10-P90 width
    it accounts for (the expected narrowing of the interval of one house), for a scenario dimension the
    spread between the alternatives (which house is being priced).  Both are amounts of money, so they
    are ranked together by ``impact`` (``combined_rank``), but they are different measures and the
    entries keep their ``kind`` (``within_scenario`` / ``scenario_spread``).
    """
    out: list[dict[str, Any]] = []
    cur = None
    if simulation is not None:
        for r in simulation.information_value:
            e = dict(r)
            e.setdefault("kind", "within_scenario")
            e["impact"] = float(e.get("p10_p90_width_accounted") or 0.0)
            e["impact_measure"] = "P10-P90 width accounted (within one house)"
            cur = cur or e.get("currency")
            out.append(e)
    if comparison is not None:
        for e in scenario_spread_entries(comparison, currency=cur):
            e["impact"] = float(e["spread"])
            e["impact_measure"] = f"spread of the {e['measure']} between build scenarios"
            out.append(e)
    out.sort(key=lambda e: (-e["impact"], e["group"]))
    for k, e in enumerate(out, 1):
        e["combined_rank"] = k
    return out
