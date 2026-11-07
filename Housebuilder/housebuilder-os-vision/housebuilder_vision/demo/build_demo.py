"""Build the bundled, fictional demonstration project "Aureom Demo House, Plot 7".

:func:`build_demo_project` assembles a complete :class:`Project` from the bundled
assets, using the logged pipeline functions (every step is in ``project.run_log``):

1. ingest ``demo_front_elevation.png`` as ``ImageKind.ELEVATION_DRAWING``, view FRONT
   (and, with ``include_side_view``, ``demo_left_elevation.png`` as LEFT);
2. analyse the images (bundled detection fixtures; offline, no optional dependency);
3. a :class:`ReferenceMeasurement` on the main facade feature - 9.60 m +/- 0.02 m,
   "confirmed frontage width from a fictional measured survey" - and calibrate;
4. generate the geometry hypotheses and select **H-A** (rectangular plan);
5. build the twin with the library's default assembly selection (masonry cavity wall,
   trench-fill foundation - all ASSUMED, never inferred from the brick-like appearance);
6. the illustrative assembly library, the FICTIONAL rate book from
   ``fictional_rates_gbp_2026.csv`` priced at the pinned :data:`DEMO_PRICING_DATE`
   (2026-11-01, for reproducibility), default :class:`CostParameters`;
7. production scenarios **PS-site** (site-built) and **PS-offsite** (off-site panelised
   timber frame with factory set-up, lines, learning, procurement tiers and a factory
   capacity step; per-house values from the timber-frame + brick variant estimate) -
   fictional, labelled assumptions;
8. build scenarios **S1** masonry H-A, **S2** timber frame + brick H-A, **S3** timber frame +
   timber cladding H-A, **S4** masonry H-B; default :class:`SimulationConfig`.

:func:`build_uncalibrated_demo_project` is the same without the reference measurement
(scale from labelled prior cues), used to show that missing dimensions keep their
uncertainty.

Why ``ELEVATION_DRAWING``: the image is a synthetic, orthographic, fronto-parallel
elevation drawn from known parameters (``make_demo_assets.py``).  ``RENDERING`` is a
*concept-reference* kind (architectural visualisation whose geometry may be
inconsistent); it would cap every basis at INFERRED and add concept warnings, which
would misdescribe a dimensionally consistent drawing.  Treating it as an elevation
drawing still never makes it a survey: its scale comes from the confirmed frontage.

Everything here is fictional demonstration data: the house, the survey, the prices,
the supplier quotes and the production economics.
"""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path
from typing import Optional, Union

from ..core.models import (
    BuildScenario,
    CostParameters,
    FeatureType,
    ImageAsset,
    ImageKind,
    ProductionScenario,
    Project,
    ReferenceMeasurement,
    SimulationConfig,
    StepCost,
    ViewDirection,
)
from ..core.settings import AssumptionLibrary, ProjectSettings

__all__ = [
    "DATA_DIR",
    "DEMO_PRICING_DATE",
    "FRONT_IMAGE",
    "LEFT_IMAGE",
    "DEMO_PROJECT_ID",
    "DEMO_PROJECT_NAME",
    "FRONTAGE_M",
    "FRONTAGE_TOLERANCE_M",
    "REFERENCE_DESCRIPTION",
    "build_demo_project",
    "build_uncalibrated_demo_project",
    "demo_build_scenarios",
    "demo_production_scenarios_for",
    "demo_registry",
    "OFFSITE_EXTERNAL_WALL",
    "main_facade_feature_id",
]

