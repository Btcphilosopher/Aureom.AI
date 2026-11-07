"""Scale calibration: pixels on the primary elevation -> metres.

:func:`calibrate_scale` returns a :class:`~housebuilder_vision.core.models.ScaleCalibration`
for the *primary image* (``analysis.primary_image_id``, else the image of the
first FRONT facade observation).  Three methods, in order of preference:

1. ``reference_measurement`` - a person supplies a :class:`ReferenceMeasurement`
   (real length + tolerance) and the pixel length is taken from the given
   endpoints ``p0``/``p1``, the referenced feature's bbox width (or line
   length), or - with neither - the width of the main front facade::

       m_per_px = real_m / px
       e_px     = 2 * pixel_uncertainty / px      (one sigma per endpoint, both ends)
       e_tol    = tolerance_m / real_m
       e_persp  = perspective.foreshortening_uncertainty   (else assumptions.perspective_dimension_error)
       hw       = sqrt(e_px**2 + e_tol**2 + e_persp**2)
       low/high = m_per_px * (1 -/+ hw)

   The components are ~2-sigma bounds of independent errors combined in
   quadrature, so the result is stored as ``Distribution.NORMAL`` with
   ``low``/``high`` read as the P5/P95 bounds.  Basis ``INFERRED``: derived from a
   user-confirmed length and observed pixels.  A reference on another image
   is transferred to the primary image through ``multiview.relative_scales``
   when the views are linked (its uncertainty is added in quadrature).
   Prior scale cues are still evaluated and attached as a *cross-check only*.

2. ``dimensioned_plan`` - a ``FLOOR_PLAN`` image whose ``DIMENSION`` features carry
   ``attributes={"length_m": x}``.  Each dimension gives a plan scale (line
   length, else the longer bbox side); they are combined by inverse-variance
   weighting in log space.  The plan scale is transferred to the primary front
   elevation through the plan's ``BUILDING_OUTLINE`` width (assumed to be the
   visible frontage, i.e. the span of all front-visible blocks).  If it cannot
   be transferred the plan result is only used when there is no front
   elevation at all; otherwise it is reported in the notes and the prior cues
   are used.

3. ``prior_cues`` - labelled priors from the :class:`AssumptionLibrary`: door
   leaf height, garage door height, and wall-plate height
   (``storeys * floor_to_floor + ground_floor_level``) against the measured
   eaves height.  Each cue implies an interval::

       mode = prior / px
       low  = prior.low  / (px + band) * (1 - e_persp)
       high = prior.high / (px - band) * (1 + e_persp)

   (``band`` = 2 x per-endpoint pixel sigma, or the +/-2-sigma half range of a
   facade measurement).  Cues are combined as the inverse-variance-weighted
   *geometric* mean of their modes (log-space sigma = ln(high/low)/4); the range
   is the intersection of the cue intervals (never narrower than the combined
   +/-2 sigma) or, if they do not intersect, their union with the warning
   "scale cues disagree".  Basis ``ASSUMED``; ``Distribution.TRIANGULAR``.

With no cue at all the method is ``none`` and the value is ``UNKNOWN``.

Every calibration carries ``correlation_group = "scale:<image_id>"`` so all
dimensions scaled from the same image are sampled with a common driver, and a
note recommending the single most useful calibration measurement.

Boundaries: this is a near-fronto-parallel elevation model.  It is not a
photogrammetric survey; it never claims surveyed accuracy.  All inputs
(references, feature attributes) are treated as untrusted and validated.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from ..core.models import (
    AnalysisResult,
    DetectedFeature,
    FacadeObservation,
    FeatureType,
    ImageKind,
    ReferenceMeasurement,
    ScaleCalibration,
    ScaleCue,
    ViewDirection,
)
from ..core.provenance import Basis, Distribution, TrackedValue
from ..core.settings import AssumptionLibrary
from ..core.units import UnitError, convert

SCALE_UNIT = "m/px"
FRONT_VIEWS = (ViewDirection.FRONT,)
FRONT_LIKE_VIEWS = (ViewDirection.FRONT, ViewDirection.FRONT_LEFT_OBLIQUE, ViewDirection.FRONT_RIGHT_OBLIQUE)
#: Sanity limits for untrusted inputs.
MAX_REFERENCE_M = 1000.0
MAX_PIXELS = 1.0e6
MAX_HALF_WIDTH = 0.9

RECOMMEND_FRONTAGE = ("Most useful calibration measurement: confirm the frontage width of the main facade "
                      "(external corner to external corner, e.g. +/-0.02 m) or upload a dimensioned plan; either "
                      "converts every pixel dimension with a stated tolerance.")
RECOMMEND_DEPTH = ("Scale is calibrated. The next most useful measurement is the plan depth of the main block "
                   "(or a side elevation photograph): depth is hidden in a front view and drives floor, wall and "
                   "roof quantities.")
RECOMMEND_CHECK_PLAN = ("Scale comes from a dimensioned plan; confirm the frontage width on site to check the "
                        "drawing scale and its transfer to the elevation.")


def scale_group(image_id: str) -> str:
    """Correlation group shared by every dimension scaled from ``image_id``."""
    return f"scale:{image_id}"


# =============================================================================
# Lookups
# =============================================================================
def primary_image_id(analysis: AnalysisResult) -> Optional[str]:
    """The image the calibration applies to (primary, else first FRONT facade's image)."""
    known = {i.image_id for i in analysis.images} | {a.image_id for a in analysis.analyses} | \
        {f.image_id for f in analysis.facades}
    if analysis.primary_image_id and analysis.primary_image_id in known:
        return analysis.primary_image_id
    for views in (FRONT_VIEWS, FRONT_LIKE_VIEWS):
        for f in analysis.facades:
            if f.view in views:
                return f.image_id
    if analysis.facades:
        return analysis.facades[0].image_id
    if analysis.images:
        return analysis.images[0].image_id
    return None


def front_facades(analysis: AnalysisResult, image_id: Optional[str]) -> list[FacadeObservation]:
    """FRONT facade observations of ``image_id`` (oblique front views as a fallback)."""
    if image_id is None:
        return []
    for views in (FRONT_VIEWS, FRONT_LIKE_VIEWS):
        fs = [f for f in analysis.facades if f.image_id == image_id and f.view in views]
        if fs:
            return fs
    return []


def main_facade(facades: Sequence[FacadeObservation]) -> Optional[FacadeObservation]:
    """The facade with block hint ``main``, else the widest one."""
    for f in facades:
        if f.block_hint == "main":
            return f
    known = [f for f in facades if f.width_px.value]
    if known:
        return max(known, key=lambda f: f.width_px.value)
    return facades[0] if facades else None


def find_feature(analysis: AnalysisResult, feature_id: str, image_id: Optional[str] = None) -> Optional[DetectedFeature]:
    """Feature by id (active preferred), optionally restricted to one image."""
    hit: Optional[DetectedFeature] = None
    for a in analysis.analyses:
        if image_id is not None and a.image_id != image_id:
            continue
        for f in a.features:
            if f.feature_id == feature_id:
                if f.active:
                    return f
                hit = hit or f
    return hit


def perspective_error(analysis: AnalysisResult, image_id: Optional[str], assumptions: AssumptionLibrary) -> float:
    """Fractional dimension error attributable to perspective for one image."""
    for a in analysis.analyses:
        if a.image_id == image_id and a.perspective is not None:
            v = a.perspective.foreshortening_uncertainty
            if v is not None and math.isfinite(v) and v >= 0:
                return float(min(v, 0.5))
    return float(assumptions.perspective_dimension_error)


def px_band(tv: Optional[TrackedValue], default_pixel_sigma: float) -> float:
    """Half range (px) of a pixel measurement: +/- (high-low)/2, else 2 x per-endpoint sigma."""
    if tv is not None and tv.low is not None and tv.high is not None and tv.high > tv.low:
        return 0.5 * (tv.high - tv.low)
    return 2.0 * default_pixel_sigma


def relative_scale(analysis: AnalysisResult, image_id: str) -> Optional[TrackedValue]:
    """Factor converting ``image_id`` pixels to primary-image pixels (multi-view link), if any."""
    mv = analysis.multiview
    if mv is None:
        return None
    k = mv.relative_scales.get(image_id)
    if k is None or k.value is None or not math.isfinite(k.value) or k.value <= 0:
        return None
    return k


def _finite_positive(v: Any) -> Optional[float]:
    if isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) and f > 0 else None


