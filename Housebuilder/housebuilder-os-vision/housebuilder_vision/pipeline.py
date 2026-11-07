"""End-to-end pipeline: the 11 engine functions with run logging, plus ``run_pipeline``.

The engine functions are thin wrappers around the module implementations with one
consistent calling convention (``library``, ``rate_book``, ``cost_params``,
``settings``, ``assumptions`` keywords) and one extra keyword, ``run_log``::

    analyse_images  -> calibrate_scale -> generate_geometry_hypotheses -> build_parametric_twin
    -> apply_construction_assemblies -> calculate_quantities -> estimate_construction_cost
    -> calculate_incremental_cost -> simulate_uncertainty -> compare_build_scenarios -> export_project

``run_log`` may be a list of :class:`RunRecord` or a :class:`Project` (its ``run_log``).
When given, every call appends a :class:`RunRecord` with the function name, the SHA-256
of the canonical JSON of its inputs and outputs (volatile timestamps removed, so equal
inputs give equal hashes), the seed (when the function is stochastic or seeded) and the
versions that affect the result: package version, model schema, Python / library
versions and the image-analysis adapters that produced output.

:func:`run_digital_simulations` runs programme -> logistics -> carbon -> heat loss for a
twin and its bill of quantities.  :func:`run_pipeline` runs the whole chain for a
:class:`Project` and returns a :class:`PipelineResult`.

Boundaries: the pipeline only orchestrates; every number keeps the provenance basis
given by the module that produced it.  Results are concept-stage estimates from a
conceptual reconstruction - not a survey, a design, a tender price or a compliance check.
Bundled demo prices are fictional.
"""

from __future__ import annotations

import os
import time
from datetime import date, datetime
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Union

from pydantic import BaseModel, ConfigDict, Field

from . import __version__
from .core.models import (
    SCHEMA_VERSION,
    AnalysisResult,
    AssemblyLibrary,
    AssemblySelection,
    BillOfQuantities,
    BuildingTwin,
    BuildScenario,
    CarbonResult,
    CostEstimate,
    CostParameters,
    DetectedFeature,
    GeometryHypothesis,
    GeometryMetrics,
    HeatLossResult,
    ImageAsset,
    LogisticsResult,
    ProductionScenario,
    ProgrammeResult,
    Project,
    RateBook,
    ReferenceMeasurement,
    RepeatBuildResult,
    RunRecord,
    ScaleCalibration,
    ScenarioComparison,
    SimulationConfig,
    SimulationResult,
    VisualFinish,
)
from .core.provenance import utcnow
from .core.settings import AssumptionLibrary, ProjectSettings

__all__ = [
    "ENGINE_FUNCTIONS",
    "PipelineResult",
    "RunLog",
    "analyse_images",
    "calibrate_scale",
    "generate_geometry_hypotheses",
    "build_parametric_twin",
    "apply_construction_assemblies",
    "calculate_quantities",
    "estimate_construction_cost",
    "calculate_incremental_cost",
    "simulate_uncertainty",
    "compare_build_scenarios",
    "export_project",
    "run_digital_simulations",
    "run_pipeline",
    "registry_from_env",
    "fingerprint",
    "engine_run_versions",
    "REPEAT_BOUNDARIES",
    "VLM_ENV",
]

#: The engine functions exposed with run logging (names are the public contract).
ENGINE_FUNCTIONS: tuple[str, ...] = (
    "analyse_images", "generate_geometry_hypotheses", "calibrate_scale", "build_parametric_twin",
    "apply_construction_assemblies", "calculate_quantities", "estimate_construction_cost",
    "calculate_incremental_cost", "simulate_uncertainty", "compare_build_scenarios", "export_project",
)
#: Repeat-build boundaries computed by :func:`run_pipeline` for every production scenario.
REPEAT_BOUNDARIES: tuple[str, ...] = ("factory_gate", "installed", "development")
#: Environment switch for the optional Claude vision-language adapter (also needs ANTHROPIC_API_KEY).
VLM_ENV = "HBV_ENABLE_VLM"