DATA_DIR = Path(__file__).resolve().parent / "data"
FRONT_IMAGE = DATA_DIR / "demo_front_elevation.png"
LEFT_IMAGE = DATA_DIR / "demo_left_elevation.png"
DEMO_PROJECT_ID = "aureom-demo-plot-7"
DEMO_PROJECT_NAME = "Aureom Demo House, Plot 7 (fictional)"
FRONTAGE_M = 9.60
FRONTAGE_TOLERANCE_M = 0.02
REFERENCE_DESCRIPTION = "confirmed frontage width from a fictional measured survey"
REFERENCE_SOURCE = "fictional measured survey (demo)"
SELECTED_HYPOTHESIS = "H-A"
FICTIONAL_NOTE = "FICTIONAL demonstration assumption - not calibrated against outturn data."
#: The demo is priced at a fixed date so its results are reproducible (a new project defaults to today).
DEMO_PRICING_DATE = date(2026, 11, 1)


def main_facade_feature_id(analysis, image_id: str) -> str:
    """Feature id of the main block's FACADE detection on ``image_id`` (the reference target)."""
    for a in analysis.analyses:
        if a.image_id != image_id:
            continue
        for f in a.features:
            if f.active and f.feature_type == FeatureType.FACADE and str(f.attributes.get("block", "")) == "main":
                return f.feature_id
    for fo in analysis.facades:
        if fo.image_id == image_id and fo.view == ViewDirection.FRONT and fo.block_hint == "main" and fo.feature_ids:
            return fo.feature_ids[0]
    raise ValueError("demo analysis has no main front facade feature")


def demo_registry():
    """Offline adapter registry for the demo: bundled fixtures + NumPy perspective + multi-view combiner.

    The optional transformers adapters are not registered (they may download model weights);
    the Claude VLM adapter is only added when ``HBV_ENABLE_VLM=1`` (an explicit opt-in to an
    external API).
    """
    from ..pipeline import registry_from_env

    return registry_from_env(enable_optional=False)


def demo_build_scenarios() -> list[BuildScenario]:
    """S1-S4: one coherent house each (hypothesis + assemblies); none is averaged with another."""
    return [
        BuildScenario(scenario_id="S1", name="S1 Masonry cavity wall, H-A",
                      description="Rectangular plan (H-A); masonry cavity external walls (brick / mineral wool / "
                                  "aircrete block / plaster); trench-fill foundation (assumed).",
                      hypothesis_id="H-A", assembly_overrides={"external_wall": "ew_masonry_cavity"},
                      production_scenario_id="PS-site"),
        BuildScenario(scenario_id="S2", name="S2 Timber frame + brick outer leaf, H-A",
                      description="Same geometry; timber frame inner leaf with a brick outer leaf - looks the same "
                                  "as S1 from outside (appearance does not establish structure).",
                      hypothesis_id="H-A", assembly_overrides={"external_wall": "ew_timber_frame_brick"},
                      production_scenario_id="PS-offsite"),
        BuildScenario(scenario_id="S3", name="S3 Timber frame + timber cladding, H-A",
                      description="Same geometry; timber frame with ventilated timber cladding (thinner wall, more "
                                  "internal area).",
                      hypothesis_id="H-A", assembly_overrides={"external_wall": "ew_timber_frame_clad"},
                      production_scenario_id="PS-offsite"),
        BuildScenario(scenario_id="S4", name="S4 Masonry cavity wall, H-B (L-shaped)",
                      description="Alternative hidden footprint H-B: shallower main block plus an assumed "
                                  "single-storey rear extension; masonry cavity walls.",
                      hypothesis_id="H-B", assembly_overrides={"external_wall": "ew_masonry_cavity"},
                      production_scenario_id="PS-site"),
    ]


#: External-wall assembly of the off-site panelised production scenario (PS-offsite).
OFFSITE_EXTERNAL_WALL = "ew_timber_frame_brick"
OFFSITE_SOURCE_DEFAULT = "the timber frame + brick outer leaf house (scenario S2 assemblies)"


