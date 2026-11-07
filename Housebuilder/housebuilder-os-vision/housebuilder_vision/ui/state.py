"""UI session state and orchestration of the engine (no layout code here).

The :class:`Workspace` held in ``st.session_state`` wraps one :class:`Project` (the source of
truth for images, references, analysis, calibration, hypotheses, the twin, library, rate book,
commercial parameters, scenarios and the run log) plus UI-only state: the user's manual
annotations / feature rejections per image, the fingerprint of the hypothesis the twin was built
from, adapter opt-ins, the latest simulation / scenario comparison / export and flash messages.

Flow (each step a function below, called from widget callbacks or buttons):

``ingest_uploads`` -> ``refresh_evidence`` (analyse -> calibrate -> hypotheses -> ``sync_twin``)
-> ``build_twin`` / ``edit_twin`` / ``set_assembly`` -> :func:`evaluate` (quantities ->
programme / logistics / carbon / heat loss -> cost estimate) -> ``run_simulation`` /
``compare_scenarios`` / ``repeat_results`` -> ``export_bundle``.

Caching: heavy work goes through ``st.cache_data`` functions whose cache key is an explicit
SHA-256 string (``twin_hash`` + fingerprints of the library, rate book, commercial parameters,
settings and assumptions); the model objects are passed as underscore-prefixed (unhashed)
arguments.  Explicit user steps (analysis, calibration, hypotheses, twin build, assembly
changes, simulation, comparison, export) append :class:`RunRecord` s to ``project.run_log``;
cached recalculations of quantities and costs do not (they are reproducible from the logged
inputs).

Boundaries: this module never alters engine results, never upgrades a basis and never treats
a missing rate or quantity as zero.  Uploaded files are handed to ``vision.ingest`` (size,
format and decode validation); annotation rows and rate-book edits are validated with Pydantic
before use.  Optional adapters (Claude VLM, OpenCV / transformers) are opt-in.
"""

from __future__ import annotations

import hashlib
import io
import math
import os
import re
import shutil
import tempfile
import zipfile
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

import streamlit as st
from pydantic import ValidationError

from .. import pipeline as P
from ..core.models import (
    AnalysisResult,
    BillOfQuantities,
    BuildingTwin,
    CarbonResult,
    CostEstimate,
    CostParameters,
    DetectedFeature,
    FeatureType,
    GeometryHypothesis,
    HeatLossResult,
    ImageAsset,
    ImageKind,
    LogisticsResult,
    ProductionScenario,
    ProgrammeResult,
    Project,
    RateBook,
    ReferenceMeasurement,
    RepeatBuildResult,
    RunRecord,
    ScenarioComparison,
    SimulationConfig,
    SimulationResult,
    TwinEdit,
    ViewDirection,
)
from ..core.provenance import Basis, EditRecord
from ..core.settings import ProjectSettings

SESSION_KEY = "hbv_workspace"
DATA_DIR_ENV = "HBV_DATA_DIR"
UI_REJECT_REASON = "rejected by the user in the Images view"
UI_ANNOTATION_METHOD = "manual-annotation"
REPEAT_UI_BOUNDARIES = ("factory_gate", "installed")
EXPORT_MIME = {"json": "application/json", "glb": "model/gltf-binary", "csv": "text/csv", "ifc": "application/x-step",
               "txt": "text/plain"}

#: Feature types offered in the manual annotation editor (lines use ``line``, the rest ``bbox``).
ANNOTATION_TYPES: tuple[str, ...] = (
    "facade", "roof", "window", "door", "garage_door", "ground_line", "eaves_line", "ridge_line", "storey_line",
    "chimney", "garage", "extension", "finish_region", "dimension", "other")
LINE_TYPES = {"ground_line", "eaves_line", "ridge_line", "storey_line", "dimension"}
ROOF_FORMS = ("", "gable", "hip", "flat", "monopitch")
_ID_SAFE = re.compile(r"[^A-Za-z0-9_.\-]+")
_CTRL = re.compile(r"[\x00-\x1f\x7f]")

#: UI labels for image kinds (spec wording) -> engine enum.
KIND_LABELS: dict[str, ImageKind] = {
    "Photo": ImageKind.PHOTOGRAPH,
    "Rendering": ImageKind.RENDERING,
    "AI concept": ImageKind.AI_CONCEPT,
    "Sketch": ImageKind.SKETCH,
    "Floor plan": ImageKind.FLOOR_PLAN,
    "Elevation drawing": ImageKind.ELEVATION_DRAWING,
    "Unknown": ImageKind.UNKNOWN,
}
VIEW_LABELS: dict[str, ViewDirection] = {
    "Front": ViewDirection.FRONT, "Rear": ViewDirection.REAR, "Left": ViewDirection.LEFT,
    "Right": ViewDirection.RIGHT, "Front-left oblique": ViewDirection.FRONT_LEFT_OBLIQUE,
    "Front-right oblique": ViewDirection.FRONT_RIGHT_OBLIQUE, "Plan": ViewDirection.PLAN,
    "Aerial": ViewDirection.AERIAL, "Unknown": ViewDirection.UNKNOWN,
}


def kind_label(kind: ImageKind) -> str:
    return next((k for k, v in KIND_LABELS.items() if v == kind), kind.value)


def view_label(view: ViewDirection) -> str:
    return next((k for k, v in VIEW_LABELS.items() if v == view), view.value)