RunLog = Union[list, Project, None]
_VOLATILE_KEYS = frozenset({"created_at", "uploaded_at", "updated_at", "timestamp"})


# =============================================================================
# Fingerprints and run records
# =============================================================================
def _plain(obj: Any) -> Any:
    """JSON-ready view of ``obj`` without volatile timestamps (for reproducibility hashes)."""
    if isinstance(obj, BaseModel):
        obj = obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return {str(k): _plain(v) for k, v in obj.items() if str(k) not in _VOLATILE_KEYS}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    if isinstance(obj, (set, frozenset)):
        return sorted((_plain(v) for v in obj), key=repr)
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Path):
        return obj.as_posix()
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if hasattr(obj, "describe") and callable(obj.describe):
        try:
            return _plain(obj.describe())
        except Exception:  # pragma: no cover - defensive
            pass
    return f"<{type(obj).__name__}>"


def fingerprint(obj: Any) -> str:
    """SHA-256 of the canonical JSON of ``obj`` (sorted keys; timestamps removed)."""
    from .io.export import canonical_sha256

    return canonical_sha256(_plain(obj))


@lru_cache(maxsize=1)
def _base_versions() -> tuple[tuple[str, str], ...]:
    from .io.export import engine_versions

    v = dict(engine_versions())
    v["housebuilder_vision"] = __version__
    v["model_schema"] = SCHEMA_VERSION
    return tuple(sorted(v.items()))


def engine_run_versions(extra: Optional[Mapping[str, str]] = None) -> dict[str, str]:
    """Versions recorded in every :class:`RunRecord` (plus ``extra``, e.g. adapter versions)."""
    v = dict(_base_versions())
    for k, val in (extra or {}).items():
        v[str(k)[:120]] = str(val)[:120]
    return v


def _log(run_log: RunLog, function: str, *, inputs: Any, outputs: Any, seed: Optional[int] = None,
         versions: Optional[Mapping[str, str]] = None, note: str = "") -> Optional[RunRecord]:
    if run_log is None:
        return None
    target = run_log.run_log if isinstance(run_log, Project) else run_log
    rec = RunRecord(function=function, inputs_sha256=fingerprint(inputs), outputs_sha256=fingerprint(outputs),
                    seed=seed, versions=engine_run_versions(versions), note=note[:500])
    target.append(rec)
    return rec


def registry_from_env(fixture_dir: Optional[Union[str, Path]] = None, *, enable_optional: bool = True):
    """Default adapter registry; the Claude VLM adapter is enabled only when ``HBV_ENABLE_VLM=1``.

    The VLM adapter additionally needs the ``anthropic`` package and ``ANTHROPIC_API_KEY``; it
    sends the image to an external API, so it is opt-in.  ``enable_optional`` registers the
    optional OpenCV / transformers adapters (each still checks that its package is installed;
    transformers models may download weights on first use, so offline runs pass ``False``).
    """
    from .vision.adapters import default_registry

    return default_registry(fixture_dir=fixture_dir, enable_vlm=os.environ.get(VLM_ENV, "").strip() == "1",
                            enable_optional=enable_optional)


# =============================================================================
# The 11 engine functions (logged wrappers)
# =============================================================================
def analyse_images(images: Sequence[ImageAsset], *, store_dir: Union[str, Path, None], registry: Any = None,
                   settings: Union[ProjectSettings, AssumptionLibrary, None] = None,
                   manual_features: Optional[Mapping[str, Sequence[DetectedFeature]]] = None,
                   assumptions: Optional[AssumptionLibrary] = None, seed: int = 0,
                   run_log: RunLog = None) -> AnalysisResult:
    """Image evidence -> pixel-space facade observations (``vision.analysis.analyse_images``)."""
    from .vision.analysis import analyse_images as _impl

    out = _impl(images, store_dir=store_dir, registry=registry, settings=settings, manual_features=manual_features,
                assumptions=assumptions, seed=seed)
    _log(run_log, "analyse_images",
         inputs={"images": [{"image_id": a.image_id, "sha256": a.sha256, "kind": a.kind, "view": a.view}
                            for a in images],
                 "manual_features": manual_features, "assumptions": assumptions, "seed": seed,
                 "registry": registry.describe() if registry is not None and hasattr(registry, "describe")
                 else "default_registry"},
         outputs=out, seed=seed, versions={f"adapter:{k}": v for k, v in out.model_versions.items()},
         note=f"{len(out.images)} image(s), {len(out.facades)} facade observation(s), {len(out.warnings)} warning(s)")
    return out