def demo_production_scenarios_for(site_estimate, timber_frame_estimate, *,
                                  offsite_source: Optional[str] = None) -> list[ProductionScenario]:
    """PS-site (from the masonry estimate) and PS-offsite (from the timber-frame estimate).

    PS-site leaves per-house materials / labour / plant / logistics / site overhead to the estimate it
    is applied to (the selected masonry twin).  PS-offsite fixes them from ``timber_frame_estimate`` so
    its economics describe a panelised timber frame: materials with their order-level data (re-rounded
    for n houses), plant, site logistics with the factory share (35 %) of material deliveries, delivery
    charges and skips removed (:func:`~housebuilder_vision.costing.repeat_build.site_logistics_for`)
    and the time-related site overhead share of its preliminaries.  ``offsite_source`` describes where
    those values come from (default: the timber frame + brick house); pass the truth when the caller
    could not build that variant.  The "Second factory shift and QA team" step is a *factory* step
    (inside the factory-gate boundary).  All values are fictional assumptions.
    """
    from ..costing.repeat_build import _estimate_defaults, demo_production_scenarios, site_logistics_for

    site0 = demo_production_scenarios(site_estimate)[0]
    panel0 = demo_production_scenarios(timber_frame_estimate)[1]
    lt = timber_frame_estimate.layer_totals
    phi = float(panel0.factory_material_fraction or 0.0)
    source = offsite_source or OFFSITE_SOURCE_DEFAULT
    site = site0.model_copy(update={
        "scenario_id": "PS-site",
        "name": "PS-site: site-built (traditional) - FICTIONAL",
        "notes": "Site-built repeat of the selected house. " + FICTIONAL_NOTE + " " + site0.notes,
    })
    tf_time_prelims = _estimate_defaults(timber_frame_estimate)["time_related_prelims"]
    panel = panel0.model_copy(update={
        "scenario_id": "PS-offsite",
        "name": "PS-offsite: off-site panelised timber frame - FICTIONAL",
        "materials_per_house": float(lt.get("1_materials", 0.0)),
        "material_orders": [o.model_copy() for o in timber_frame_estimate.material_orders],
        "plant_per_house": float(lt.get("3_plant", 0.0)),
        "site_logistics_per_house": site_logistics_for(timber_frame_estimate, phi),
        "site_overhead_per_house": tf_time_prelims * panel0.site_overhead_share,
        "step_costs": [StepCost(name="Second factory shift and QA team", every_n_units=50, cost=55000.0,
                                starts_after_units=40, boundary="factory",
                                note="Factory capacity step beyond 40 units: " + FICTIONAL_NOTE)],
        "notes": (f"Per-house materials (with their order-level pack data), plant, site logistics (factory share "
                  f"{phi:.0%} of material deliveries and skips removed) and time-related site overhead "
                  f"({panel0.site_overhead_share:.0%} of its preliminaries) from {source}; factory set-up, lines, "
                  "learning, tiers and the factory capacity step are " + FICTIONAL_NOTE + " " + panel0.notes),
    })
    return [site, panel]


def _ingest(path: Path, view: ViewDirection, store_dir: Path) -> ImageAsset:
    from ..vision.ingest import ingest_path

    return ingest_path(path, kind=ImageKind.ELEVATION_DRAWING, view=view, store_dir=store_dir,
                       notes="Synthetic demo elevation (orthographic, drawn from fictional parameters); "
                             "kind ELEVATION_DRAWING because it is a dimensionally consistent drawing, not a "
                             "concept rendering.")