# =============================================================================
# Workspace
# =============================================================================
@dataclass
class Evaluation:
    """Deterministic results for one twin + inputs (cached by ``key``)."""

    key: str
    boq: BillOfQuantities
    programme: ProgrammeResult
    logistics: LogisticsResult
    carbon: CarbonResult
    heat_loss: HeatLossResult
    estimate: CostEstimate


@dataclass
class Workspace:
    project: Optional[Project] = None
    store_dir: str = ""
    #: image_id -> user annotations and rejected detections (passed as ``manual_features``).
    manual: dict[str, list[DetectedFeature]] = field(default_factory=dict)
    analysis_key: Optional[str] = None
    #: Fingerprint of the hypothesis the current twin was built from.
    twin_source_fp: Optional[str] = None
    proceed_with_assumptions: bool = False
    vlm_enabled: bool = False
    optional_adapters: bool = False
    simulation: Optional[SimulationResult] = None
    simulation_key: Optional[str] = None
    comparison: Optional[ScenarioComparison] = None
    comparison_key: Optional[str] = None
    export: Optional[dict[str, Any]] = None
    cur_kpis: Optional[dict[str, float]] = None
    prev_kpis: Optional[dict[str, float]] = None
    kpi_key: Optional[str] = None
    flash: list[tuple[str, str]] = field(default_factory=list)
    calibration_error: Optional[str] = None

    # ------------------------------------------------------------------ helpers
    def reset(self, project: Optional[Project]) -> None:
        keep = (self.store_dir, self.vlm_enabled, self.optional_adapters)
        self.__init__()  # type: ignore[misc]
        self.store_dir, self.vlm_enabled, self.optional_adapters = keep
        self.project = project

    def say(self, level: str, text: str) -> None:
        self.flash.append((level, str(text)[:2000]))

    @property
    def has_project(self) -> bool:
        return self.project is not None

    def hypothesis(self, hypothesis_id: Optional[str] = None) -> Optional[GeometryHypothesis]:
        p = self.project
        if p is None or not p.hypotheses:
            return None
        hid = hypothesis_id or p.selected_hypothesis_id
        return next((h for h in p.hypotheses if h.hypothesis_id == hid), None)

    def image(self, image_id: str) -> Optional[ImageAsset]:
        p = self.project
        return next((a for a in p.images if a.image_id == image_id), None) if p else None


def data_dir() -> Path:
    base = os.environ.get(DATA_DIR_ENV)
    return Path(base) if base else Path.cwd() / ".hbv"


def image_store_dir() -> Path:
    d = data_dir() / "images"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_workspace() -> Workspace:
    ws = st.session_state.get(SESSION_KEY)
    if not isinstance(ws, Workspace):
        ws = Workspace(store_dir=str(image_store_dir()))
        ws.vlm_enabled = os.environ.get(P.VLM_ENV, "").strip() == "1" and vlm_available()
        st.session_state[SESSION_KEY] = ws
    return ws


# =============================================================================
# Fingerprints
# =============================================================================
_FP_MEMO: "OrderedDict[int, tuple[Any, str]]" = OrderedDict()
_FP_MEMO_SIZE = 256