def calibrate_scale(analysis: AnalysisResult, reference: Optional[ReferenceMeasurement] = None, *,
                    assumptions: Optional[AssumptionLibrary] = None, run_log: RunLog = None) -> ScaleCalibration:
    """Pixels -> metres with provenance (``twin.calibration.calibrate_scale``)."""
    from .twin.calibration import calibrate_scale as _impl

    out = _impl(analysis, reference, assumptions=assumptions)
    _log(run_log, "calibrate_scale", inputs={"analysis": analysis, "reference": reference,
                                             "assumptions": assumptions}, outputs=out,
         note=f"method={out.method}, basis={out.metres_per_pixel.basis.value}")
    return out


def generate_geometry_hypotheses(analysis: AnalysisResult, calibration: ScaleCalibration, *,
                                 assumptions: Optional[AssumptionLibrary] = None,
                                 settings: Optional[ProjectSettings] = None,
                                 run_log: RunLog = None) -> list[GeometryHypothesis]:
    """Competing hidden-footprint hypotheses (``twin.hypotheses.generate_geometry_hypotheses``)."""
    from .twin.hypotheses import generate_geometry_hypotheses as _impl

    out = _impl(analysis, calibration, assumptions=assumptions, settings=settings)
    _log(run_log, "generate_geometry_hypotheses", inputs={"analysis": analysis, "calibration": calibration,
                                                          "assumptions": assumptions, "settings": settings},
         outputs=out, note=", ".join(h.hypothesis_id for h in out))
    return out


def build_parametric_twin(hypothesis: GeometryHypothesis, *, selection: AssemblySelection,
                          settings: Optional[ProjectSettings] = None,
                          visual_finishes: Optional[Sequence[VisualFinish]] = None, twin_id: Optional[str] = None,
                          run_log: RunLog = None) -> BuildingTwin:
    """Editable parametric twin from a hypothesis (``twin.builder.build_parametric_twin``)."""
    from .twin.builder import build_parametric_twin as _impl

    out = _impl(hypothesis, selection=selection, settings=settings, visual_finishes=visual_finishes, twin_id=twin_id)
    _log(run_log, "build_parametric_twin", inputs={"hypothesis": hypothesis, "selection": selection,
                                                   "settings": settings, "visual_finishes": visual_finishes,
                                                   "twin_id": twin_id},
         outputs=out, note=f"{out.twin_id} v{out.version}: {len(out.blocks)} block(s), {len(out.openings)} opening(s)")
    return out


def apply_construction_assemblies(twin: BuildingTwin, selection_changes: dict[str, str], library: AssemblyLibrary,
                                  *, actor: str = "user", block_id: Optional[str] = None, reason: str = "",
                                  run_log: RunLog = None) -> BuildingTwin:
    """Change assembly selections (``quantities.takeoff.apply_construction_assemblies``)."""
    from .quantities.takeoff import apply_construction_assemblies as _impl

    out = _impl(twin, selection_changes, library, actor=actor, block_id=block_id, reason=reason)
    _log(run_log, "apply_construction_assemblies",
         inputs={"twin": twin, "selection_changes": selection_changes, "library": library.name,
                 "library_version": library.version, "actor": actor, "block_id": block_id, "reason": reason},
         outputs=out, note=f"actor={actor}; {', '.join(f'{k}={v}' for k, v in selection_changes.items())}"[:500])
    return out