def build_demo_project(store_dir: Union[str, Path, None] = None, *, include_side_view: bool = False,
                       with_reference: bool = True, registry=None) -> Project:
    """The fictional demo project, analysed, calibrated and with a twin, rates and scenarios.

    ``store_dir`` receives the preserved original images (default: a new temporary directory).
    ``include_side_view`` adds the left elevation (multi-view depth and pitch).  ``with_reference``
    False gives the uncalibrated variant (see :func:`build_uncalibrated_demo_project`).
    """
    from .. import pipeline as P
    from ..costing.adapters import DEMO_RATES_PATH
    from ..costing.rates import load_rate_book_csv
    from ..quantities.library import default_library, default_selection
    from ..twin.builder import visual_finishes_from_analysis

    store = Path(store_dir) if store_dir is not None else Path(tempfile.mkdtemp(prefix="hbv-demo-"))
    store.mkdir(parents=True, exist_ok=True)
    settings = ProjectSettings(pricing_date=DEMO_PRICING_DATE)
    assumptions = AssumptionLibrary()
    project = Project(
        project_id=DEMO_PROJECT_ID if with_reference else f"{DEMO_PROJECT_ID}-uncalibrated",
        name=DEMO_PROJECT_NAME + ("" if with_reference else " - uncalibrated"),
        settings=settings, assumptions=assumptions,
        notes=("FICTIONAL demonstration project: synthetic elevation(s), fictional survey dimension, fictional "
               "prices and production economics. Not a real site, survey, design or price."))
    images = [_ingest(FRONT_IMAGE, ViewDirection.FRONT, store)]
    if include_side_view:
        images.append(_ingest(LEFT_IMAGE, ViewDirection.LEFT, store))
    project.images = images
    reg = registry if registry is not None else demo_registry()
    analysis = P.analyse_images(images, store_dir=store, registry=reg, assumptions=assumptions, run_log=project)
    project.analysis = analysis
    front_id = images[0].image_id
    reference: Optional[ReferenceMeasurement] = None
    if with_reference:
        reference = ReferenceMeasurement(
            image_id=front_id, feature_id=main_facade_feature_id(analysis, front_id), real_length=FRONTAGE_M,
            unit="m", tolerance=FRONTAGE_TOLERANCE_M, description=REFERENCE_DESCRIPTION, source=REFERENCE_SOURCE)
        project.references = [reference]
    calibration = P.calibrate_scale(analysis, reference, assumptions=assumptions, run_log=project)
    project.calibration = calibration
    hypotheses = P.generate_geometry_hypotheses(analysis, calibration, assumptions=assumptions, settings=settings,
                                                run_log=project)
    project.hypotheses = hypotheses
    hyp = next((h for h in hypotheses if h.hypothesis_id == SELECTED_HYPOTHESIS), hypotheses[0])
    project.selected_hypothesis_id = hyp.hypothesis_id
    library = default_library()
    project.library = library
    twin = P.build_parametric_twin(hyp, selection=default_selection(library), settings=settings,
                                   visual_finishes=visual_finishes_from_analysis(analysis), run_log=project)
    project.twin = twin
    project.rate_book = load_rate_book_csv(DEMO_RATES_PATH, name="Fictional demo rates GBP 2026 (FICTIONAL)")
    project.cost_parameters = CostParameters()

    # production scenarios need single-house estimates (masonry twin and its timber-frame variant)
    def quick_estimate(t):
        boq = P.calculate_quantities(t, library, assumptions=assumptions)
        sims = P.run_digital_simulations(t, boq, library, settings, cost_params=project.cost_parameters)
        return P.estimate_construction_cost(boq, project.rate_book, project.cost_parameters, settings=settings,
                                            programme_weeks=sims["programme"].duration_weeks,
                                            logistics=sims["logistics"], library=library)

    site_est = quick_estimate(twin)
    tf_twin = P.apply_construction_assemblies(twin, {"external_wall": OFFSITE_EXTERNAL_WALL}, library,
                                              actor="scenario:PS-offsite",
                                              reason="timber-frame variant for the off-site production scenario",
                                              run_log=project)
    tf_est = quick_estimate(tf_twin)
    project.production_scenarios = demo_production_scenarios_for(site_est, tf_est)
    project.build_scenarios = demo_build_scenarios()
    project.simulation_config = SimulationConfig()
    return project


def build_uncalibrated_demo_project(store_dir: Union[str, Path, None] = None, *, include_side_view: bool = False,
                                    registry=None) -> Project:
    """The demo project without the reference measurement (scale from labelled prior cues).

    Hypotheses then include H-C (deep plan / shallow pitch) and every scaled dimension keeps the
    wide prior-cue range - uncertainty is preserved, never hidden.  H-A is selected.
    """
    return build_demo_project(store_dir, include_side_view=include_side_view, with_reference=False,
                              registry=registry)