def fp(obj: Any) -> str:
    """Canonical SHA-256 of a model / plain value, memoised by identity (models are treated as immutable)."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return P.fingerprint(obj)
    k = id(obj)
    hit = _FP_MEMO.get(k)
    if hit is not None and hit[0] is obj:
        _FP_MEMO.move_to_end(k)
        return hit[1]
    if isinstance(obj, BuildingTwin):
        from ..twin.builder import twin_hash

        val = twin_hash(obj)
    else:
        val = P.fingerprint(obj)
    _FP_MEMO[k] = (obj, val)
    while len(_FP_MEMO) > _FP_MEMO_SIZE:
        _FP_MEMO.popitem(last=False)
    return val


def combine(*parts: Any) -> str:
    text = "|".join(p if isinstance(p, str) else fp(p) for p in parts)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def eval_key(project: Project, twin: BuildingTwin) -> str:
    return combine(fp(twin), fp(project.library), fp(project.rate_book), fp(project.cost_parameters),
                   fp(project.settings), fp(project.assumptions))


# =============================================================================
# Adapters
# =============================================================================
def vlm_available() -> bool:
    """True when the optional Claude adapter could run (``anthropic`` installed and a key set)."""
    try:
        from ..vision.vlm_adapter import ClaudeVLMExtractor

        return bool(ClaudeVLMExtractor().is_available())
    except Exception:  # noqa: BLE001 - optional adapter must never break the UI
        return False


@st.cache_resource(show_spinner=False)
def get_registry(vlm: bool = False, optional: bool = False):
    """Adapter registry: bundled fixtures + NumPy perspective + multi-view (+ opt-in VLM / optional)."""
    from ..vision.adapters import default_registry

    return default_registry(enable_vlm=bool(vlm), enable_optional=bool(optional))


# =============================================================================
# Cached engine calls
# =============================================================================
@st.cache_data(max_entries=24, show_spinner=False)
def _cached_analysis(key: str, _images: list[ImageAsset], _store_dir: str,
                     _manual: dict[str, list[DetectedFeature]], _assumptions, vlm: bool,
                     optional: bool) -> tuple[AnalysisResult, list[RunRecord]]:
    records: list[RunRecord] = []
    reg = get_registry(vlm, optional)
    out = P.analyse_images(_images, store_dir=_store_dir, registry=reg, manual_features=_manual or None,
                           assumptions=_assumptions, run_log=records)
    return out, records


@st.cache_data(max_entries=64, show_spinner=False)
def _cached_evaluation(key: str, _twin: BuildingTwin, _library, _rate_book: RateBook, _params: CostParameters,
                       _settings: ProjectSettings, _assumptions) -> Evaluation:
    boq = P.calculate_quantities(_twin, _library, assumptions=_assumptions)
    sims = P.run_digital_simulations(_twin, boq, _library, _settings, cost_params=_params)
    est = P.estimate_construction_cost(boq, _rate_book, _params, settings=_settings,
                                       programme_weeks=sims["programme"].duration_weeks,
                                       logistics=sims["logistics"], library=_library)
    return Evaluation(key=key, boq=boq, programme=sims["programme"], logistics=sims["logistics"],
                      carbon=sims["carbon"], heat_loss=sims["heat_loss"], estimate=est)


@st.cache_data(max_entries=64, show_spinner=False)
def _cached_repeat(key: str, _estimate: CostEstimate, _scenario: ProductionScenario, boundary: str,
                   _params: CostParameters) -> RepeatBuildResult:
    return P.calculate_incremental_cost(_estimate, _scenario, boundary=boundary, cost_params=_params)


@st.cache_data(max_entries=12, show_spinner=False)
def _cached_simulation(key: str, _twin, _library, _rate_book, _params, _settings, _config, _calibration,
                       _assumptions) -> tuple[SimulationResult, list[RunRecord]]:
    records: list[RunRecord] = []
    out = P.simulate_uncertainty(_twin, _library, _rate_book, _params, _settings, config=_config,
                                 calibration=_calibration, assumptions=_assumptions, scenario_id=_twin.twin_id,
                                 run_log=records)
    return out, records


@st.cache_data(max_entries=12, show_spinner=False)
def _cached_comparison(key: str, _twin, _hypotheses, _scenarios, _library, _rate_book, _params, _settings,
                       simulate: bool, _config, _calibration, _assumptions
                       ) -> tuple[ScenarioComparison, list[RunRecord]]:
    records: list[RunRecord] = []
    out = P.compare_build_scenarios(_twin, _hypotheses, _scenarios, _library, _rate_book, _params, _settings,
                                    simulate=simulate, config=_config, calibration=_calibration,
                                    assumptions=_assumptions, run_log=records)
    return out, records


@st.cache_data(max_entries=32, show_spinner=False)
def image_preview(sha256: str, _asset: ImageAsset, _store_dir: str, max_width: int = 1200) -> tuple[str, float]:
    """``(data URI, scale)`` of a downscaled JPEG preview of the preserved original."""
    import base64

    from PIL import Image

    from ..vision.ingest import load_image_array

    rgb = load_image_array(_asset, _store_dir)
    im = Image.fromarray(rgb)
    scale = min(1.0, float(max_width) / float(im.width))
    if scale < 1.0:
        im = im.resize((max(1, int(round(im.width * scale))), max(1, int(round(im.height * scale)))),
                       Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    im.convert("RGB").save(buf, format="JPEG", quality=86, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii"), scale


# =============================================================================
# Project lifecycle
# =============================================================================
def _slug(text: str, n: int = 40) -> str:
    s = _ID_SAFE.sub("-", (text or "").strip().lower()).strip("-.")
    return (s or "project")[:n]


def load_demo(ws: Workspace, *, side_view: bool = False, concept: bool = False) -> None:
    """Replace the workspace with the FICTIONAL demo project (H-A twin, demo rates, scenarios)."""
    from ..demo.build_demo import DATA_DIR, build_demo_project
    from ..vision.ingest import ingest_path

    store = ws.store_dir or str(image_store_dir())
    project = build_demo_project(store, include_side_view=side_view, registry=get_registry(False, False))
    ws.reset(project)
    ws.store_dir = store
    hyp = ws.hypothesis()
    ws.twin_source_fp = fp(hyp) if hyp is not None else None
    if concept:
        asset = ingest_path(DATA_DIR / "concept_render_example.jpg", kind=ImageKind.AI_CONCEPT,
                            view=ViewDirection.FRONT, store_dir=store,
                            notes="AI-generated concept render bundled as a concept-reference example (fictional).")
        project.images.append(asset)
        refresh_evidence(ws)
    else:
        ws.analysis_key = analysis_key(ws)
    ws.say("success", f"Loaded the fictional demo project '{project.name}'"
           + (" with the left elevation" if side_view else "") + (" and an AI concept example" if concept else "")
           + ". All prices and production economics are FICTIONAL.")


def new_project(ws: Workspace, name: str, *, use_demo_rates: bool = True) -> None:
    from ..costing.adapters import demo_rate_book
    from ..quantities.library import default_library

    clean = _CTRL.sub(" ", name or "").strip()[:120] or "Untitled project"
    pid = f"{_slug(clean)}-{datetime.now(timezone.utc):%Y%m%d%H%M%S}"
    book = demo_rate_book() if use_demo_rates else RateBook(name="empty rate book")
    project = Project(project_id=pid, name=clean, library=default_library(), rate_book=book,
                      cost_parameters=CostParameters(), simulation_config=SimulationConfig(),
                      notes="Created in the Housebuilder.OS Vision UI.")
    store = ws.store_dir
    ws.reset(project)
    ws.store_dir = store
    ws.say("success", f"New project '{clean}' created. Upload images in the Images view."
           + (" The FICTIONAL demo rate book is loaded until you upload your own." if use_demo_rates else ""))


def project_store():
    from ..io.persistence import ProjectStore

    return ProjectStore(data_dir() / "housebuilder.db")


def save_project(ws: Workspace) -> str:
    p = ws.project
    if p is None:
        raise ValueError("no project to save")
    if p.twin is not None:
        p.selected_hypothesis_id = p.selected_hypothesis_id or p.twin.source_hypothesis_id
    with project_store() as store:
        saved = store.save_project(p)
    ws.project = saved
    return f"Saved '{saved.name}' ({saved.project_id}) to {data_dir() / 'housebuilder.db'}."


def list_saved_projects() -> list[Any]:
    try:
        with project_store() as store:
            return store.list_projects()
    except Exception:  # noqa: BLE001 - a missing / locked store just means nothing to list
        return []


def load_saved_project(ws: Workspace, project_id: str) -> str:
    with project_store() as store:
        project = store.load_project(project_id)
    store_dir = ws.store_dir
    ws.reset(project)
    ws.store_dir = store_dir
    ws.manual = manual_from_analysis(project.analysis)
    hyp = ws.hypothesis()
    if project.twin is not None and hyp is not None and project.twin.source_hypothesis_id == hyp.hypothesis_id:
        ws.twin_source_fp = fp(hyp)
    ws.analysis_key = analysis_key(ws) if project.analysis is not None else None
    return f"Loaded '{project.name}' ({project.project_id}, {len(project.images)} image(s))."


# =============================================================================
# Evidence
# =============================================================================
def manual_from_analysis(analysis: Optional[AnalysisResult]) -> dict[str, list[DetectedFeature]]:
    """Reconstruct the user's annotations and rejections from a stored analysis."""
    out: dict[str, list[DetectedFeature]] = {}
    if analysis is None:
        return out
    for a in analysis.analyses:
        for f in a.features:
            rejected = (not f.active) and any(h.reason == UI_REJECT_REASON for h in f.history)
            if f.method == UI_ANNOTATION_METHOD or rejected:
                hist = [h for h in f.history if h.reason == UI_REJECT_REASON][:1]
                out.setdefault(a.image_id, []).append(f.model_copy(update={"history": hist}, deep=True))
    return out