def calculate_quantities(twin: BuildingTwin, library: AssemblyLibrary, *, metrics: Optional[GeometryMetrics] = None,
                         assumptions: Any = None, run_log: RunLog = None) -> BillOfQuantities:
    """Traceable bill of quantities (``quantities.takeoff.calculate_quantities``)."""
    from .quantities.takeoff import calculate_quantities as _impl

    out = _impl(twin, library, metrics=metrics, assumptions=assumptions)
    _log(run_log, "calculate_quantities", inputs={"twin": twin, "library": library, "metrics": metrics,
                                                  "assumptions": assumptions},
         outputs=out, note=f"{len(out.lines)} line(s), {len(out.unresolved)} unresolved")
    return out


def estimate_construction_cost(boq: BillOfQuantities, rate_book: RateBook, cost_params: CostParameters, *,
                               settings: ProjectSettings, programme_weeks: Optional[float] = None,
                               logistics: Optional[LogisticsResult] = None,
                               library: Optional[AssemblyLibrary] = None, run_log: RunLog = None) -> CostEstimate:
    """Nine-layer cost estimate with cost boundaries (``costing.engine.estimate_construction_cost``)."""
    from .costing.engine import estimate_construction_cost as _impl

    out = _impl(boq, rate_book, cost_params, settings=settings, programme_weeks=programme_weeks,
                logistics=logistics, library=library)
    _log(run_log, "estimate_construction_cost",
         inputs={"boq": boq, "rate_book": rate_book, "cost_params": cost_params, "settings": settings,
                 "programme_weeks": programme_weeks, "logistics": logistics,
                 "library": library.name if library is not None else None},
         outputs=out, versions={"rate_book": rate_book.name},
         note=f"{len(out.lines)} cost line(s), {len(out.unresolved_items)} unresolved")
    return out


def calculate_incremental_cost(estimate: CostEstimate, scenario: ProductionScenario, *, boundary: str = "installed",
                               max_n: int = 101, comparison_ns: Sequence[int] = (1, 10, 25, 50, 100),
                               cost_params: Optional[CostParameters] = None,
                               run_log: RunLog = None) -> RepeatBuildResult:
    """C(n), average and incremental repeat-build cost (``costing.repeat_build.calculate_incremental_cost``)."""
    from .costing.repeat_build import calculate_incremental_cost as _impl

    out = _impl(estimate, scenario, boundary=boundary, max_n=max_n, comparison_ns=comparison_ns,
                cost_params=cost_params)
    _log(run_log, "calculate_incremental_cost",
         inputs={"estimate": estimate, "scenario": scenario, "boundary": boundary, "max_n": max_n,
                 "comparison_ns": list(comparison_ns), "cost_params": cost_params},
         outputs=out, note=f"{scenario.scenario_id} / {boundary}")
    return out


def simulate_uncertainty(twin: BuildingTwin, library: AssemblyLibrary, rate_book: RateBook,
                         cost_params: CostParameters, settings: ProjectSettings, *,
                         config: Optional[SimulationConfig] = None, calibration: Optional[ScaleCalibration] = None,
                         assumptions: Any = None, scenario_id: Optional[str] = None,
                         crew_sizes: Optional[Mapping[str, float]] = None, run_log: RunLog = None) -> SimulationResult:
    """Uncertainty simulation of one coherent house (``simulation.uncertainty.simulate_uncertainty``)."""
    from .simulation.uncertainty import simulate_uncertainty as _impl

    cfg = config if config is not None else SimulationConfig()
    out = _impl(twin, library, rate_book, cost_params, settings, config=cfg, calibration=calibration,
                assumptions=assumptions, scenario_id=scenario_id, crew_sizes=crew_sizes)
    _log(run_log, "simulate_uncertainty",
         inputs={"twin": twin, "library": library, "rate_book": rate_book, "cost_params": cost_params,
                 "settings": settings, "config": cfg, "calibration": calibration, "assumptions": assumptions,
                 "scenario_id": scenario_id, "crew_sizes": crew_sizes},
         outputs={k: v for k, v in out.model_dump(mode="json").items() if k != "notes"},
         seed=cfg.seed, versions={"sampler": f"{cfg.method}"},
         note=f"n={out.n_samples}, {len(out.inputs)} input(s), method={cfg.method}")
    return out