def _rel_half(tv: TrackedValue) -> float:
    if tv.value and tv.low is not None and tv.high is not None:
        return 0.5 * (tv.high - tv.low) / tv.value
    return 0.0


# =============================================================================
# Reference resolution
# =============================================================================
@dataclass(frozen=True)
class ResolvedReference:
    """A validated reference measurement expressed in pixels and metres."""

    image_id: str
    pixels: float
    #: Per-endpoint 1-sigma pixel error.
    pixel_uncertainty: float
    real_m: float
    tolerance_m: float
    #: "points", "feature:<id>" or "facade:<block_hint>".
    target: str
    #: Block hint of the facade whose full width the reference spans (else None).
    facade_block_hint: Optional[str] = None
    evidence_ids: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_facade_width(self) -> bool:
        return self.facade_block_hint is not None


def _to_metres(value: float, unit: str, what: str) -> float:
    try:
        return convert(float(value), unit, "m")
    except UnitError as exc:
        raise ValueError(f"reference {what} unit '{unit}' is not a length unit: {exc}") from None


def resolve_reference(analysis: AnalysisResult, reference: ReferenceMeasurement, *,
                      assumptions: Optional[AssumptionLibrary] = None) -> ResolvedReference:
    """Validate ``reference`` against ``analysis`` and express it in pixels and metres.

    Raises ``ValueError`` for unknown images/features, non-length units, absurd
    lengths, or zero pixel length.
    """
    A = assumptions or AssumptionLibrary()
    known = {i.image_id for i in analysis.images} | {a.image_id for a in analysis.analyses} | \
        {f.image_id for f in analysis.facades}
    if reference.image_id not in known:
        raise ValueError(f"reference image '{reference.image_id}' is not part of the analysis")
    real_m = _to_metres(reference.real_length, reference.unit, "length")
    tol_m = abs(_to_metres(reference.tolerance, reference.unit, "tolerance"))
    if not (math.isfinite(real_m) and 0 < real_m <= MAX_REFERENCE_M):
        raise ValueError(f"reference length {real_m} m is outside (0, {MAX_REFERENCE_M}] m")
    if not math.isfinite(tol_m) or tol_m >= real_m:
        raise ValueError("reference tolerance must be finite and smaller than the length")
    facades = [f for f in analysis.facades if f.image_id == reference.image_id]
    fronts = front_facades(analysis, reference.image_id) or facades
    pu_default = float(A.pixel_measurement_error_px)

    if (reference.p0 is None) != (reference.p1 is None):
        raise ValueError("reference needs both p0 and p1 (or neither)")
    if reference.p0 is not None and reference.p1 is not None:
        (x0, y0), (x1, y1) = reference.p0, reference.p1
        vals = [x0, y0, x1, y1]
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in vals):
            raise ValueError("reference endpoints must be finite numbers")
        px = math.hypot(x1 - x0, y1 - y0)
        hint = None
        if px > 0 and abs(y1 - y0) <= 0.05 * px:  # horizontal: does it span a facade?
            xa, xb = sorted((x0, x1))
            for f in facades:
                if f.left_x_px is None or not f.width_px.value:
                    continue
                w = f.width_px.value
                tol = max(3.0 * 0.5 * px_band(f.width_px, pu_default), 0.01 * w)
                if abs(xa - f.left_x_px) <= tol and abs(xb - (f.left_x_px + w)) <= tol:
                    hint = f.block_hint
                    break
        res = ResolvedReference(reference.image_id, px, pu_default, real_m, tol_m, "points", hint, ())
    elif reference.feature_id:
        fid = reference.feature_id
        feat = find_feature(analysis, fid, reference.image_id)
        if feat is not None:
            px = feat.width_px()
            if px is None:
                raise ValueError(f"reference feature '{fid}' has no bbox or line to measure")
            hint = None
            if feat.feature_type in (FeatureType.FACADE, FeatureType.BUILDING_OUTLINE, FeatureType.WALL):
                for f in facades:
                    if fid in f.feature_ids:
                        hint = f.block_hint
                        break
            res = ResolvedReference(reference.image_id, float(px), float(feat.pixel_uncertainty), real_m, tol_m,
                                    f"feature:{fid}", hint, (fid,))
        else:
            name = fid.split(":", 1)[1] if fid.startswith("facade:") else fid
            fac = next((f for f in facades if f.block_hint == name), None)
            if fac is None or not fac.width_px.value:
                raise ValueError(f"reference feature '{fid}' not found in image '{reference.image_id}'")
            res = ResolvedReference(reference.image_id, float(fac.width_px.value),
                                    0.5 * px_band(fac.width_px, pu_default), real_m, tol_m,
                                    f"facade:{fac.block_hint}", fac.block_hint, tuple(fac.feature_ids[:1]))
    else:
        fac = main_facade(fronts)
        if fac is None or not fac.width_px.value:
            raise ValueError("reference has neither endpoints nor a feature, and no facade width is available")
        res = ResolvedReference(reference.image_id, float(fac.width_px.value),
                                0.5 * px_band(fac.width_px, pu_default), real_m, tol_m,
                                f"facade:{fac.block_hint}", fac.block_hint, tuple(fac.feature_ids[:1]))
    if not (math.isfinite(res.pixels) and 0 < res.pixels <= MAX_PIXELS):
        raise ValueError(f"reference pixel length {res.pixels} is not usable")
    return res