def analysis_key(ws: Workspace) -> str:
    p = ws.project
    assert p is not None
    imgs = [(a.image_id, a.sha256, a.kind.value, a.view.value) for a in p.images]
    manual = {k: [f.model_dump(mode="json", exclude={"history"}) for f in v] for k, v in sorted(ws.manual.items())}
    return combine(P.fingerprint(imgs), P.fingerprint(manual), fp(p.assumptions),
                   f"vlm={ws.vlm_enabled}", f"opt={ws.optional_adapters}")


def _calibrate(ws: Workspace, analysis: AnalysisResult):
    p = ws.project
    ref = p.references[0] if p.references else None
    ws.calibration_error = None
    if ref is not None:
        try:
            return P.calibrate_scale(analysis, ref, assumptions=p.assumptions, run_log=p)
        except (ValueError, ValidationError) as e:
            ws.calibration_error = f"Reference measurement not usable ({e}); labelled prior cues are used instead."
    return P.calibrate_scale(analysis, None, assumptions=p.assumptions, run_log=p)


def refresh_evidence(ws: Workspace) -> None:
    """Analyse images -> calibrate -> hypotheses -> keep / rebuild the twin."""
    p = ws.project
    if p is None:
        return
    if not p.images:
        p.analysis, p.calibration, p.hypotheses = None, None, []
        ws.analysis_key = None
        return
    key = analysis_key(ws)
    analysis, records = _cached_analysis(key, list(p.images), ws.store_dir, dict(ws.manual), p.assumptions,
                                         ws.vlm_enabled, ws.optional_adapters)
    if key != ws.analysis_key:
        p.run_log.extend(records)
        ws.analysis_key = key
    p.analysis = analysis
    if not analysis.facades:
        p.calibration, p.hypotheses = None, []
        return
    try:
        cal = _calibrate(ws, analysis)
        hyps = P.generate_geometry_hypotheses(analysis, cal, assumptions=p.assumptions, settings=p.settings, run_log=p)
    except (ValueError, ValidationError) as e:
        p.calibration, p.hypotheses = None, []
        ws.say("error", f"Calibration / hypotheses could not be derived from this evidence: {e}")
        return
    p.calibration, p.hypotheses = cal, hyps
    ids = [h.hypothesis_id for h in hyps]
    if hyps and p.selected_hypothesis_id not in ids:
        p.selected_hypothesis_id = ids[0]
    sync_twin(ws)


def user_geometry_edits(twin: Optional[BuildingTwin]) -> int:
    if twin is None:
        return 0
    return sum(1 for r in twin.edit_log
               if not r.target.startswith("assemblies") and not r.actor.lower().startswith(("system", "scenario")))


