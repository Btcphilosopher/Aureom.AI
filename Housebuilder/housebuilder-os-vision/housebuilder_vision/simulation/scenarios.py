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
    cost   = estimate_construction_cost(boq, rate book [x rate_multiplier],
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
* ``rate_multiplier`` scales every rate of the rate book for that scenario (a labelled
  price-level assumption).

Boundaries: indicative concept-stage comparison.  Heat loss is a simplified
steady-state coefficient (not SAP/SBEM/PHPP), carbon uses illustrative factors, the
programme is an indicative critical path; nothing here is a compliance, structural or
energy-performance claim.  Bundled demo prices are fictional.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Sequence, Union

from ..core.models import (
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
from ..costing.engine import estimate_construction_cost
from ..quantities.measures import TakeoffAssumptions
from ..quantities.takeoff import apply_construction_assemblies, calculate_quantities, wall_thicknesses
from .carbon import embodied_carbon
from .logistics import plan_deliveries
from .programme import build_programme
from .thermal import heat_loss
from .uncertainty import COST_METRIC, simulate_uncertainty

__all__ = ["ScenarioEvaluation", "evaluate_build_scenario", "compare_build_scenarios", "scale_rate_book",
           "DEFAULT_SCENARIO_SAMPLES", "COMPARISON_NOTES"]

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


def scale_rate_book(rate_book: RateBook, multiplier: float) -> RateBook:
    """A copy of ``rate_book`` with every rate value multiplied (labelled scenario price level)."""
    m = float(multiplier)
    if m == 1.0:
        return rate_book
    if not (m > 0.0) or m != m:
        raise ValueError(f"rate_multiplier must be a positive number, got {multiplier!r}")
    return rate_book.model_copy(update={
        "name": f"{rate_book.name} x{m:g} (scenario price level)",
        "rates": [r.model_copy(update={"value": r.value * m}) for r in rate_book.rates],
        "notes": (rate_book.notes + " " if rate_book.notes else "") + f"All rates x{m:g} for a build scenario.",
    })


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
    boq = calculate_quantities(twin, library, assumptions=assumptions)
    prog = build_programme(boq, library, crew_sizes=crew_sizes)
    logi = plan_deliveries(boq, library, prog, waste_bulking_factor=cost_params.waste_bulking_factor,
                           skip_volume_m3=cost_params.skip_volume_m3)
    est = estimate_construction_cost(boq, book, cost_params, settings=settings, programme_weeks=prog.duration_weeks,
                                     logistics=logi, library=library)
    carbon = embodied_carbon(boq, library, logistics=logi)
    heat = heat_loss(twin, boq.geometry, library, settings)
    sim: Optional[SimulationResult] = None
    if simulate:
        cfg = config if config is not None else SimulationConfig(n_samples=DEFAULT_SCENARIO_SAMPLES)
        sim = simulate_uncertainty(twin, library, book, cost_params, settings, config=cfg, calibration=calibration,
                                   assumptions=assumptions, scenario_id=scenario.scenario_id, crew_sizes=crew_sizes)
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
        key.append(f"All rates x{scenario.rate_multiplier:g} (scenario price-level assumption).")
    if scenario.production_scenario_id:
        key.append(f"Linked production scenario: {scenario.production_scenario_id} (repeat-build economics are "
                   "reported separately).")
    key.append(f"Programme {prog.duration_weeks:.1f} weeks (indicative critical path) drives time-related "
               "preliminaries.")
    if est.unresolved_items:
        key.append(f"{len(est.unresolved_items)} unresolved cost item(s) are excluded from the totals.")
    if sim is not None:
        key.append(f"P10/P50/P90 from {sim.n_samples} samples of this scenario only (assumed scenario uncertainty).")
    key.extend(notes)
    outcome = ScenarioOutcome(
        scenario_id=scenario.scenario_id, name=scenario.name, hypothesis_id=twin.source_hypothesis_id,
        gia_m2=gia, external_wall_thickness_m=float(t_ext), construction_cost=construction,
        contract_sum=bnd.get("contract_sum", float("nan")),
        cost_per_m2_gia=construction / gia if gia > 0 else float("nan"), labour_hours=labour,
        programme_weeks=float(prog.duration_weeks), embodied_carbon_kgco2e=float(carbon.total_kgco2e),
        heat_loss_coefficient_w_k=float(heat.heat_loss_coefficient_w_k), peak_heat_load_kw=float(heat.peak_heat_load_kw),
        cost_p10=_p(sim, "p10"), cost_p50=_p(sim, "p50"), cost_p90=_p(sim, "p90"), key_assumptions=key)
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
    ``config`` (default ``SimulationConfig(n_samples=200)``, same seed for every scenario).
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
                     "statistically calibrated).")
    if any(r.source_type.value == "fictional_demo" for r in rate_book.rates):
        notes.append("Rate book contains FICTIONAL demo prices - comparisons illustrate the method, not market costs.")
    return ScenarioComparison(outcomes=[e.outcome for e in evals], notes=notes)
