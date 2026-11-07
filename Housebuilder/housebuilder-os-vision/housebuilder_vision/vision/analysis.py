"""Image analysis: adapters -> evidence -> pixel-space facade observations.

:func:`analyse_images` runs the registered adapters on each image, merges user
annotations, and summarises every elevation-like view into
:class:`~housebuilder_vision.core.models.FacadeObservation` objects (one per
image and visible block).  It works entirely in **pixels**; conversion to
metres is the job of ``twin.calibration``.

Measurement conventions (per facade / block hint)
-------------------------------------------------
* ``width_px``: width of the facade bounding box (external face to external
  face on the facade plane).
* ``ground_y_px``: ground line at the facade centre (bbox bottom if no ground
  line was detected; then ``INFERRED``).
* ``eaves_height_px``: ground line to wall plate.  Taken from an eaves line;
  otherwise the lowest roof edge, otherwise the top of the facade box (both
  ``INFERRED``).
* ``ridge_height_px``: ground line to the ridge or roof apex (ridge line, else
  the highest roof outline point; flat roofs equal the eaves height).
* Pixel uncertainties: each feature's ``pixel_uncertainty`` is one standard
  deviation per edge/vertex; ``low``/``high`` are +/- 2 sigma of the combined
  error (triangular distribution).  Perspective uncertainty is *not* folded
  into pixel lengths; it is reported in ``ImageAnalysis.perspective`` and
  included in the pitch uncertainty.
* ``storeys`` (``INFERRED``): number of window rows (windows clustered by
  vertical centre), cross-checked with storey lines (string courses/floor
  bands) and with the wall height relative to a door (which uses the labelled
  door-height and floor-to-floor *assumptions*); a VLM storey count, if
  present, is only a cross-check.  When only the door-height check is
  available the count is ``INFERRED`` if it is robust to the whole assumed
  prior range, otherwise ``ASSUMED``.
* ``apparent_pitch_deg`` (``OBSERVED``): only when a gable triangle is visible
  in elevation: ``atan(2 * rise / base)``, with vertex pixel errors, slope
  asymmetry and perspective foreshortening propagated into ``low``/``high``.
  Never computed from a hip end or from a roof band seen eaves-on.
* Openings get a storey index from storey lines, or from midpoints between
  window rows, and a ``block_hint`` from the ``block`` attribute or by
  containment in the smallest enclosing facade box.
* Finishes are :class:`ObservedFinish` (appearance only, with the caveat that
  appearance does not establish structure or build-up).

Provenance rules
----------------
* Detections from fixtures/manual annotation are ``OBSERVED`` image evidence;
  manual features supplied through ``manual_features`` are recorded as
  ``USER_CONFIRMED`` and override overlapping detections (which are kept but
  deactivated, with an :class:`EditRecord`).
* Concept references (AI concept, rendering, sketch — from ``ImageAsset.kind``,
  fixture metadata or the VLM) never yield ``OBSERVED`` measurements: their
  bases are capped at ``INFERRED`` and a warning states that geometry may be
  inconsistent and dimensions are indicative only.  For AI concepts simple
  internal inconsistencies are checked and recorded (misaligned window rows,
  overlapping openings, openings outside their facade, VLM-reported issues).
* ``unknowns`` always lists what images cannot establish: structural system
  and material, insulation and thicknesses, foundations, concealed services,
  engineering adequacy, internal layout, hidden facades (naming the missing
  views), and per-block plan depth / roof pitch when not observed.
* Nothing is fabricated: an image without a matching fixture, detector output
  or manual annotation yields no facade observation, only a warning.
* Every adapter considered is recorded as an ``AdapterRun`` on the image's
  ``ImageAnalysis.adapters`` (multi-view runs on the primary image's), and
  ``model_versions`` lists every adapter/detector/model that produced output.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import numpy as np

from ..core.models import (
    AnalysisResult,
    DetectedFeature,
    FacadeObservation,
    FeatureType,
    ImageAnalysis,
    ImageAsset,
    ImageKind,
    ObservedFinish,
    ObservedOpening,
    PerspectiveEstimate,
    VLMExtraction,
    ViewDirection,
)
from ..core.provenance import BASIS_RANK, Basis, Distribution, EditRecord, TrackedValue, unknown, weakest_basis
from ..core.settings import AssumptionLibrary, ProjectSettings
from .adapters import AdapterRegistry, Capability, default_registry
from .ingest import ImageRejected, load_image_array

ANALYSIS_METHOD = "housebuilder_vision.vision.analysis"
ANALYSIS_VERSION = "1.0"

ELEVATION_VIEWS = {ViewDirection.FRONT, ViewDirection.REAR, ViewDirection.LEFT, ViewDirection.RIGHT}
OBLIQUE_COVERAGE = {
    ViewDirection.FRONT_LEFT_OBLIQUE: ("front", "left"),
    ViewDirection.FRONT_RIGHT_OBLIQUE: ("front", "right"),
}
OPENING_KINDS: dict[FeatureType, str] = {
    FeatureType.WINDOW: "window",
    FeatureType.DOOR: "door",
    FeatureType.GARAGE_DOOR: "garage_door",
}
_OPENING_KIND_VALUES = {"window", "door", "garage_door", "patio_door", "balcony_door"}
FINISH_ELEMENTS = {"walls", "roof", "garage_door", "windows", "doors", "other"}
CONCEPT_HINTS = {
    "ai_generated_concept": ImageKind.AI_CONCEPT,
    "ai_concept": ImageKind.AI_CONCEPT,
    "architectural_rendering": ImageKind.RENDERING,
    "rendering": ImageKind.RENDERING,
    "sketch": ImageKind.SKETCH,
}
_CONCEPT_KIND_VALUES = {ImageKind.AI_CONCEPT, ImageKind.RENDERING, ImageKind.SKETCH}

_ROOF_SYNONYMS = {"gabled": "gable", "hipped": "hip", "mono-pitch": "monopitch", "lean-to": "monopitch",
                  "shed": "monopitch", "pent": "monopitch"}
_ROOF_FORMS = {"gable", "hip", "flat", "monopitch"}
_PARALLEL = {"parallel_to_view", "parallel", "along_facade", "horizontal", "x"}
_PERPENDICULAR = {"perpendicular_to_view", "perpendicular", "end_on", "towards_viewer", "y"}

UNKNOWN_STRUCTURE = ("Structural system and structural material: not identifiable from appearance (a brick-like "
                     "facade may be a masonry cavity wall or a timber frame with a brick outer leaf).")
UNKNOWN_INSULATION = ("Insulation type and position, and wall / roof / floor build-up thicknesses (and therefore "
                      "U-values): not visible.")
UNKNOWN_FOUNDATIONS = ("Foundations: type, depth and ground conditions are not visible (site investigation and an "
                       "engineer's design are required).")
UNKNOWN_SERVICES = ("Concealed services: drainage, water, gas, electrical, heating and ventilation routes and "
                    "specification.")
UNKNOWN_ENGINEERING = ("Engineering adequacy (structural, fire, thermal, acoustic, moisture) cannot be assessed "
                       "from images; no compliance or adequacy is implied.")
UNKNOWN_LAYOUT = "Internal layout: rooms, partitions, stairs and floor structure are not visible."
BASE_UNKNOWNS = [UNKNOWN_STRUCTURE, UNKNOWN_INSULATION, UNKNOWN_FOUNDATIONS, UNKNOWN_SERVICES,
                 UNKNOWN_ENGINEERING, UNKNOWN_LAYOUT]
_SIDES = ("front", "rear", "left", "right")


# =============================================================================
# Small geometry helpers
# =============================================================================
Box = tuple[float, float, float, float]


def _bbox_of(f: DetectedFeature) -> Optional[Box]:
    if f.bbox is not None:
        return tuple(float(v) for v in f.bbox)  # type: ignore[return-value]
    if f.polygon:
        xs = [p[0] for p in f.polygon]
        ys = [p[1] for p in f.polygon]
        return (min(xs), min(ys), max(xs), max(ys))
    if f.line is not None:
        x0, y0, x1, y1 = f.line
        return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
    return None


def _center(b: Box) -> tuple[float, float]:
    return 0.5 * (b[0] + b[2]), 0.5 * (b[1] + b[3])


def _area(b: Box) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _x_overlap_frac(a: Box, b: Box) -> float:
    """Overlap of ``a``'s x-range with ``b``'s, as a fraction of the shorter range."""
    ov = min(a[2], b[2]) - max(a[0], b[0])
    span = max(1e-9, min(a[2] - a[0], b[2] - b[0]))
    return max(0.0, ov) / span


def _iou(a: Box, b: Box) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = _area(a) + _area(b) - inter
    return inter / union if union > 0 else 0.0


def _line_y_at(f: DetectedFeature, x: float) -> float:
    if f.line is None:
        b = _bbox_of(f)
        return 0.5 * (b[1] + b[3]) if b else float("nan")
    x0, y0, x1, y1 = f.line
    if abs(x1 - x0) < 1e-6:
        return 0.5 * (y0 + y1)
    lo, hi = min(x0, x1), max(x0, x1)
    x = min(max(x, lo), hi)
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def _norm_block(v: Any) -> Optional[str]:
    if not isinstance(v, str):
        return None
    s = re.sub(r"[^a-z0-9_\-]+", "_", v.strip().lower()).strip("_")
    return s[:40] or None


def _text_attr(v: Any, limit: int = 120) -> Optional[str]:
    if not isinstance(v, str):
        return None
    s = re.sub(r"[\x00-\x1f\x7f]+", " ", v)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit] or None


def _roof_form_attr(f: DetectedFeature) -> Optional[str]:
    v = f.attributes.get("roof_form")
    if not isinstance(v, str):
        return None
    t = v.strip().lower()
    t = _ROOF_SYNONYMS.get(t, t)
    return t if t in _ROOF_FORMS else None


# =============================================================================
# Provenance helpers
# =============================================================================
def _cap(basis: Basis, concept: bool) -> Basis:
    if concept and BASIS_RANK[basis] > BASIS_RANK[Basis.INFERRED]:
        return Basis.INFERRED
    return basis


def _px(value: float, sigma: float, basis: Basis, *, source: str, evidence: Sequence[str], note: str = "") -> TrackedValue:
    sigma = max(0.0, float(sigma))
    lo, hi = value - 2.0 * sigma, value + 2.0 * sigma
    return TrackedValue(value=float(value), unit="px", basis=basis, low=lo, high=hi,
                        distribution=Distribution.TRIANGULAR if hi > lo else Distribution.FIXED,
                        source=source, evidence_ids=list(dict.fromkeys(evidence)), note=note)


def _sig(f: Optional[DetectedFeature], default: float = 3.0) -> float:
    if f is None:
        return default
    return max(0.5, float(f.pixel_uncertainty))


# =============================================================================
# Feature hygiene and manual annotations
# =============================================================================
def _sanitize_features(asset: ImageAsset, feats: Sequence[Any], source: str, warnings: list[str],
                       taken_ids: set[str]) -> list[DetectedFeature]:
    """Re-validate adapter output (untrusted): type, image id, bounds, unique ids."""
    out: list[DetectedFeature] = []
    mx, my = 0.10 * asset.width_px, 0.10 * asset.height_px
    dropped = 0
    for f in feats or []:
        if not isinstance(f, DetectedFeature):
            dropped += 1
            continue
        if f.image_id != asset.image_id:
            dropped += 1
            continue
        b = _bbox_of(f)
        if b is None or not all(math.isfinite(v) for v in b):
            dropped += 1
            continue
        if b[0] < -mx or b[1] < -my or b[2] > asset.width_px + mx or b[3] > asset.height_px + my:
            dropped += 1
            continue
        if f.feature_id in taken_ids:
            k = 2
            while f"{f.feature_id}~{k}" in taken_ids:
                k += 1
            f = f.model_copy(update={"feature_id": f"{f.feature_id}~{k}"[:80]})
        taken_ids.add(f.feature_id)
        out.append(f)
    if dropped:
        warnings.append(f"{dropped} feature(s) from {source} were invalid (wrong image, no geometry or outside "
                        "the image) and were ignored.")
    return out


def _deactivate(f: DetectedFeature, by: DetectedFeature) -> DetectedFeature:
    rec = EditRecord(actor="user", target=f.feature_id, field="active", old_value=True, new_value=False,
                     old_basis=f.basis, new_basis=f.basis,
                     reason=f"superseded by user annotation {by.feature_id}")
    return f.model_copy(update={"active": False, "history": [*f.history, rec]}, deep=True)


def _supersedes(m: DetectedFeature, d: DetectedFeature, img_h: float) -> bool:
    if not d.active:
        return False
    if d.feature_type != m.feature_type and not (m.feature_type in OPENING_KINDS and d.feature_type in OPENING_KINDS):
        return False
    mb, db = _bbox_of(m), _bbox_of(d)
    if mb is None or db is None:
        return False
    mblk, dblk = _norm_block(m.attributes.get("block")), _norm_block(d.attributes.get("block"))
    t = m.feature_type
    if t == FeatureType.FACADE:
        return (mblk or "main") == (dblk or "main")
    if t in OPENING_KINDS:
        return _iou(mb, db) > 0.5
    if t == FeatureType.ROOF:
        return _iou(mb, db) > 0.3 or (mblk is not None and mblk == dblk)
    if t in (FeatureType.EAVES_LINE, FeatureType.RIDGE_LINE, FeatureType.GROUND_LINE, FeatureType.STOREY_LINE):
        same_block = mblk == dblk or mblk is None or dblk is None
        return same_block and abs(_center(mb)[1] - _center(db)[1]) < 0.05 * img_h and _x_overlap_frac(mb, db) > 0.3
    if t == FeatureType.FINISH_REGION:
        return _iou(mb, db) > 0.5
    return False


def _merge_manual(asset: ImageAsset, detected: list[DetectedFeature], manual: Sequence[DetectedFeature],
                  warnings: list[str]) -> list[DetectedFeature]:
    out = list(detected)
    ids = {f.feature_id: i for i, f in enumerate(out)}
    for mf in manual:
        if mf.image_id != asset.image_id:
            warnings.append(f"Manual feature {mf.feature_id} refers to image {mf.image_id}, not {asset.image_id}; ignored.")
            continue
        mf = mf.model_copy(deep=True)
        if mf.basis == Basis.OBSERVED:
            rec = EditRecord(actor="user", target=mf.feature_id, field="basis", old_basis=Basis.OBSERVED,
                             new_basis=Basis.USER_CONFIRMED, reason="manual annotation supplied by the user")
            mf = mf.model_copy(update={"basis": Basis.USER_CONFIRMED, "history": [*mf.history, rec]})
        if mf.method in ("unknown", ""):
            mf = mf.model_copy(update={"method": "manual-annotation", "method_version": "user"})
        if mf.feature_id in ids:
            old = out[ids[mf.feature_id]]
            rec = EditRecord(actor="user", target=mf.feature_id, field="feature", old_basis=old.basis,
                             new_basis=mf.basis, reason="manual annotation replaces the detected feature")
            out[ids[mf.feature_id]] = mf.model_copy(update={"history": [*old.history, *mf.history, rec]})
            continue
        for i, d in enumerate(out):
            if d.active and _supersedes(mf, d, asset.height_px):
                out[i] = _deactivate(d, mf)
        ids[mf.feature_id] = len(out)
        out.append(mf)
    return out


# =============================================================================
# Facade construction
# =============================================================================
class _Ctx:
    def __init__(self, asset: ImageAsset, view: ViewDirection, concept: bool, ai_concept: bool, fu: float,
                 assumptions: AssumptionLibrary) -> None:
        self.asset = asset
        self.view = view
        self.concept = concept
        self.ai_concept = ai_concept
        self.fu = fu
        self.assumptions = assumptions
        self.warnings: list[str] = []
        self.inconsistencies: list[str] = []

    def basis(self, *bases: Basis) -> Basis:
        return _cap(weakest_basis(list(bases)), self.concept)


def _gable_pitch(roof: DetectedFeature, fu: float) -> Optional[tuple[float, float, str]]:
    """(pitch deg, 1-sigma deg, note) from a visible gable triangle, else None."""
    if roof.attributes.get("gable_visible") is False:
        return None
    form = _roof_form_attr(roof)
    if form not in (None, "gable"):
        return None
    poly = roof.polygon
    if not poly or len(poly) < 3:
        return None
    if len(poly) > 3 and roof.attributes.get("gable_visible") is not True:
        return None
    pts = np.asarray(poly, dtype=np.float64)
    ai = int(np.argmin(pts[:, 1]))
    apex = pts[ai]
    rest = np.delete(pts, ai, axis=0)
    left, right = rest[int(np.argmin(rest[:, 0]))], rest[int(np.argmax(rest[:, 0]))]
    if not (left[0] < apex[0] < right[0]):
        return None
    base_y = 0.5 * (left[1] + right[1])
    rise, base = base_y - apex[1], right[0] - left[0]
    if rise <= 0 or base <= 0:
        return None
    th = math.atan2(2.0 * rise, base)
    th_l = math.atan2(left[1] - apex[1], apex[0] - left[0])
    th_r = math.atan2(right[1] - apex[1], right[0] - apex[0])
    e = _sig(roof)
    s_rise, s_base = e * math.sqrt(1.5), e * math.sqrt(2.0)
    den = base * base + 4.0 * rise * rise
    s_px = math.hypot(2.0 * base / den * s_rise, 2.0 * rise / den * s_base)
    s_persp = 0.5 * math.sin(2.0 * th) * fu
    s_asym = 0.5 * abs(th_l - th_r)
    s = math.sqrt(s_px ** 2 + s_persp ** 2 + s_asym ** 2)
    note = (f"atan(2 x rise / base) on the visible gable: rise {rise:.1f} px, base {base:.1f} px; "
            f"half-slopes {math.degrees(th_l):.1f}/{math.degrees(th_r):.1f} deg. Low/high = +/- 2 sigma "
            f"(vertex error {e:.1f} px, perspective {fu:.0%}, asymmetry).")
    return math.degrees(th), math.degrees(s), note


def _cluster_rows(windows: list[tuple[DetectedFeature, Box]]) -> list[list[tuple[DetectedFeature, Box]]]:
    """Cluster windows into rows by vertical centre (single linkage: a new row starts where the
    gap between consecutive centres exceeds 0.6 x the median window height); rows ordered bottom -> top."""
    if not windows:
        return []
    hs = [b[3] - b[1] for _, b in windows]
    gap = max(0.6 * float(np.median(hs)), 8.0)
    srt = sorted(windows, key=lambda t: -_center(t[1])[1])
    rows: list[list] = [[srt[0]]]
    for item in srt[1:]:
        prev_c = _center(rows[-1][-1][1])[1]
        if prev_c - _center(item[1])[1] > gap:
            rows.append([item])
        else:
            rows[-1].append(item)
    return rows


def _storeys_from_height(eaves_h: Optional[float], openings: list[tuple[DetectedFeature, Box, str]],
                         a: AssumptionLibrary) -> Optional[dict[str, Any]]:
    """Storeys from wall height relative to a door, using labelled assumptions."""
    if not eaves_h or eaves_h <= 0:
        return None
    ref = None
    for f, b, kind in openings:
        if kind == "door":
            ref = (b[3] - b[1], a.door_leaf_height_m, "door")
            break
    if ref is None:
        for f, b, kind in openings:
            if kind == "garage_door":
                ref = (b[3] - b[1], a.garage_door_height_m, "garage door")
                break
    if ref is None or ref[0] <= 0:
        return None
    px, prior, label = ref
    ests = []
    for dh in {prior.v(), prior.low or prior.v(), prior.high or prior.v()}:
        for ftf in {a.floor_to_floor_m.v(), a.floor_to_floor_m.low or a.floor_to_floor_m.v(),
                    a.floor_to_floor_m.high or a.floor_to_floor_m.v()}:
            for ffl in {a.ground_floor_level_m.v(), a.ground_floor_level_m.low or a.ground_floor_level_m.v(),
                        a.ground_floor_level_m.high or a.ground_floor_level_m.v()}:
                ests.append((eaves_h * dh / px - ffl) / ftf)
    nominal = (eaves_h * prior.v() / px - a.ground_floor_level_m.v()) / a.floor_to_floor_m.v()
    value = max(1, int(round(nominal)))
    lo, hi = max(1, int(round(min(ests)))), max(1, int(round(max(ests))))
    return {"value": value, "nominal": nominal, "low": min(lo, value), "high": max(hi, value),
            "robust": lo == hi == value, "ref": label,
            "note": (f"wall height / {label} height = {nominal:.2f} storeys using assumed {label} height "
                     f"{prior.v():.2f} m, floor-to-floor {a.floor_to_floor_m.v():.2f} m, FFL "
                     f"{a.ground_floor_level_m.v():.2f} m")}


def _assign_block(f: DetectedFeature, b: Box, boxes: dict[str, Box], *, roofs_mode: bool = False) -> Optional[str]:
    blk = _norm_block(f.attributes.get("block"))
    if blk and blk in boxes:
        return blk
    if roofs_mode or f.feature_type in (FeatureType.ROOF, FeatureType.EAVES_LINE, FeatureType.RIDGE_LINE,
                                         FeatureType.STOREY_LINE):
        scored = [(_x_overlap_frac(b, fb), -_area(fb), k) for k, fb in boxes.items()
                  if b[3] <= fb[3] + 0.05 * (fb[3] - fb[1])]  # cannot lie below the facade bottom
        scored = [t for t in scored if t[0] >= 0.5]
        return max(scored)[2] if scored else None
    cx, cy = _center(b)
    cands = []
    for k, fb in boxes.items():
        tx, ty = 0.02 * (fb[2] - fb[0]), 0.02 * (fb[3] - fb[1])
        if fb[0] - tx <= cx <= fb[2] + tx and fb[1] - ty <= cy <= fb[3] + ty:
            cands.append(k)
    if not cands:
        return None
    return min(cands, key=lambda k: _area(boxes[k]))


def _pick_line(lines: list[DetectedFeature], block: str, fbox: Box, target_y: float,
               boxes: dict[str, Box]) -> Optional[DetectedFeature]:
    """Line tagged with this block, else an untagged (or foreign-tagged) line overlapping the facade,
    nearest to ``target_y`` at the facade centre."""
    pool = [l for l in lines if _norm_block(l.attributes.get("block")) == block]
    if not pool:
        pool = [l for l in lines if _norm_block(l.attributes.get("block")) not in boxes
                and _x_overlap_frac(_bbox_of(l), fbox) > 0.3]
    if not pool:
        return None
    xc = _center(fbox)[0]
    return min(pool, key=lambda l: (abs(_line_y_at(l, xc) - target_y), -BASIS_RANK[l.basis]))


def _build_facade(ctx: _Ctx, block: str, fac: DetectedFeature, boxes: dict[str, Box],
                  active: list[DetectedFeature], vlm: Optional[VLMExtraction]) -> FacadeObservation:
    a = ctx.asset
    fb = boxes[block]
    x0, y0, x1, y1 = fb
    xc = _center(fb)[0]
    ef = _sig(fac)
    ids: list[str] = [fac.feature_id]
    width = _px(x1 - x0, math.sqrt(2.0) * ef, ctx.basis(fac.basis), source=f"{fac.method} {fac.method_version}",
                evidence=[fac.feature_id], note="Facade bounding-box width (external faces).")

    by_type: dict[FeatureType, list[DetectedFeature]] = defaultdict(list)
    for f in active:
        by_type[f.feature_type].append(f)

    # ---- ground line
    ground = _pick_line(by_type[FeatureType.GROUND_LINE], block, fb, y1, boxes)
    if ground is not None:
        gy, sg, gb = _line_y_at(ground, xc), _sig(ground), ground.basis
        ids.append(ground.feature_id)
    else:
        gy, sg, gb = y1, ef, Basis.INFERRED
        ctx.warnings.append(f"{block}: no ground line detected; the facade box bottom is used as ground level.")

    # ---- roofs for this block
    roofs = [r for r in by_type[FeatureType.ROOF] if r.polygon or r.bbox]
    roofs = [r for r in roofs if _assign_block(r, _bbox_of(r), boxes, roofs_mode=True) == block]
    ids += [r.feature_id for r in roofs]

    # ---- eaves
    eaves_line = _pick_line(by_type[FeatureType.EAVES_LINE], block, fb, y0, boxes)
    eaves_from_line = eaves_line is not None
    if eaves_line is not None:
        ey, se, eb, esrc = _line_y_at(eaves_line, xc), _sig(eaves_line), eaves_line.basis, "eaves line"
        ids.append(eaves_line.feature_id)
    elif roofs:
        ey = max(_bbox_of(r)[3] for r in roofs)
        se, eb, esrc = max(_sig(r) for r in roofs), Basis.INFERRED, "lowest roof edge (no eaves line detected)"
    else:
        ey, se, eb, esrc = y0, ef, Basis.INFERRED, "top of the facade box (no eaves line or roof detected)"
    eaves_h_val = gy - ey
    if eaves_h_val > 0:
        eaves_h = _px(eaves_h_val, math.hypot(sg, se), ctx.basis(gb, eb), source=esrc,
                      evidence=[i for i in (ground.feature_id if ground else None,
                                            eaves_line.feature_id if eaves_line else None) if i],
                      note=f"Ground line to wall plate ({esrc}).")
    else:
        eaves_h = unknown("px", note="eaves at or below ground in the image; not measurable")
        ctx.warnings.append(f"{block}: eaves height is not positive; not measured.")

    # ---- roof form, gable, pitch, ridge axis
    forms = [fm for fm in (_roof_form_attr(r) for r in roofs) if fm]
    roof_form: Optional[str] = None
    roof_basis = Basis.UNKNOWN
    pitch_tv: Optional[TrackedValue] = None
    ridge_axis: Optional[str] = None
    gable_roof = None
    for r in roofs:
        res = _gable_pitch(r, ctx.fu)
        if res is not None:
            gable_roof, pitch = r, res
            break
    if forms:
        roof_form = forms[0] if len(set(forms)) == 1 else "mixed"
    elif gable_roof is not None:
        roof_form = "gable"
    if roof_form is not None:
        src_roofs = roofs if roof_form != "gable" or gable_roof is None else [gable_roof]
        if gable_roof is not None and roof_form == "gable":
            roof_basis = ctx.basis(gable_roof.basis, Basis.OBSERVED)
        else:
            roof_basis = ctx.basis(*[r.basis for r in src_roofs], Basis.INFERRED)
    if gable_roof is not None:
        val, s_deg, note = pitch
        lo, hi = max(0.1, val - 2.0 * s_deg), min(89.9, val + 2.0 * s_deg)
        pitch_tv = TrackedValue(value=val, unit="deg", basis=ctx.basis(gable_roof.basis, Basis.OBSERVED),
                                low=min(lo, val), high=max(hi, val), distribution=Distribution.TRIANGULAR,
                                source=f"{gable_roof.method} {gable_roof.method_version}",
                                evidence_ids=[gable_roof.feature_id], note=note)
        ridge_axis = "perpendicular_to_view"
    for r in roofs:
        hint = r.attributes.get("ridge_orientation")
        if isinstance(hint, str):
            h = hint.strip().lower()
            if h in _PARALLEL:
                ridge_axis = ridge_axis or "parallel_to_view"
            elif h in _PERPENDICULAR:
                ridge_axis = ridge_axis or "perpendicular_to_view"

    # ---- ridge
    ridge_line = _pick_line(by_type[FeatureType.RIDGE_LINE], block, fb, min([y0, *[_bbox_of(r)[1] for r in roofs]]), boxes)
    if ridge_line is not None:
        ry, sr, rb, rsrc = _line_y_at(ridge_line, xc), _sig(ridge_line), ridge_line.basis, "ridge line"
        ids.append(ridge_line.feature_id)
        if ridge_axis is None and (_bbox_of(ridge_line)[2] - _bbox_of(ridge_line)[0]) > 0.5 * (x1 - x0):
            ridge_axis = "parallel_to_view"
    elif roofs:
        top = min(roofs, key=lambda r: _bbox_of(r)[1])
        ry, sr, rb, rsrc = _bbox_of(top)[1], _sig(top), top.basis, "highest roof outline point"
    else:
        ry = None
        sr, rb, rsrc = 0.0, Basis.UNKNOWN, ""
    if ry is not None and gy - ry > 0:
        ridge_h = _px(gy - ry, math.hypot(sg, sr), ctx.basis(gb, rb), source=rsrc,
                      evidence=[i for i in (ground.feature_id if ground else None,
                                            ridge_line.feature_id if ridge_line else None) if i],
                      note=f"Ground line to ridge / roof top ({rsrc}).")
    elif roof_form == "flat" and eaves_h.value is not None:
        ridge_h = eaves_h.model_copy(update={"basis": _cap(weakest_basis(eaves_h.basis, Basis.INFERRED), ctx.concept),
                                             "note": "Flat roof: roof top taken at the eaves line."})
    else:
        ridge_h = unknown("px", note="no ridge line or roof outline detected")

    # ---- openings
    op_feats: list[tuple[DetectedFeature, Box, str]] = []
    for f in active:
        if f.feature_type in OPENING_KINDS and f.bbox is not None:
            b = _bbox_of(f)
            if _assign_block(f, b, boxes) == block:
                kind = OPENING_KINDS[f.feature_type]
                k2 = f.attributes.get("kind")
                if isinstance(k2, str) and k2 in _OPENING_KIND_VALUES:
                    kind = k2
                op_feats.append((f, b, kind))
    ids += [f.feature_id for f, _, _ in op_feats]
    windows = [(f, b) for f, b, k in op_feats if k == "window"]
    roof_level: list[tuple[DetectedFeature, Box]] = []
    if eaves_from_line:
        roof_level = [(f, b) for f, b in windows if _center(b)[1] < ey - 0.25 * (b[3] - b[1])]
        windows = [(f, b) for f, b in windows if (f, b) not in roof_level]
    rows = _cluster_rows(windows)

    # ---- storey lines (strictly between ground and eaves)
    slines = []
    for l in by_type[FeatureType.STOREY_LINE]:
        lb = _bbox_of(l)
        tagged = _norm_block(l.attributes.get("block"))
        if tagged and tagged != block:
            continue
        if not tagged and _x_overlap_frac(lb, fb) < 0.5:
            continue
        yl = _line_y_at(l, xc)
        if ey + 4.0 < yl < gy - 4.0:
            slines.append((l, yl))
    ids += [l.feature_id for l, _ in slines]
    if slines:
        boundaries = sorted((yl for _, yl in slines), reverse=True)
    elif len(rows) >= 2:
        boundaries = []
        for k in range(len(rows) - 1):
            lower_top = min(b[1] for _, b in rows[k])
            upper_bottom = max(b[3] for _, b in rows[k + 1])
            boundaries.append(0.5 * (lower_top + upper_bottom))
    else:
        boundaries = []

    def storey_of(b: Box) -> int:
        cy = _center(b)[1]
        return int(sum(1 for yb in boundaries if yb > cy))

    openings = [ObservedOpening(feature_id=f.feature_id, kind=kind, bbox_px=b, storey_index=storey_of(b),
                                block_hint=block) for f, b, kind in op_feats]

    # ---- storeys
    hest = _storeys_from_height(eaves_h.value, op_feats, ctx.assumptions)
    n_rows = len(rows)
    n_lines = len(slines) + 1 if slines else None
    notes: list[str] = []
    evidence = [f.feature_id for f, _ in windows] + [l.feature_id for l, _ in slines]
    if n_rows or n_lines:
        vals = [v for v in (n_rows or None, n_lines) if v]
        value = max(vals)
        lo, hi = min(vals), max(vals)
        if n_rows:
            notes.append(f"{n_rows} window row(s)")
        if n_lines:
            notes.append(f"{len(slines)} storey line(s) -> {n_lines} storeys")
        if n_rows and n_lines and n_rows != n_lines:
            ctx.warnings.append(f"{block}: window rows ({n_rows}) and storey lines ({n_lines}) disagree; "
                                f"using {value} with range {lo}-{hi}.")
        if hest is not None:
            notes.append(hest["note"])
            if hest["robust"] and hest["value"] != value:
                ctx.warnings.append(f"{block}: wall-height check suggests {hest['value']} storeys vs {value} from "
                                    "window rows/storey lines; range widened.")
                lo, hi = min(lo, hest["value"]), max(hi, hest["value"])
        basis = ctx.basis(*[f.basis for f, _ in windows], *[l.basis for l, _ in slines], Basis.INFERRED)
        storeys = TrackedValue(value=float(value), unit="storeys", basis=basis,
                               low=float(lo) if hi > lo else None, high=float(hi) if hi > lo else None,
                               distribution=Distribution.TRIANGULAR if hi > lo else Distribution.FIXED,
                               source="window-row clustering / storey lines", evidence_ids=evidence,
                               note="; ".join(notes))
    elif hest is not None:
        basis = ctx.basis(Basis.INFERRED if hest["robust"] else Basis.ASSUMED)
        lo, hi = hest["low"], hest["high"]
        storeys = TrackedValue(value=float(hest["value"]), unit="storeys", basis=basis,
                               low=float(lo) if hi > lo else None, high=float(hi) if hi > lo else None,
                               distribution=Distribution.TRIANGULAR if hi > lo else Distribution.FIXED,
                               source=f"wall height relative to {hest['ref']}",
                               evidence_ids=[f.feature_id for f, _, k in op_feats if k in ("door", "garage_door")],
                               note=hest["note"] + ("; robust across the assumed ranges" if hest["robust"] else
                                                    "; depends on the assumed values"))
    else:
        storeys = unknown("storeys", note="no window rows, storey lines or door reference detected")
    if roof_level:
        ctx.warnings.append(f"{block}: {len(roof_level)} window(s) above the eaves line (possible room in roof); "
                            "not counted as a full storey.")

    # ---- finishes (appearance only)
    finishes: dict[tuple[str, str], ObservedFinish] = {}
    roof_boxes = [_bbox_of(r) for r in roofs]
    for f in by_type[FeatureType.FINISH_REGION]:
        b = _bbox_of(f)
        blk = _norm_block(f.attributes.get("block"))
        if blk in boxes:
            if blk != block:
                continue
        else:  # untagged: smallest facade whose x-range contains the region centre (region at or above its bottom)
            cx, cy = _center(b)
            inside = [k for k, bb in boxes.items() if bb[0] <= cx <= bb[2] and cy <= bb[3]]
            if not inside or min(inside, key=lambda k: _area(boxes[k])) != block:
                continue
        appearance = _text_attr(f.attributes.get("appearance")) or _text_attr(f.label)
        if not appearance:
            continue
        element = f.attributes.get("element")
        if element not in FINISH_ELEMENTS:
            element = "roof" if any(_iou(b, rb) > 0.3 for rb in roof_boxes) else "walls"
        basis = Basis.USER_CONFIRMED if f.basis == Basis.USER_CONFIRMED else Basis.INFERRED
        key = (element, appearance)
        if key in finishes:
            finishes[key].feature_ids.append(f.feature_id)
        else:
            finishes[key] = ObservedFinish(element=element, appearance=appearance, basis=_cap(basis, ctx.concept),
                                           feature_ids=[f.feature_id])
        ids.append(f.feature_id)

    # ---- AI-concept consistency checks
    if ctx.ai_concept:
        _concept_checks(ctx, block, fb, rows, op_feats)

    return FacadeObservation(
        image_id=a.image_id, view=ctx.view, block_hint=block, storeys=storeys, width_px=width,
        eaves_height_px=eaves_h, ridge_height_px=ridge_h, ground_y_px=float(gy), left_x_px=float(x0),
        roof_form=roof_form, roof_form_basis=roof_basis, apparent_pitch_deg=pitch_tv,
        ridge_axis_hint=ridge_axis, openings=openings, finishes=list(finishes.values()),
        feature_ids=list(dict.fromkeys(ids)))


def _concept_checks(ctx: _Ctx, block: str, fb: Box, rows: list, op_feats: list) -> None:
    for k, row in enumerate(rows):
        if len(row) < 2:
            continue
        hs = [b[3] - b[1] for _, b in row]
        med = float(np.median(hs))
        heads = [b[1] for _, b in row]
        sills = [b[3] for _, b in row]
        spread_h, spread_s = max(heads) - min(heads), max(sills) - min(sills)
        tol = max(0.25 * med, 6.0)
        if spread_h > tol or spread_s > tol:
            ctx.inconsistencies.append(
                f"{block}: window heads/sills in row {k} (storey {k}) vary by {spread_h:.0f}/{spread_s:.0f} px "
                f"({spread_h / med:.1f}/{spread_s / med:.1f} window heights); rows are not aligned across the facade.")
    for i in range(len(op_feats)):
        for j in range(i + 1, len(op_feats)):
            if _iou(op_feats[i][1], op_feats[j][1]) > 0.05:
                ctx.inconsistencies.append(f"{block}: openings {op_feats[i][0].feature_id} and "
                                           f"{op_feats[j][0].feature_id} overlap.")
    w = fb[2] - fb[0]
    for f, b, _ in op_feats:
        if b[0] < fb[0] - 0.1 * w or b[2] > fb[2] + 0.1 * w or b[3] > fb[3] + 0.1 * (fb[3] - fb[1]):
            ctx.inconsistencies.append(f"{block}: opening {f.feature_id} extends outside its facade.")


def _facades_for_image(ctx: _Ctx, features: list[DetectedFeature],
                       vlm: Optional[VLMExtraction]) -> list[FacadeObservation]:
    active = [f for f in features if f.active]
    facade_feats = [f for f in active if f.feature_type == FeatureType.FACADE and _bbox_of(f) is not None]
    if not facade_feats:
        if any(f.feature_type in OPENING_KINDS for f in active):
            ctx.warnings.append("Openings were detected but no facade extent; annotate the facade box to obtain "
                                "facade measurements.")
        return []
    groups: dict[str, DetectedFeature] = {}
    for f in sorted(facade_feats, key=lambda f: (-BASIS_RANK[f.basis], -(f.confidence or 0.0), f.feature_id)):
        blk = _norm_block(f.attributes.get("block")) or "main"
        if blk in groups:
            ctx.warnings.append(f"More than one facade extent for block '{blk}'; using {groups[blk].feature_id}.")
            continue
        groups[blk] = f
    boxes = {k: _bbox_of(f) for k, f in groups.items()}
    return [_build_facade(ctx, blk, groups[blk], boxes, active, vlm) for blk in sorted(groups, key=lambda k: boxes[k][0])]


def _vlm_crosscheck(asset: ImageAsset, facades: list[FacadeObservation], features: list[DetectedFeature],
                    vlm: VLMExtraction, warnings: list[str]) -> list[FacadeObservation]:
    if not facades:
        if vlm.storeys:
            warnings.append(f"VLM suggests {vlm.storeys} storey(s) (inferred); no facade measurements without "
                            "detections or annotations.")
        return facades
    out = list(facades)
    tallest = max(range(len(out)), key=lambda i: out[i].storeys.value or 0)
    st = out[tallest].storeys
    if vlm.storeys and st.value is not None and int(st.value) != vlm.storeys:
        lo = min(st.low if st.low is not None else st.value, float(vlm.storeys))
        hi = max(st.high if st.high is not None else st.value, float(vlm.storeys))
        warnings.append(f"{out[tallest].block_hint}: VLM storey count {vlm.storeys} differs from detections "
                        f"({int(st.value)}); range widened.")
        out[tallest] = out[tallest].model_copy(update={"storeys": st.model_copy(update={
            "low": lo, "high": hi, "distribution": Distribution.TRIANGULAR,
            "note": (st.note + "; " if st.note else "") + f"VLM cross-check (inferred): {vlm.storeys}"})})
    elif vlm.storeys and st.value is not None:
        out[tallest] = out[tallest].model_copy(update={"storeys": st.model_copy(update={
            "note": (st.note + "; " if st.note else "") + f"VLM cross-check (inferred) agrees: {vlm.storeys}"})})
    if vlm.roof_form and vlm.roof_form not in ("mixed", "unclear"):
        mains = [f for f in out if f.roof_form]
        if mains and all(f.roof_form != vlm.roof_form for f in mains):
            warnings.append(f"VLM roof form '{vlm.roof_form}' differs from detected "
                            f"{sorted({f.roof_form for f in mains})}.")
    n_win = sum(1 for f in features if f.active and f.feature_type == FeatureType.WINDOW)
    if vlm.window_count_visible is not None and n_win and abs(vlm.window_count_visible - n_win) > max(2, 0.3 * n_win):
        warnings.append(f"VLM counts {vlm.window_count_visible} windows; {n_win} were detected/annotated.")
    return out


# =============================================================================
# Public entry point
# =============================================================================
def _concept_status(asset: ImageAsset, features: list[DetectedFeature],
                    vlm: Optional[VLMExtraction]) -> tuple[bool, bool, list[str]]:
    notes: list[str] = []
    kind = asset.kind
    hinted: Optional[ImageKind] = None
    for f in features:
        h = f.attributes.get("image_kind_hint")
        if isinstance(h, str) and h.strip().lower() in CONCEPT_HINTS:
            hinted = CONCEPT_HINTS[h.strip().lower()]
            break
    if hinted is not None and kind not in _CONCEPT_KIND_VALUES:
        notes.append(f"Image annotations mark this image as {hinted.value}; it is treated as a concept reference.")
        kind = hinted
    if vlm is not None and vlm.image_appears_ai_generated and kind not in _CONCEPT_KIND_VALUES:
        notes.append("The VLM (inferred) reports that this image looks AI-generated; treated as a concept reference.")
        kind = ImageKind.AI_CONCEPT
    concept = kind in _CONCEPT_KIND_VALUES
    return concept, kind == ImageKind.AI_CONCEPT, notes


def _label(asset: ImageAsset) -> str:
    return f"{asset.original_filename} ({asset.image_id})"


def analyse_images(images: Sequence[ImageAsset], *, store_dir: Path | str | None,
                   registry: Optional[AdapterRegistry] = None,
                   settings: ProjectSettings | AssumptionLibrary | None = None,
                   manual_features: Optional[Mapping[str, Sequence[DetectedFeature]]] = None,
                   assumptions: Optional[AssumptionLibrary] = None, seed: int = 0) -> AnalysisResult:
    """Analyse ingested images into evidence and pixel-space facade observations.

    ``manual_features`` maps ``image_id`` to user annotations (recorded as
    ``USER_CONFIRMED``; they override overlapping detections).  ``settings`` is
    accepted for interface symmetry (analysis is in pixels); an
    :class:`AssumptionLibrary` passed there is used as ``assumptions`` (door
    height, floor-to-floor, FFL priors for the storey cross-check, perspective
    error fallback).  Deterministic for a given ``seed``.
    """
    if isinstance(settings, AssumptionLibrary) and assumptions is None:
        assumptions = settings
    assumptions = assumptions or AssumptionLibrary()
    registry = registry if registry is not None else default_registry()
    warnings: list[str] = []
    model_versions: dict[str, str] = {ANALYSIS_METHOD: ANALYSIS_VERSION}

    uniq: list[ImageAsset] = []
    seen: set[str] = set()
    for a in images:
        if a.image_id in seen:
            warnings.append(f"Duplicate image {_label(a)} ignored (same content as an earlier image).")
            continue
        seen.add(a.image_id)
        uniq.append(a)
    manual = {k: list(v) for k, v in (manual_features or {}).items()}
    for k in manual:
        if k not in seen:
            warnings.append(f"Manual features supplied for unknown image id {k}; ignored.")

    analyses: list[ImageAnalysis] = []
    facades: list[FacadeObservation] = []
    concept_flags: dict[str, bool] = {}
    for asset in uniq:
        iw: list[str] = []
        rgb = None
        try:
            rgb = load_image_array(asset, store_dir)
        except (ImageRejected, OSError) as exc:
            iw.append(f"Pixel data unavailable ({type(exc).__name__}: {exc}); only adapters that do not need "
                      "pixels were run.")
        runs = []
        taken: set[str] = set()
        features: list[DetectedFeature] = []
        for cap in (Capability.ELEMENT_DETECTION, Capability.SEGMENTATION):
            rr = registry.run(cap, asset, rgb, seed=seed)
            runs += rr.runs
            for outcome in rr.results:
                features += _sanitize_features(asset, outcome.value, outcome.adapter, iw, taken)
        perspective: Optional[PerspectiveEstimate] = None
        rr = registry.run(Capability.PERSPECTIVE, asset, rgb, seed=seed)
        runs += rr.runs
        if isinstance(rr.first, PerspectiveEstimate):
            perspective = rr.first
        depth = None
        if registry.adapters(Capability.DEPTH):
            rr = registry.run(Capability.DEPTH, asset, rgb, seed=seed)
            runs += rr.runs
            depth = rr.first
        vlm: Optional[VLMExtraction] = None
        if registry.adapters(Capability.VLM_EXTRACTION):
            rr = registry.run(Capability.VLM_EXTRACTION, asset, rgb, seed=seed)
            runs += rr.runs
            vlm = rr.first if isinstance(rr.first, VLMExtraction) else None
        if manual.get(asset.image_id):
            features = _merge_manual(asset, features, manual[asset.image_id], iw)
        for run in runs:
            if run.status == "ok":
                model_versions[run.adapter] = run.version
        for f in features:
            model_versions.setdefault(f.method, f.method_version)
        if perspective is not None:
            model_versions.setdefault(perspective.method, perspective.method_version)
        if vlm is not None:
            model_versions[vlm.method] = vlm.model_id

        concept, ai_concept, cnotes = _concept_status(asset, features, vlm)
        iw += cnotes
        concept_flags[asset.image_id] = concept
        if concept:
            kind_label = "AI-generated concept" if ai_concept else (asset.kind.value if asset.kind in
                                                                     _CONCEPT_KIND_VALUES else "concept reference")
            iw.append(f"Concept reference ({kind_label}): geometry may be internally inconsistent; dimensions "
                      "derived from it are indicative only, and its measurements are recorded as inferred, "
                      "not observed.")

        view = asset.view
        img_facades: list[FacadeObservation] = []
        evidence_feats = [f for f in features if f.active and f.feature_type != FeatureType.OTHER]
        if view == ViewDirection.UNKNOWN:
            iw.append("View direction unknown: treated as a FRONT elevation; confirm the view.")
            view = ViewDirection.FRONT
        fu = perspective.foreshortening_uncertainty if perspective is not None else assumptions.perspective_dimension_error
        if perspective is not None and perspective.is_near_fronto_parallel is False:
            iw.append(f"View is not fronto-parallel (obliqueness {perspective.facade_obliqueness_deg} deg, tilt "
                      f"{perspective.vertical_tilt_deg} deg); pixel ratios carry ~{fu:.0%} foreshortening "
                      "uncertainty.")
        if view in ELEVATION_VIEWS:
            ctx = _Ctx(asset, view, concept, ai_concept, fu, assumptions)
            img_facades = _facades_for_image(ctx, features, vlm)
            iw += ctx.warnings
            iw += [f"AI-concept inconsistency: {m}" for m in ctx.inconsistencies]
        elif evidence_feats:
            iw.append(f"View '{view.value}' is not an elevation: features are kept as evidence but no facade "
                      "measurements are made (oblique/plan/aerial views need rectification or plan analysis).")
        if not evidence_feats:
            iw.append("No element detections: no detection fixture matches this image's content and no detector "
                      "adapter produced results. Add manual annotations (manual_features) or enable a detector "
                      "adapter. No facade measurements were produced; nothing was fabricated.")
        if vlm is not None:
            img_facades = _vlm_crosscheck(asset, img_facades, features, vlm, iw)
            if concept and ai_concept:
                iw += [f"AI-concept inconsistency (VLM-reported, inferred): {m}" for m in vlm.geometry_inconsistencies]
        facades += img_facades
        analyses.append(ImageAnalysis(image_id=asset.image_id, features=features, perspective=perspective,
                                      depth=depth, vlm=vlm, adapters=runs, warnings=iw))
        warnings += [f"{_label(asset)}: {w}" for w in iw]

    # ---- primary image
    primary: Optional[str] = None
    for a in uniq:
        if not concept_flags.get(a.image_id) and any(f.image_id == a.image_id and f.view == ViewDirection.FRONT
                                                     for f in facades):
            primary = a.image_id
            break
    if primary is None:
        primary = next((f.image_id for f in facades), uniq[0].image_id if uniq else None)

    # ---- multi-view linking
    multiview = None
    if facades and registry.adapters(Capability.MULTIVIEW) and len({f.image_id for f in facades}) > 1:
        rr = registry.run(Capability.MULTIVIEW, uniq, facades, primary_image_id=primary,
                          load_rgb=lambda a: load_image_array(a, store_dir), seed=seed)
        multiview = rr.first
        for run in rr.runs:
            if run.status == "ok":
                model_versions[run.adapter] = run.version
        if multiview is not None:
            model_versions.setdefault(multiview.method, multiview.method_version)
        target = next((x for x in analyses if x.image_id == primary), analyses[0] if analyses else None)
        if target is not None:
            target.adapters.extend(rr.runs)

    # ---- unknowns
    unknowns = list(BASE_UNKNOWNS)
    real = [f for f in facades if not concept_flags.get(f.image_id)]
    covered = {f.view.value for f in real}
    concept_cov = {f.view.value for f in facades if concept_flags.get(f.image_id)} - covered
    partial = {s for a in uniq if not concept_flags.get(a.image_id) for s in OBLIQUE_COVERAGE.get(a.view, ())}
    missing = [s for s in _SIDES if s not in covered]
    if missing:
        txt = f"Hidden facades not observed in any measured elevation: {', '.join(missing)}"
        extras = []
        if concept_cov & set(missing):
            extras.append(f"seen only in concept references: {', '.join(s for s in missing if s in concept_cov)}")
        if partial & set(missing):
            extras.append(f"seen obliquely but not measured: {', '.join(s for s in missing if s in partial)}")
        if extras:
            txt += f" ({'; '.join(extras)})"
        unknowns.append(txt + ". Openings and finishes there must be assumed or confirmed.")
    linked = multiview.linked_measurements if multiview is not None else {}
    for block in sorted({f.block_hint for f in real}):
        bf = [f for f in real if f.block_hint == block]
        if f"{block}.depth_front_px_equiv" not in linked:
            unknowns.append(f"Plan depth of block '{block}': not observable in the available views (no linked side "
                            "elevation); hidden-footprint hypotheses are required.")
        if not any(f.apparent_pitch_deg is not None for f in bf) and not any(f.roof_form == "flat" for f in bf):
            unknowns.append(f"Roof pitch of block '{block}': no gable end is seen in elevation, so the pitch is not "
                            "directly measurable.")
    if uniq and all(concept_flags.get(a.image_id) for a in uniq):
        warnings.append("All images are concept references: no evidence of an existing or measured building; all "
                        "geometry is indicative.")

    return AnalysisResult(images=uniq, analyses=analyses, facades=facades, multiview=multiview,
                          primary_image_id=primary, unknowns=unknowns, warnings=warnings,
                          model_versions=model_versions)


__all__ = ["analyse_images", "ANALYSIS_VERSION", "BASE_UNKNOWNS", "UNKNOWN_STRUCTURE", "UNKNOWN_INSULATION",
           "UNKNOWN_FOUNDATIONS", "UNKNOWN_SERVICES", "UNKNOWN_ENGINEERING", "UNKNOWN_LAYOUT"]