def twin_status(ws: Workspace) -> str:
    """``"none"`` (no twin), ``"ok"`` or ``"stale"`` (evidence / hypothesis changed since it was built)."""
    p = ws.project
    if p is None or p.twin is None:
        return "none"
    hyp = ws.hypothesis()
    if hyp is None:
        return "stale" if p.images else "ok"
    if p.twin.source_hypothesis_id != hyp.hypothesis_id or ws.twin_source_fp != fp(hyp):
        return "stale"
    return "ok"


def sync_twin(ws: Workspace) -> None:
    """Build the twin when none exists; rebuild silently when it carries no geometry edits."""
    p = ws.project
    hyp = ws.hypothesis()
    if p is None or hyp is None:
        return
    if p.twin is None:
        build_twin(ws, hyp.hypothesis_id)
        return
    if twin_status(ws) == "stale" and user_geometry_edits(p.twin) == 0 \
            and p.twin.source_hypothesis_id == hyp.hypothesis_id:
        build_twin(ws, hyp.hypothesis_id, announce=False)


def build_twin(ws: Workspace, hypothesis_id: str, *, announce: bool = True) -> None:
    """Build the twin from a hypothesis, keeping the current assembly selection (never set by appearance)."""
    from ..quantities.library import default_selection
    from ..twin.builder import visual_finishes_from_analysis

    p = ws.project
    hyp = ws.hypothesis(hypothesis_id)
    if p is None or hyp is None:
        raise ValueError(f"unknown hypothesis '{hypothesis_id}'")
    if not p.library.assemblies:
        from ..quantities.library import default_library

        p.library = default_library()
    selection = p.twin.assemblies if p.twin is not None else default_selection(p.library)
    finishes = visual_finishes_from_analysis(p.analysis) if p.analysis is not None else None
    lost = user_geometry_edits(p.twin)
    twin = P.build_parametric_twin(hyp, selection=selection, settings=p.settings, visual_finishes=finishes,
                                   run_log=p)
    p.twin = twin
    p.selected_hypothesis_id = hyp.hypothesis_id
    ws.twin_source_fp = fp(hyp)
    if announce:
        ws.say("success", f"Twin built from {hyp.hypothesis_id} '{hyp.name}'"
               + (f"; {lost} earlier geometry edit(s) were not carried over" if lost else "")
               + "; the assembly selection was kept.")


def ingest_uploads(ws: Workspace, uploads: Sequence[tuple[str, bytes, ImageKind, ViewDirection]]
                   ) -> tuple[list[str], list[tuple[str, str]]]:
    """Validate and add uploads (``vision.ingest``); returns (added names, [(name, rejection reason)])."""
    from ..vision.ingest import ImageRejected, ingest_image

    p = ws.project
    if p is None:
        raise ValueError("create or load a project first")
    added: list[str] = []
    rejected: list[tuple[str, str]] = []
    known = {a.image_id for a in p.images}
    for name, data, kind, view in uploads:
        try:
            asset = ingest_image(data, name, kind=kind, view=view, store_dir=ws.store_dir)
        except ImageRejected as e:
            rejected.append((name, str(e)))
            continue
        except Exception as e:  # noqa: BLE001 - any decoder failure is a rejection, never a crash
            rejected.append((name, f"could not be read as an image ({type(e).__name__})"))
            continue
        if asset.image_id in known:
            rejected.append((name, "duplicate - the same image content is already in the project"))
            continue
        p.images.append(asset)
        known.add(asset.image_id)
        added.append(asset.original_filename)
    if added:
        refresh_evidence(ws)
    return added, rejected


def update_image(ws: Workspace, image_id: str, *, kind: Optional[ImageKind] = None,
                 view: Optional[ViewDirection] = None) -> None:
    p = ws.project
    for i, a in enumerate(p.images):
        if a.image_id == image_id:
            upd = {}
            if kind is not None and kind != a.kind:
                upd["kind"] = kind
            if view is not None and view != a.view:
                upd["view"] = view
            if upd:
                p.images[i] = a.model_copy(update=upd)
                refresh_evidence(ws)
            return
    raise ValueError(f"unknown image {image_id}")


def remove_image(ws: Workspace, image_id: str) -> None:
    p = ws.project
    p.images = [a for a in p.images if a.image_id != image_id]
    ws.manual.pop(image_id, None)
    p.references = [r for r in p.references if r.image_id != image_id]
    refresh_evidence(ws)


def set_feature_active(ws: Workspace, image_id: str, feature: DetectedFeature, active: bool) -> None:
    """Reject (or restore) a feature; the analysis is re-run with the change as user input."""
    items = list(ws.manual.get(image_id, []))
    idx = next((i for i, f in enumerate(items) if f.feature_id == feature.feature_id), None)
    if feature.method == UI_ANNOTATION_METHOD and idx is not None:
        items[idx] = items[idx].model_copy(update={"active": active})
    elif not active:
        rec = EditRecord(actor="user", target=feature.feature_id, field="active", old_value=True, new_value=False,
                         old_basis=feature.basis, new_basis=feature.basis, reason=UI_REJECT_REASON)
        rej = feature.model_copy(update={"active": False, "history": [rec]}, deep=True)
        if idx is None:
            items.append(rej)
        else:
            items[idx] = rej
    elif idx is not None:
        items.pop(idx)
    ws.manual[image_id] = items
    refresh_evidence(ws)


def _clean_text(v: Any, limit: int = 120) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    return _CTRL.sub(" ", str(v)).strip()[:limit]