# =============================================================================
# Prior cues
# =============================================================================
def _cue(name: str, feature_id: Optional[str], px: float, band: float, prior: TrackedValue,
         e_persp: float, evidence: Sequence[str] = ()) -> Optional[ScaleCue]:
    if not px or px <= 0 or prior.value is None:
        return None
    lo_px = max(px - band, 0.5 * px)
    hi_px = px + band
    p_lo = prior.low if prior.low is not None else prior.value
    p_hi = prior.high if prior.high is not None else prior.value
    mode = prior.value / px
    low = min(mode, p_lo / hi_px * (1.0 - e_persp))
    high = max(mode, p_hi / lo_px * (1.0 + e_persp))
    implied = TrackedValue(
        value=mode, unit=SCALE_UNIT, basis=Basis.ASSUMED, low=low, high=high,
        distribution=Distribution.TRIANGULAR, source=f"prior cue: {name}",
        evidence_ids=[e for e in (feature_id, *evidence) if e],
        note=(f"{prior.value:.2f} m ({p_lo:.2f}-{p_hi:.2f}) assumed over {px:.1f} +/- {band:.1f} px, "
              f"perspective +/-{e_persp:.0%}."))
    return ScaleCue(name=name, feature_id=feature_id, pixels=float(px),
                    assumed_real=prior.model_copy(update={"basis": Basis.ASSUMED}, deep=True),
                    implied_m_per_px=implied)