def compare_build_scenarios(base_twin: BuildingTwin, hypotheses: Sequence[GeometryHypothesis],
                            scenarios: Sequence[BuildScenario], library: AssemblyLibrary, rate_book: RateBook,
                            cost_params: CostParameters, settings: ProjectSettings, *, simulate: bool = False,
                            config: Optional[SimulationConfig] = None,
                            calibration: Optional[ScaleCalibration] = None, assumptions: Any = None,
                            crew_sizes: Optional[Mapping[str, float]] = None,
                            run_log: RunLog = None) -> ScenarioComparison:
    """Side-by-side coherent build scenarios (``simulation.scenarios.compare_build_scenarios``)."""
    from .simulation.scenarios import DEFAULT_SCENARIO_SAMPLES
    from .simulation.scenarios import compare_build_scenarios as _impl

    cfg = config if config is not None else (SimulationConfig(n_samples=DEFAULT_SCENARIO_SAMPLES) if simulate
                                             else None)
    out = _impl(base_twin, hypotheses, scenarios, library, rate_book, cost_params, settings, simulate=simulate,
                config=cfg, calibration=calibration, assumptions=assumptions, crew_sizes=crew_sizes)
    _log(run_log, "compare_build_scenarios",
         inputs={"base_twin": base_twin, "hypotheses": hypotheses, "scenarios": scenarios, "library": library,
                 "rate_book": rate_book, "cost_params": cost_params, "settings": settings, "simulate": simulate,
                 "config": cfg, "calibration": calibration, "assumptions": assumptions},
         outputs=out, seed=cfg.seed if (simulate and cfg is not None) else None,
         note=f"{len(out.outcomes)} scenario(s), simulate={simulate}")
    return out


def export_project(project: Project, out_dir: Union[str, Path], *, boq: Optional[BillOfQuantities] = None,
                   estimate: Optional[CostEstimate] = None, simulation: Optional[SimulationResult] = None,
                   repeat: Union[RepeatBuildResult, Sequence[RepeatBuildResult], None] = None,
                   comparison: Optional[ScenarioComparison] = None,
                   formats: Union[str, Sequence[str]] = ("json", "glb", "csv", "ifc"),
                   library: Optional[AssemblyLibrary] = None, rate_book: Optional[RateBook] = None,
                   run_log: RunLog = None):
    """JSON / GLB / CSV / optional IFC export with a sha256 manifest (``io.export.export_project``)."""
    from .io.export import export_project as _impl

    manifest = _impl(project, out_dir, boq=boq, estimate=estimate, simulation=simulation, repeat=repeat,
                     comparison=comparison, formats=formats, library=library, rate_book=rate_book)
    _log(run_log, "export_project",
         inputs={"project": project, "boq": boq, "estimate": estimate, "simulation": simulation, "repeat": repeat,
                 "comparison": comparison, "formats": formats},
         outputs={"files": [{"path": f.path, "sha256": f.sha256} for f in manifest.files],
                  "warnings": manifest.warnings},
         versions={"ifcopenshell": manifest.ifc.ifcopenshell_version} if manifest.ifc is not None
         and getattr(manifest.ifc, "ifcopenshell_version", None) else None,
         note=f"{len(manifest.files)} file(s): {', '.join(sorted({f.format for f in manifest.files}))}")
    return manifest