def _num_or_none(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def annotation_rows(ws: Workspace, image_id: str) -> list[dict[str, Any]]:
    """Current user annotations of ``image_id`` as editor rows."""
    rows = []
    for f in ws.manual.get(image_id, []):
        if f.method != UI_ANNOTATION_METHOD:
            continue
        g = f.line if f.line is not None else f.bbox
        rows.append({"type": f.feature_type.value, "x0": g[0], "y0": g[1], "x1": g[2], "y1": g[3],
                     "label": f.label, "storey": f.attributes.get("storey"), "block": f.attributes.get("block", ""),
                     "roof_form": f.attributes.get("roof_form", ""), "active": f.active})
    return rows


def annotations_to_features(asset: ImageAsset, rows: Sequence[dict[str, Any]]
                            ) -> tuple[list[DetectedFeature], list[str]]:
    """Validate editor rows into USER_CONFIRMED :class:`DetectedFeature` s (errors name the row)."""
    feats: list[DetectedFeature] = []
    errors: list[str] = []
    mx, my = 0.10 * asset.width_px, 0.10 * asset.height_px
    for i, r in enumerate(rows, start=1):
        if not any(_num_or_none(r.get(k)) is not None for k in ("x0", "y0", "x1", "y1")) and not r.get("type"):
            continue  # an empty row added by the editor
        t = _clean_text(r.get("type"), 30)
        if t not in ANNOTATION_TYPES:
            errors.append(f"row {i}: choose a feature type")
            continue
        xy = [_num_or_none(r.get(k)) for k in ("x0", "y0", "x1", "y1")]
        if any(v is None for v in xy):
            errors.append(f"row {i}: x0, y0, x1 and y1 must be numbers (pixels)")
            continue
        x0, y0, x1, y1 = xy  # type: ignore[misc]
        if min(x0, x1) < -mx or max(x0, x1) > asset.width_px + mx or min(y0, y1) < -my \
                or max(y0, y1) > asset.height_px + my:
            errors.append(f"row {i}: coordinates are outside the image ({asset.width_px} x {asset.height_px} px)")
            continue
        attrs: dict[str, Any] = {}
        block = _ID_SAFE.sub("_", _clean_text(r.get("block"), 30)).strip("_").lower()
        if block:
            attrs["block"] = block
        elif t == "facade":
            attrs["block"] = "main"
        st_v = _num_or_none(r.get("storey"))
        if st_v is not None:
            if st_v < 0 or st_v > 9 or abs(st_v - round(st_v)) > 1e-9:
                errors.append(f"row {i}: storey must be an integer 0-9 (0 = ground floor)")
                continue
            attrs["storey"] = int(round(st_v))
        rf = _clean_text(r.get("roof_form"), 12).lower()
        if rf:
            if rf not in ROOF_FORMS:
                errors.append(f"row {i}: roof form must be one of {', '.join(f for f in ROOF_FORMS if f)}")
                continue
            attrs["roof_form"] = rf
        geom: dict[str, Any]
        if t in LINE_TYPES:
            geom = {"line": (x0, y0, x1, y1)}
        else:
            if abs(x1 - x0) < 1 or abs(y1 - y0) < 1:
                errors.append(f"row {i}: a {t} box needs a width and height of at least 1 px")
                continue
            geom = {"bbox": (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))}
        try:
            feats.append(DetectedFeature(
                feature_id=f"{asset.image_id}.u{i:03d}", image_id=asset.image_id, feature_type=FeatureType(t),
                label=_clean_text(r.get("label")) or f"user {t.replace('_', ' ')}", basis=Basis.USER_CONFIRMED,
                method=UI_ANNOTATION_METHOD, method_version="user", confidence=None, pixel_uncertainty=3.0,
                attributes=attrs, evidence="Manual annotation entered in the Images view (user-confirmed).",
                active=bool(r.get("active", True)) if r.get("active") is not None else True, **geom))
        except ValidationError as e:
            errors.append(f"row {i}: {e.errors()[0].get('msg', 'invalid')}")
    return feats, errors


def set_annotations(ws: Workspace, image_id: str, rows: Sequence[dict[str, Any]]) -> list[str]:
    """Replace the user annotations of an image (rejections are kept) and re-run the analysis."""
    asset = ws.image(image_id)
    if asset is None:
        return [f"unknown image {image_id}"]
    feats, errors = annotations_to_features(asset, rows)
    if errors:
        return errors
    keep = [f for f in ws.manual.get(image_id, []) if f.method != UI_ANNOTATION_METHOD]
    ws.manual[image_id] = keep + feats
    refresh_evidence(ws)
    return []


def set_reference(ws: Workspace, ref: ReferenceMeasurement) -> Optional[str]:
    """Use ``ref`` for calibration; returns an error message (and keeps the old reference) on failure."""
    p = ws.project
    from ..twin.calibration import resolve_reference

    if p.analysis is None:
        return "analyse an image first"
    try:
        resolve_reference(p.analysis, ref, assumptions=p.assumptions)
    except (ValueError, ValidationError) as e:
        return f"Reference measurement rejected: {e}"
    p.references = [ref] + [r for r in p.references[1:]]
    ws.proceed_with_assumptions = False
    refresh_evidence(ws)
    return None


def clear_reference(ws: Workspace) -> None:
    ws.project.references = []
    refresh_evidence(ws)