def _median_opening(facades: Sequence[FacadeObservation], kind: str):
    items = []
    for f in facades:
        for o in f.openings:
            if o.kind == kind:
                h = o.bbox_px[3] - o.bbox_px[1]
                if h > 0:
                    items.append((h, o.feature_id, o))
    if not items:
        return None
    items.sort(key=lambda t: (t[0], t[1]))
    return items[len(items) // 2]


def prior_scale_cues(analysis: AnalysisResult, image_id: Optional[str],
                     assumptions: Optional[AssumptionLibrary] = None) -> tuple[list[ScaleCue], list[str]]:
    """Scale cues from labelled priors on ``image_id`` (door, garage door, wall-plate height)."""
    A = assumptions or AssumptionLibrary()
    notes: list[str] = []
    facades = front_facades(analysis, image_id) or [f for f in analysis.facades if f.image_id == image_id]
    if not facades:
        return [], notes
    e_persp = perspective_error(analysis, image_id, A)
    pu_default = float(A.pixel_measurement_error_px)
    cues: list[ScaleCue] = []

    def pu_of(fid: str) -> float:
        feat = find_feature(analysis, fid, image_id)
        return float(feat.pixel_uncertainty) if feat is not None else pu_default

    for kind, prior, label in (("door", A.door_leaf_height_m, "door leaf height"),
                               ("garage_door", A.garage_door_height_m, "garage door height")):
        hit = _median_opening(facades, kind)
        if hit is not None:
            h, fid, _ = hit
            c = _cue(label, fid, h, 2.0 * pu_of(fid), prior, e_persp)
            if c is not None:
                cues.append(c)

    main = main_facade(facades)
    if main is not None and main.eaves_height_px.value and main.eaves_height_px.value > 0:
        st = main.storeys
        if st.value is not None and st.value >= 1:
            n = max(1, int(round(st.value)))
            n_lo = max(1, int(round(st.low))) if st.low is not None else n
            n_hi = max(n, int(round(st.high))) if st.high is not None else n
            storey_note = f"{n} storey(s) from the facade observation ({st.basis.value})"
        else:
            n, n_lo, n_hi = 2, 1, 3
            storey_note = "storey count unknown: 2 assumed (1-3)"
            notes.append("Wall-plate scale cue uses an assumed storey count (2, range 1-3); it is weak.")
        ftf, ffl = A.floor_to_floor_m, A.ground_floor_level_m
        real = TrackedValue(
            value=ffl.value + n * ftf.value, unit="m", basis=Basis.ASSUMED,
            low=min(ffl.value + n * ftf.value, ffl.low + n_lo * ftf.low),
            high=max(ffl.value + n * ftf.value, ffl.high + n_hi * ftf.high),
            distribution=Distribution.TRIANGULAR, source=ftf.source,
            note=f"Wall plate = FFL + storeys x floor-to-floor; {storey_note}.")
        band = px_band(main.eaves_height_px, pu_default)
        c = _cue(f"wall plate height ({main.block_hint})", None, main.eaves_height_px.value, band, real, e_persp,
                 evidence=main.eaves_height_px.evidence_ids or main.feature_ids[:1])
        if c is not None:
            cues.append(c)
    return cues, notes


def combine_cues(cues: Sequence[ScaleCue], image_id: str) -> tuple[TrackedValue, list[str]]:
    """Inverse-variance geometric mean of cue modes; range = intersection (else union + warning)."""
    notes: list[str] = []
    logs, ws, lows, highs = [], [], [], []
    for c in cues:
        t = c.implied_m_per_px
        lo, hi = t.low or t.value, t.high or t.value
        s = max((math.log(hi) - math.log(lo)) / 4.0, 1e-6)
        logs.append(math.log(t.value))
        ws.append(1.0 / (s * s))
        lows.append(lo)
        highs.append(hi)
    lm = sum(w * l for w, l in zip(ws, logs)) / sum(ws)
    mode = math.exp(lm)
    sc = 1.0 / math.sqrt(sum(ws))
    lo_i, hi_i = max(lows), min(highs)
    if lo_i <= hi_i:
        low = min(lo_i, mode * math.exp(-2.0 * sc))
        high = max(hi_i, mode * math.exp(2.0 * sc))
        how = "intersection of cue intervals"
    else:
        low, high = min(lows), max(highs)
        how = "union of cue intervals"
        notes.append("Warning: scale cues disagree (their intervals do not overlap: "
                     + "; ".join(f"{c.name} {c.implied_m_per_px.low:.5f}-{c.implied_m_per_px.high:.5f}"
                                 for c in cues)
                     + "). The union is used; check door/storey detections or add a reference measurement.")
    mode = min(max(mode, low), high)
    tv = TrackedValue(
        value=mode, unit=SCALE_UNIT, basis=Basis.ASSUMED, low=low, high=high,
        distribution=Distribution.TRIANGULAR, correlation_group=scale_group(image_id), source="prior_cues",
        evidence_ids=[e for c in cues for e in c.implied_m_per_px.evidence_ids],
        note=(f"Inverse-variance geometric mean of {len(cues)} prior cue(s); range = {how}. "
              "Assumption-based scale: dimensions derived from it are ASSUMED."))
    return tv, notes


# =============================================================================
# Dimensioned plan
# =============================================================================
def _plan_scale(analysis: AnalysisResult, A: AssumptionLibrary) -> Optional[dict[str, Any]]:
    best: Optional[dict[str, Any]] = None
    feats_by_img = {a.image_id: [f for f in a.features if f.active] for a in analysis.analyses}
    for img in analysis.images:
        if img.kind != ImageKind.FLOOR_PLAN:
            continue
        cues: list[ScaleCue] = []
        notes: list[str] = []
        for f in feats_by_img.get(img.image_id, []):
            if f.feature_type != FeatureType.DIMENSION or "length_m" not in f.attributes:
                continue
            length = _finite_positive(f.attributes.get("length_m"))
            if length is None or length > MAX_REFERENCE_M:
                notes.append(f"Plan dimension {f.feature_id}: invalid length_m ignored.")
                continue
            if f.line is not None:
                px = math.hypot(f.line[2] - f.line[0], f.line[3] - f.line[1])
            elif f.bbox is not None:
                px = max(f.bbox[2] - f.bbox[0], f.bbox[3] - f.bbox[1])
            else:
                px = 0.0
            if not (0 < px <= MAX_PIXELS):
                notes.append(f"Plan dimension {f.feature_id}: no measurable pixel length; ignored.")
                continue
            e_px = 2.0 * float(f.pixel_uncertainty) / px
            v = length / px
            rb = f.basis if f.basis in (Basis.OBSERVED, Basis.USER_CONFIRMED) else Basis.INFERRED
            cues.append(ScaleCue(
                name=f"plan dimension {f.label or f.feature_id}"[:120], feature_id=f.feature_id, pixels=px,
                assumed_real=TrackedValue(value=length, unit="m", basis=rb, distribution=Distribution.FIXED,
                                          source="dimension annotation on plan", evidence_ids=[f.feature_id]),
                implied_m_per_px=TrackedValue(value=v, unit=SCALE_UNIT, basis=Basis.INFERRED,
                                              low=v * (1 - e_px), high=v * (1 + e_px),
                                              distribution=Distribution.NORMAL, source="dimensioned_plan",
                                              evidence_ids=[f.feature_id])))
        if cues and (best is None or len(cues) > len(best["cues"])):
            best = {"image_id": img.image_id, "cues": cues, "notes": notes,
                    "outline": next((f for f in feats_by_img.get(img.image_id, [])
                                     if f.feature_type == FeatureType.BUILDING_OUTLINE and f.bbox), None)}
    if best is None:
        return None
    logs, ws = [], []
    for c in best["cues"]:
        t = c.implied_m_per_px
        s = max(0.5 * _rel_half(t), 1e-4)
        logs.append(math.log(t.value))
        ws.append(1.0 / (s * s))
    v = math.exp(sum(w * l for w, l in zip(ws, logs)) / sum(ws))
    e = 2.0 / math.sqrt(sum(ws))
    vals = [c.implied_m_per_px.value for c in best["cues"]]
    spread = (max(vals) - min(vals)) / v
    if spread > 2.0 * e:
        best["notes"].append(f"Plan dimensions imply scales differing by {spread:.1%}; uncertainty widened.")
        e = max(e, 0.5 * spread)
    best["value"], best["e"] = v, e
    return best


# =============================================================================
# Public entry point
# =============================================================================
def calibrate_scale(analysis: AnalysisResult, reference: Optional[ReferenceMeasurement] = None, *,
                    assumptions: Optional[AssumptionLibrary] = None) -> ScaleCalibration:
    """Calibrate metres-per-pixel for the primary image (see module docstring)."""
    A = assumptions or AssumptionLibrary()
    primary = primary_image_id(analysis)
    if reference is not None:
        return _from_reference(analysis, reference, primary, A)
    plan = _plan_scale(analysis, A)
    plan_notes: list[str] = []
    if plan is not None:
        cal = _from_plan(analysis, plan, primary, A)
        if cal is not None:
            return cal
        plan_notes = list(plan["notes"]) + [
            f"Dimensioned plan {plan['image_id']} gives {plan['value']:.5f} m/px on the plan, but it could not be "
            "transferred to the front elevation (no BUILDING_OUTLINE on the plan or no front facade); "
            "prior cues are used for the elevation."]
    return _from_priors(analysis, primary, A, extra_notes=plan_notes)


def _from_reference(analysis: AnalysisResult, reference: ReferenceMeasurement, primary: Optional[str],
                    A: AssumptionLibrary) -> ScaleCalibration:
    rr = resolve_reference(analysis, reference, assumptions=A)
    e_px = 2.0 * rr.pixel_uncertainty / rr.pixels
    e_tol = rr.tolerance_m / rr.real_m
    e_persp = perspective_error(analysis, rr.image_id, A)
    hw = math.sqrt(e_px ** 2 + e_tol ** 2 + e_persp ** 2)
    value = rr.real_m / rr.pixels
    image_id = rr.image_id
    notes = [f"Reference {rr.real_m:.3f} m +/- {rr.tolerance_m:.3f} m over {rr.pixels:.1f} px ({rr.target}); "
             f"errors: pixels {e_px:.2%}, tolerance {e_tol:.2%}, perspective {e_persp:.2%} -> +/-{hw:.2%} "
             "(NORMAL, low/high = P5/P95)."]
    if rr.is_facade_width:
        notes.append(f"The reference spans the full width of the '{rr.facade_block_hint}' facade.")
    evidence = list(rr.evidence_ids)
    if primary is not None and rr.image_id != primary:
        k = relative_scale(analysis, rr.image_id)
        if k is not None:
            e_k = _rel_half(k)
            value = value / k.value
            hw = math.sqrt(hw ** 2 + e_k ** 2)
            notes.append(f"Reference measured on {rr.image_id}; transferred to the primary image {primary} with "
                         f"the multi-view relative scale {k.value:.4f} (+/-{e_k:.2%}).")
            image_id = primary
            evidence += list(k.evidence_ids)
        else:
            notes.append(f"Reference is on image {rr.image_id}, which is not linked to the primary image "
                         f"{primary}; the calibration applies to {rr.image_id} only.")
    hw = min(hw, MAX_HALF_WIDTH)
    tv = TrackedValue(
        value=value, unit=SCALE_UNIT, basis=Basis.INFERRED, low=value * (1 - hw), high=value * (1 + hw),
        distribution=Distribution.NORMAL, correlation_group=scale_group(image_id), source="reference_measurement",
        evidence_ids=list(dict.fromkeys(evidence)),
        note=("Derived from a user-confirmed reference length and observed pixels (INFERRED). "
              + (reference.description[:200] if reference.description else "")).strip())
    cues, cue_notes = prior_scale_cues(analysis, image_id, A)
    if cues:
        ctv, _ = combine_cues(cues, image_id)
        ok = ctv.low <= value <= ctv.high
        notes.append(f"Cross-check only: prior cues imply {ctv.value:.5f} m/px ({ctv.low:.5f}-{ctv.high:.5f}); "
                     + ("consistent with the reference." if ok else
                        "INCONSISTENT with the reference - check the reference or the detections."))
    notes.append(RECOMMEND_DEPTH if rr.is_facade_width else RECOMMEND_FRONTAGE)
    return ScaleCalibration(image_id=image_id, method="reference_measurement", metres_per_pixel=tv,
                            reference=reference.model_copy(deep=True), cues=cues, notes=notes)


def _from_plan(analysis: AnalysisResult, plan: dict[str, Any], primary: Optional[str],
               A: AssumptionLibrary) -> Optional[ScaleCalibration]:
    v, e = plan["value"], plan["e"]
    notes = list(plan["notes"])
    target = primary if primary != plan["image_id"] and front_facades(analysis, primary) else next(
        (f.image_id for f in analysis.facades if f.view == ViewDirection.FRONT and f.image_id != plan["image_id"]),
        None)
    fronts = front_facades(analysis, target)
    primary = target if target is not None else primary
    outline: Optional[DetectedFeature] = plan["outline"]
    measurable = [f for f in fronts if f.left_x_px is not None and f.width_px.value]
    if outline is not None and measurable:
        ow = outline.bbox[2] - outline.bbox[0]
        x0 = min(f.left_x_px for f in measurable)
        x1 = max(f.left_x_px + f.width_px.value for f in measurable)
        span = x1 - x0
        if ow > 0 and span > 0:
            frontage = ow * v
            pu = float(A.pixel_measurement_error_px)
            e_out = 2.0 * float(outline.pixel_uncertainty) / ow
            e_span = 2.0 * pu / span
            e_persp = perspective_error(analysis, primary, A)
            hw = min(math.sqrt(e ** 2 + e_out ** 2 + e_span ** 2 + e_persp ** 2), MAX_HALF_WIDTH)
            val = frontage / span
            notes.append(f"Plan scale {v:.5f} m/px ({len(plan['cues'])} dimension(s), +/-{e:.2%}); plan outline "
                         f"width {frontage:.2f} m transferred to the front elevation span of {span:.1f} px. "
                         "Assumes the outline's horizontal extent is the visible frontage of all front blocks.")
            notes.append(RECOMMEND_CHECK_PLAN)
            tv = TrackedValue(value=val, unit=SCALE_UNIT, basis=Basis.INFERRED, low=val * (1 - hw),
                              high=val * (1 + hw), distribution=Distribution.NORMAL,
                              correlation_group=scale_group(primary), source="dimensioned_plan",
                              evidence_ids=[c.feature_id for c in plan["cues"] if c.feature_id] + [outline.feature_id],
                              note="Derived from plan dimension annotations and observed pixels (INFERRED).")
            return ScaleCalibration(image_id=primary, method="dimensioned_plan", metres_per_pixel=tv,
                                    cues=plan["cues"], notes=notes)
    if primary is None or primary == plan["image_id"] or not fronts:
        notes.append(f"Plan scale {v:.5f} m/px from {len(plan['cues'])} dimension(s); applies to the plan image only.")
        notes.append(RECOMMEND_CHECK_PLAN)
        tv = TrackedValue(value=v, unit=SCALE_UNIT, basis=Basis.INFERRED, low=v * (1 - e), high=v * (1 + e),
                          distribution=Distribution.NORMAL, correlation_group=scale_group(plan["image_id"]),
                          source="dimensioned_plan",
                          evidence_ids=[c.feature_id for c in plan["cues"] if c.feature_id],
                          note="Derived from plan dimension annotations (INFERRED).")
        return ScaleCalibration(image_id=plan["image_id"], method="dimensioned_plan", metres_per_pixel=tv,
                                cues=plan["cues"], notes=notes)
    return None


def _from_priors(analysis: AnalysisResult, primary: Optional[str], A: AssumptionLibrary, *,
                 extra_notes: Sequence[str] = ()) -> ScaleCalibration:
    image_id = primary or "unknown"
    cues, notes = prior_scale_cues(analysis, primary, A)
    notes = list(extra_notes) + notes
    if not cues:
        notes.append("No scale cue was found (no door, garage door or measurable wall-plate height): metres per "
                     "pixel is UNKNOWN. Please add a calibration measurement (a confirmed real dimension).")
        notes.append(RECOMMEND_FRONTAGE)
        tv = TrackedValue(value=None, unit=SCALE_UNIT, basis=Basis.UNKNOWN, distribution=Distribution.FIXED,
                          correlation_group=scale_group(image_id), source="none",
                          note="No calibration measurement and no prior scale cue.")
        return ScaleCalibration(image_id=image_id, method="none", metres_per_pixel=tv, notes=notes)
    tv, cnotes = combine_cues(cues, image_id)
    notes += cnotes
    notes.append(f"Scale from labelled prior cues ({', '.join(c.name for c in cues)}): an assumption, not a "
                 f"measurement; range {tv.low:.5f}-{tv.high:.5f} m/px (+/-{0.5 * tv.relative_spread():.1%}).")
    notes.append(RECOMMEND_FRONTAGE)
    return ScaleCalibration(image_id=image_id, method="prior_cues", metres_per_pixel=tv, cues=cues, notes=notes)


def prior_cue_calibration(analysis: AnalysisResult, image_id: Optional[str], *,
                          assumptions: Optional[AssumptionLibrary] = None) -> ScaleCalibration:
    """Prior-cue (or ``none``) calibration of a specific image, ignoring references and plans."""
    return _from_priors(analysis, image_id, assumptions or AssumptionLibrary())


__all__ = [
    "ResolvedReference",
    "SCALE_UNIT",
    "calibrate_scale",
    "combine_cues",
    "find_feature",
    "front_facades",
    "main_facade",
    "perspective_error",
    "primary_image_id",
    "prior_cue_calibration",
    "prior_scale_cues",
    "px_band",
    "relative_scale",
    "resolve_reference",
    "scale_group",
]