# =============================================================================
# Digital simulations
# =============================================================================
def run_digital_simulations(twin: BuildingTwin, boq: BillOfQuantities, library: AssemblyLibrary,
                            settings: ProjectSettings, *, cost_params: Optional[CostParameters] = None,
                            crew_sizes: Optional[Mapping[str, float]] = None,
                            lead_time_weeks: Optional[Mapping[str, float]] = None,
                            run_log: RunLog = None) -> dict[str, Any]:
    """Programme -> logistics -> embodied carbon -> heat loss for ``twin`` and its ``boq``.

    Returns ``{"programme": ProgrammeResult, "logistics": LogisticsResult, "carbon": CarbonResult,
    "heat_loss": HeatLossResult}``.  Waste bulking and skip volume follow ``cost_params`` so the
    logistics skip count matches the cost engine.  Heat loss uses ``boq.geometry`` (the metrics of
    this twin with its selected wall thicknesses).
    """
    from .simulation.carbon import embodied_carbon
    from .simulation.logistics import plan_deliveries
    from .simulation.programme import build_programme
    from .simulation.thermal import heat_loss

    cp = cost_params or CostParameters()
    prog = build_programme(boq, library, crew_sizes=crew_sizes, lead_time_weeks=lead_time_weeks)
    _log(run_log, "build_programme", inputs={"boq": boq, "library": library, "crew_sizes": crew_sizes,
                                             "lead_time_weeks": lead_time_weeks},
         outputs=prog, note=f"{prog.duration_weeks:.1f} weeks")
    logi = plan_deliveries(boq, library, prog, lead_time_weeks=lead_time_weeks,
                           waste_bulking_factor=cp.waste_bulking_factor, skip_volume_m3=cp.skip_volume_m3)
    _log(run_log, "plan_deliveries", inputs={"boq": boq, "library": library, "programme": prog,
                                             "waste_bulking_factor": cp.waste_bulking_factor,
                                             "skip_volume_m3": cp.skip_volume_m3},
         outputs=logi, note=f"{logi.total_loads} load(s), {logi.skips} skip(s)")
    carbon = embodied_carbon(boq, library, logistics=logi)
    _log(run_log, "embodied_carbon", inputs={"boq": boq, "library": library, "logistics": logi}, outputs=carbon,
         note=f"{carbon.total_kgco2e:,.0f} kgCO2e (illustrative factors)")
    heat = heat_loss(twin, boq.geometry, library, settings)
    _log(run_log, "heat_loss", inputs={"twin": twin, "metrics": boq.geometry, "library": library,
                                       "settings": settings},
         outputs=heat, note=f"HLC {heat.heat_loss_coefficient_w_k:.1f} W/K (simplified, not SAP)")
    return {"programme": prog, "logistics": logi, "carbon": carbon, "heat_loss": heat}


# =============================================================================
# Pipeline result and orchestration
# =============================================================================
class PipelineResult(BaseModel):
    """Everything :func:`run_pipeline` produced for one project run."""

    model_config = ConfigDict(extra="forbid")

    project_id: str
    analysis: Optional[AnalysisResult] = None
    calibration: Optional[ScaleCalibration] = None
    hypotheses: list[GeometryHypothesis] = Field(default_factory=list)
    selected_hypothesis_id: Optional[str] = None
    twin: BuildingTwin
    boq: BillOfQuantities
    programme: ProgrammeResult
    logistics: LogisticsResult
    carbon: CarbonResult
    heat_loss: HeatLossResult
    estimate: CostEstimate
    simulation: Optional[SimulationResult] = None
    #: {production scenario id: {boundary: RepeatBuildResult}}
    repeat_build: dict[str, dict[str, RepeatBuildResult]] = Field(default_factory=dict)
    comparison: Optional[ScenarioComparison] = None
    #: Run records appended by this run (also in ``project.run_log``).
    run_records: list[RunRecord] = Field(default_factory=list)
    timings_s: dict[str, float] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def repeat_results(self) -> list[RepeatBuildResult]:
        """All repeat-build results as a flat list (scenario order, boundary order)."""
        return [r for by_b in self.repeat_build.values() for r in by_b.values()]