def set_vlm(ws: Workspace, enabled: bool) -> None:
    ws.vlm_enabled = bool(enabled) and vlm_available()
    refresh_evidence(ws)


def set_optional_adapters(ws: Workspace, enabled: bool) -> None:
    ws.optional_adapters = bool(enabled)
    refresh_evidence(ws)


# =============================================================================
# Twin edits
# =============================================================================
def edit_twin(ws: Workspace, edit: TwinEdit) -> Optional[str]:
    """Apply one validated edit (new twin version, basis USER_CONFIRMED); returns an error message or None."""
    from ..twin.builder import apply_twin_edit

    p = ws.project
    if p is None or p.twin is None:
        return "no twin to edit"
    try:
        p.twin = apply_twin_edit(p.twin, edit)
    except (ValueError, ValidationError) as e:
        return f"Edit not applied ({edit.target_type} {edit.target_id or ''} {edit.field}): {e}"
    return None


def set_assembly(ws: Workspace, element: str, assembly_id: str) -> Optional[str]:
    p = ws.project
    if p is None or p.twin is None:
        return "no twin"
    try:
        p.twin = P.apply_construction_assemblies(p.twin, {element: assembly_id}, p.library, actor="user",
                                                 reason="selected in the Twin view", run_log=p)
    except (ValueError, ValidationError) as e:
        return f"Assembly not applied: {e}"
    return None


# =============================================================================
# Commercial inputs
# =============================================================================
def update_settings(ws: Workspace, **changes: Any) -> Optional[str]:
    p = ws.project
    try:
        new = ProjectSettings.model_validate({**p.settings.model_dump(), **changes})
    except ValidationError as e:
        return f"Settings not applied: {e.errors()[0].get('msg')}"
    p.settings = new
    return None


def update_cost_parameters(ws: Workspace, data: dict[str, Any]) -> Optional[str]:
    p = ws.project
    try:
        p.cost_parameters = CostParameters.model_validate({**p.cost_parameters.model_dump(), **data})
    except ValidationError as e:
        err = e.errors()[0]
        return f"Commercial parameters not applied: {'.'.join(str(x) for x in err.get('loc', ()))}: {err.get('msg')}"
    return None


def replace_rate_book(ws: Workspace, book: RateBook) -> None:
    ws.project.rate_book = book


def update_production_scenario(ws: Workspace, scenario: ProductionScenario) -> None:
    p = ws.project
    p.production_scenarios = [scenario if s.scenario_id == scenario.scenario_id else s
                              for s in p.production_scenarios]


def add_example_production_scenarios(ws: Workspace, ev: Evaluation) -> None:
    from ..demo.build_demo import demo_production_scenarios_for

    ws.project.production_scenarios = demo_production_scenarios_for(ev.estimate, ev.estimate)


def add_example_build_scenarios(ws: Workspace) -> int:
    from ..demo.build_demo import demo_build_scenarios

    p = ws.project
    hyp_ids = {h.hypothesis_id for h in p.hypotheses}
    asm = {a.assembly_id for a in p.library.assemblies}
    keep = [s for s in demo_build_scenarios()
            if (s.hypothesis_id is None or s.hypothesis_id in hyp_ids)
            and all(v in asm for v in s.assembly_overrides.values())]
    p.build_scenarios = keep
    return len(keep)


# =============================================================================
# Results
# =============================================================================
def evaluate(ws: Workspace) -> Optional[Evaluation]:
    p = ws.project
    if p is None or p.twin is None:
        return None
    key = eval_key(p, p.twin)
    ev = _cached_evaluation(key, p.twin, p.library, p.rate_book, p.cost_parameters, p.settings, p.assumptions)
    _track_kpis(ws, ev)
    return ev


def kpis(ev: Evaluation) -> dict[str, float]:
    est = ev.estimate
    b = {x.key: x.amount for x in est.boundaries}
    gia = est.gia_m2
    cost = b.get("construction_incl_contingency", float("nan"))
    return {"gia_m2": gia, "construction": cost, "contract_sum": b.get("contract_sum", float("nan")),
            "per_m2": cost / gia if gia > 0 else float("nan"), "programme_weeks": ev.programme.duration_weeks,
            "hlc": ev.heat_loss.heat_loss_coefficient_w_k, "carbon": ev.carbon.total_kgco2e,
            "unresolved": float(len(est.unresolved_items))}


def _track_kpis(ws: Workspace, ev: Evaluation) -> None:
    if ws.kpi_key == ev.key:
        return
    ws.prev_kpis, ws.cur_kpis, ws.kpi_key = ws.cur_kpis, kpis(ev), ev.key


def repeat_results(ws: Workspace, ev: Evaluation, scenario: ProductionScenario,
                   boundaries: Sequence[str] = REPEAT_UI_BOUNDARIES) -> dict[str, RepeatBuildResult]:
    p = ws.project
    out = {}
    for b in boundaries:
        key = combine(ev.key, fp(scenario), b, fp(p.cost_parameters))
        out[b] = _cached_repeat(key, ev.estimate, scenario, b, p.cost_parameters)
    return out


def simulation_inputs_key(ws: Workspace, config: SimulationConfig) -> str:
    p = ws.project
    return combine(eval_key(p, p.twin), fp(config), fp(p.calibration))