def _library_for(project: Project, notes: list[str]) -> AssemblyLibrary:
    if project.library.assemblies:
        return project.library
    from .quantities.library import default_library

    notes.append("Project library was empty: the bundled generic (illustrative) assembly library is used and stored "
                 "on the project.")
    lib = default_library()
    project.library = lib
    return lib


def run_pipeline(project: Project, *, store_dir: Union[str, Path, None], simulate: bool = True, n_samples: int = 500,
                 registry: Any = None, scenario_samples: Optional[int] = None,
                 crew_sizes: Optional[Mapping[str, float]] = None) -> PipelineResult:
    """Run the full chain for ``project`` and return a :class:`PipelineResult`.

    Steps: analyse ``project.images`` (or reuse ``project.analysis`` when there are no images) ->
    calibrate with the first ``project.references`` entry (prior cues when none) -> hypotheses ->
    select ``project.selected_hypothesis_id`` (else the first) -> twin -> quantities -> programme,
    logistics, carbon, heat loss -> cost estimate (programme weeks + logistics) -> uncertainty
    simulation (``n_samples``, ``project.simulation_config`` otherwise) -> repeat-build results for
    every production scenario and boundary -> build-scenario comparison (``scenario_samples``
    each, default ``min(n_samples, 200)``, when ``simulate``).

    The twin: an existing ``project.twin`` built from the selected hypothesis is kept (it may carry
    user edits); otherwise a new twin is built from the hypothesis with the existing twin's assembly
    selection (else the library defaults, all ASSUMED).  ``project`` is updated in place
    (analysis, calibration, hypotheses, selected hypothesis, twin, library if empty, run log,
    ``updated_at``); every engine call appends a :class:`RunRecord`.
    """
    from .quantities.library import default_selection
    from .twin.builder import visual_finishes_from_analysis

    t_all = time.perf_counter()
    timings: dict[str, float] = {}
    notes: list[str] = []
    warnings: list[str] = []
    start = len(project.run_log)
    log = project

    def lap(name: str, t0: float) -> None:
        timings[name] = round(time.perf_counter() - t0, 4)

    settings, A = project.settings, project.assumptions
    # ---- evidence
    t0 = time.perf_counter()
    if project.images:
        reg = registry if registry is not None else registry_from_env()
        analysis = analyse_images(project.images, store_dir=store_dir, registry=reg, assumptions=A, run_log=log)
    elif project.analysis is not None:
        analysis = project.analysis
        notes.append("No images on the project: the stored analysis was reused.")
    else:
        raise ValueError("project has no images and no analysis; add at least one front elevation image")
    lap("analyse_images", t0)
    warnings += [f"analysis: {w}" for w in analysis.warnings]

    t0 = time.perf_counter()
    reference = project.references[0] if project.references else None
    if len(project.references) > 1:
        notes.append(f"{len(project.references)} reference measurements on the project; the first is used for "
                     "calibration, the others are kept for cross-checking.")
    calibration = calibrate_scale(analysis, reference, assumptions=A, run_log=log)
    hypotheses = generate_geometry_hypotheses(analysis, calibration, assumptions=A, settings=settings, run_log=log)
    lap("calibrate_and_hypotheses", t0)
    ids = [h.hypothesis_id for h in hypotheses]
    selected_id = project.selected_hypothesis_id if project.selected_hypothesis_id in ids else ids[0]
    if project.selected_hypothesis_id and project.selected_hypothesis_id not in ids:
        warnings.append(f"Selected hypothesis '{project.selected_hypothesis_id}' is no longer generated; "
                        f"'{selected_id}' is used.")
    hyp = hypotheses[ids.index(selected_id)]

    # ---- twin
    t0 = time.perf_counter()
    library = _library_for(project, notes)
    if project.twin is not None and project.twin.source_hypothesis_id == selected_id:
        twin = project.twin
        notes.append(f"Existing twin '{twin.twin_id}' v{twin.version} (from {selected_id}) kept with its "
                     f"{len(twin.edit_log)} edit(s); clear project.twin to rebuild it from the hypothesis.")
    else:
        selection = project.twin.assemblies if project.twin is not None else default_selection(library)
        twin = build_parametric_twin(hyp, selection=selection, settings=settings,
                                     visual_finishes=visual_finishes_from_analysis(analysis), run_log=log)
    lap("twin", t0)

    # ---- quantities, simulations, cost
    t0 = time.perf_counter()
    boq = calculate_quantities(twin, library, assumptions=A, run_log=log)
    lap("calculate_quantities", t0)
    t0 = time.perf_counter()
    sims = run_digital_simulations(twin, boq, library, settings, cost_params=project.cost_parameters,
                                   crew_sizes=crew_sizes, run_log=log)
    lap("digital_simulations", t0)
    t0 = time.perf_counter()
    estimate = estimate_construction_cost(boq, project.rate_book, project.cost_parameters, settings=settings,
                                          programme_weeks=sims["programme"].duration_weeks,
                                          logistics=sims["logistics"], library=library, run_log=log)
    lap("estimate_construction_cost", t0)
    if not project.rate_book.rates:
        warnings.append("The project rate book is empty: every cost item is listed as a missing rate.")

    # ---- uncertainty
    simulation: Optional[SimulationResult] = None
    if simulate:
        t0 = time.perf_counter()
        cfg = project.simulation_config.model_copy(update={"n_samples": int(n_samples)})
        simulation = simulate_uncertainty(twin, library, project.rate_book, project.cost_parameters, settings,
                                          config=cfg, calibration=calibration, assumptions=A,
                                          scenario_id=f"{twin.twin_id}", crew_sizes=crew_sizes, run_log=log)
        lap("simulate_uncertainty", t0)

    # ---- repeat build
    t0 = time.perf_counter()
    repeat: dict[str, dict[str, RepeatBuildResult]] = {}
    for ps in project.production_scenarios:
        repeat[ps.scenario_id] = {
            b: calculate_incremental_cost(estimate, ps, boundary=b, cost_params=project.cost_parameters, run_log=log)
            for b in REPEAT_BOUNDARIES}
    lap("repeat_build", t0)

    # ---- build scenarios
    comparison: Optional[ScenarioComparison] = None
    if project.build_scenarios:
        t0 = time.perf_counter()
        ns = scenario_samples if scenario_samples is not None else min(int(n_samples), 200)
        cfg_s = project.simulation_config.model_copy(update={"n_samples": max(20, int(ns))}) if simulate else None
        comparison = compare_build_scenarios(twin, hypotheses, project.build_scenarios, library, project.rate_book,
                                             project.cost_parameters, settings, simulate=simulate, config=cfg_s,
                                             calibration=calibration, assumptions=A, crew_sizes=crew_sizes,
                                             run_log=log)
        lap("compare_build_scenarios", t0)

    # ---- update the project
    project.analysis = analysis
    project.calibration = calibration
    project.hypotheses = hypotheses
    project.selected_hypothesis_id = selected_id
    project.twin = twin
    project.updated_at = utcnow()
    timings["total"] = round(time.perf_counter() - t_all, 4)
    if estimate.unresolved_items:
        warnings.append(f"Cost estimate has {len(estimate.unresolved_items)} unresolved item(s) (not priced as zero).")
    return PipelineResult(
        project_id=project.project_id, analysis=analysis, calibration=calibration, hypotheses=hypotheses,
        selected_hypothesis_id=selected_id, twin=twin, boq=boq, programme=sims["programme"],
        logistics=sims["logistics"], carbon=sims["carbon"], heat_loss=sims["heat_loss"], estimate=estimate,
        simulation=simulation, repeat_build=repeat, comparison=comparison,
        run_records=list(project.run_log[start:]), timings_s=timings, notes=notes, warnings=warnings)