def run_simulation(ws: Workspace, *, n_samples: int, seed: int, groups: Sequence[str], method: str = "lhs"
                   ) -> SimulationResult:
    p = ws.project
    if p is None or p.twin is None:
        raise ValueError("build a twin first")
    cfg = p.simulation_config.model_copy(update={
        "n_samples": int(n_samples), "seed": int(seed), "include_groups": list(groups), "method": method})
    cfg = SimulationConfig.model_validate(cfg.model_dump())
    p.simulation_config = cfg
    key = simulation_inputs_key(ws, cfg)
    res, records = _cached_simulation(key, p.twin, p.library, p.rate_book, p.cost_parameters, p.settings, cfg,
                                      p.calibration, p.assumptions)
    if key != ws.simulation_key:
        p.run_log.extend(records)
    ws.simulation, ws.simulation_key = res, key
    return res


def simulation_is_current(ws: Workspace) -> bool:
    p = ws.project
    if ws.simulation is None or p is None or p.twin is None:
        return False
    return ws.simulation_key == simulation_inputs_key(ws, p.simulation_config)


def comparison_inputs_key(ws: Workspace, simulate: bool, n: int) -> str:
    p = ws.project
    return combine(eval_key(p, p.twin), P.fingerprint([h.model_dump(mode="json") for h in p.hypotheses]),
                   P.fingerprint([s.model_dump(mode="json") for s in p.build_scenarios]), f"sim={simulate}",
                   f"n={n}", f"seed={p.simulation_config.seed}", fp(p.calibration))


def compare_scenarios(ws: Workspace, *, simulate: bool = False, n: int = 60) -> ScenarioComparison:
    p = ws.project
    if p is None or p.twin is None:
        raise ValueError("build a twin first")
    if not p.build_scenarios:
        raise ValueError("the project has no build scenarios")
    cfg = p.simulation_config.model_copy(update={"n_samples": max(20, int(n))}) if simulate else None
    key = comparison_inputs_key(ws, simulate, n)
    res, records = _cached_comparison(key, p.twin, list(p.hypotheses), list(p.build_scenarios), p.library,
                                      p.rate_book, p.cost_parameters, p.settings, simulate, cfg, p.calibration,
                                      p.assumptions)
    if key != ws.comparison_key:
        p.run_log.extend(records)
    ws.comparison, ws.comparison_key = res, key
    return res


def export_bundle(ws: Workspace, ev: Evaluation, formats: Sequence[str]) -> dict[str, Any]:
    """Run ``export_project`` into a temporary folder and keep the files in memory for download."""
    p = ws.project
    repeats: list[RepeatBuildResult] = []
    for ps in p.production_scenarios:
        repeats.extend(repeat_results(ws, ev, ps, P.REPEAT_BOUNDARIES).values())
    sim = ws.simulation if simulation_is_current(ws) else None
    comp = ws.comparison if ws.comparison is not None else None
    tmp = Path(tempfile.mkdtemp(prefix="hbv-ui-export-"))
    try:
        manifest = P.export_project(p, tmp, boq=ev.boq, estimate=ev.estimate, simulation=sim, repeat=repeats,
                                    comparison=comp, formats=list(formats), library=p.library, rate_book=p.rate_book,
                                    run_log=p)
        files = []
        for f in manifest.files:
            path = (tmp / f.path).resolve()
            if tmp.resolve() not in path.parents or not path.is_file():
                continue
            ext = path.suffix.lstrip(".").lower()
            files.append({"name": f.path, "data": path.read_bytes(), "mime": EXPORT_MIME.get(ext, "application/octet-stream"),
                          "format": f.format, "description": f.description, "size": f.size_bytes})
        mpath = tmp / "manifest.json"
        if mpath.is_file():
            files.append({"name": "manifest.json", "data": mpath.read_bytes(), "mime": "application/json",
                          "format": "json", "description": "sha256 manifest", "size": mpath.stat().st_size})
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for f in files:
                z.writestr(f"{_slug(p.project_id, 60)}/{f['name']}", f["data"])
        out = {"manifest": manifest, "files": files, "zip": buf.getvalue(), "key": ev.key,
               "simulation_included": sim is not None}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    ws.export = out
    return out


__all__ = [
    "ANNOTATION_TYPES", "Evaluation", "KIND_LABELS", "LINE_TYPES", "ROOF_FORMS", "UI_ANNOTATION_METHOD",
    "UI_REJECT_REASON", "VIEW_LABELS", "Workspace", "add_example_build_scenarios", "add_example_production_scenarios",
    "analysis_key", "annotation_rows", "annotations_to_features", "build_twin", "clear_reference", "combine",
    "compare_scenarios", "data_dir", "edit_twin", "eval_key", "evaluate", "export_bundle", "fp", "get_registry",
    "get_workspace", "image_preview", "image_store_dir", "ingest_uploads", "kind_label", "kpis", "list_saved_projects",
    "load_demo", "load_saved_project", "manual_from_analysis", "new_project", "refresh_evidence", "remove_image",
    "repeat_results", "replace_rate_book", "run_simulation", "save_project", "set_annotations", "set_assembly",
    "set_feature_active", "set_optional_adapters", "set_reference", "set_vlm", "simulation_is_current", "sync_twin",
    "twin_status", "update_cost_parameters", "update_image", "update_production_scenario", "update_settings",
    "user_geometry_edits", "view_label", "vlm_available",
]
