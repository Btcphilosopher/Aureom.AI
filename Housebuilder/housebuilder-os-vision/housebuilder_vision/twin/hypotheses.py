"""Hidden-footprint geometry hypotheses from calibrated facade observations.

:func:`generate_geometry_hypotheses` turns the pixel-space
:class:`~housebuilder_vision.core.models.FacadeObservation` objects of the front
elevation (one per visible block: ``main``, ``garage``, ``extension``, ...),
optional multi-view links and the labelled priors of the
:class:`~housebuilder_vision.core.settings.AssumptionLibrary` into competing
parametric hypotheses (:class:`GeometryHypothesis`).  A single front view
cannot show plan depth, so the hypotheses differ in what is hidden:

``H-A`` "Rectangular plan"
    main depth from the observed ridge rise and the pitch prior,
    ``depth = 2 * rise / tan(pitch)`` (range from the pitch prior range, clipped
    to the depth/width prior range; if the value itself is clipped the pitch
    is re-derived from the rise so the roof still reproduces it); without a
    visible rise, ``depth = width * depth_to_width``.  Depth and pitch are
    *coupled*: the observed rise is stored on the roof
    (``RoofSpec.observed_rise_m``) and ``twin.builder.apply_twin_edit``
    re-derives the other value when either is edited.
``H-B`` "L-shaped: shallower main + single-storey rear extension"
    ``main depth = max(0.6 * width, depth_A - 1.2 m)`` (assumed), pitch implied
    by the same observed rise ``atan(2 * rise / depth)``, plus a heated
    single-storey flat-roofed extension (0.5 x main width by 3.60 m, assumed)
    attached at the rear-left corner (rear-right when the left side was seen in
    another view).  For the demo house: 9.60 x 7.20 m + 4.80 x 3.60 m.
``H-C`` "Deep plan / shallow pitch" (uncalibrated runs only)
    depth from the *low* pitch bound (clipped to the depth/width prior maximum),
    pitch implied by the observed rise.

When a linked side elevation (``multiview.linked_measurements``) shows the
block depth and/or gable pitch, the depth is no longer hidden: H-A uses the
observed depth (narrow range) and only one alternative is kept (a hidden rear
extension), so fewer hypotheses are produced.

Provenance rules
----------------
* metres = px x scale.  Ranges combine the scale range and the pixel error in
  quadrature; every scale-derived value carries
  ``correlation_group = "scale:<image_id>"`` (one common driver per image).
* Basis is ``INFERRED`` when the scale comes from a reference measurement or a
  dimensioned plan and ``ASSUMED`` when it comes from prior cues.  When the
  reference *is* the main facade width, the main width is ``USER_CONFIRMED``
  (value = reference, range = tolerance).
* Storeys come from the observation; floor-to-floor = (eaves - FFL) / storeys
  when calibrated, otherwise the prior.  FFL is always the prior
  (``ASSUMED``), so the floor-to-floor and every opening sill (bottom above
  ground - FFL - storey x floor-to-floor) take ``ASSUMED`` too (weakest basis;
  the notes say which part was observed).  A hidden rear extension copies the
  main block's floor-to-floor and FFL as ``ASSUMED`` values without evidence.
* Pixel lengths (opening sizes and positions, overhangs, block offsets) use the
  +/-2-sigma band of a length between two edges, ``2 x sqrt(2) x`` the
  per-edge pixel sigma (``calibration.length_band``).
* When the front view shows the roof band of a ridge parallel to the frontage,
  the rise (``INFERRED`` with a calibrated scale, else ``ASSUMED``) is stored on
  the main block's roof as ``observed_rise_m`` with its evidence ids, in every
  hypothesis that uses it (H-A, H-B, H-C and the side-view variants).
* Pitch is ``OBSERVED`` only when a gable is seen in elevation (front gable or
  linked side view); otherwise it is the prior or implied by an assumed depth
  (``ASSUMED``).
* Everything not visible (depths, rear extension, garage depth 6.0 m
  (5.0-7.0), unheated garage, flush front faces, hidden facades) is
  ``ASSUMED`` and listed in the hypothesis notes.
* ``plausibility`` is a subjective prior weight (not a calibrated probability).

Boundaries: hypotheses describe geometry only.  They make no structural,
compliance or survey claim and never infer construction from appearance.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

from ..core.models import (
    AnalysisResult,
    Block,
    BlockRole,
    FacadeObservation,
    GeometryHypothesis,
    HiddenSideAssumptions,
    Opening,
    OpeningKind,
    RoofForm,
    RoofSpec,
    ScaleCalibration,
    Side,
    ViewDirection,
)
from ..core.provenance import Basis, Distribution, TrackedValue, assumed, weakest_basis
from ..core.settings import AssumptionLibrary, ProjectSettings
from ..geometry.footprint import GeometryError, Rect, validate_rects
from .builder import block_coupling
from .calibration import (
    find_feature,
    front_facades,
    length_band,
    main_facade,
    prior_cue_calibration,
    primary_image_id,
    px_band,
    relative_scale,
    resolve_reference,
    scale_group,
)

#: Subjective prior weights (not calibrated probabilities).
PLAUSIBILITY_UNCALIBRATED = {"H-A": 0.50, "H-B": 0.35, "H-C": 0.15}
PLAUSIBILITY_CALIBRATED = {"H-A": 0.60, "H-B": 0.40}
PLAUSIBILITY_DEPTH_OBSERVED = {"H-A": 0.75, "H-B": 0.25}

SNAP_GAP_M = 0.30
MIN_DEPTH_FRACTION = 0.60  # of main width
H_B_DEPTH_REDUCTION_M = 1.20
EXT_WIDTH_FRACTION = (0.50, 0.40, 0.70)
EXT_DEPTH_M = (3.60, 3.00, 4.50)
GARAGE_DEPTH_M = (6.00, 5.00, 7.00)
WING_DEPTH_FRACTION = (0.80, 0.50, 1.00)  # of H-A main depth
FTF_PLAUSIBLE = (2.0, 4.5)
MAX_OVERHANG_M = 1.0
PITCH_LIMITS = (1.0, 74.0)
SOURCE = "twin.hypotheses"

_FORMS = {
    "gable": RoofForm.GABLE, "gabled": RoofForm.GABLE, "pitched": RoofForm.GABLE,
    "hip": RoofForm.HIP, "hipped": RoofForm.HIP,
    "flat": RoofForm.FLAT,
    "monopitch": RoofForm.MONOPITCH, "mono-pitch": RoofForm.MONOPITCH, "mono_pitch": RoofForm.MONOPITCH,
    "lean-to": RoofForm.MONOPITCH, "lean_to": RoofForm.MONOPITCH, "pent": RoofForm.MONOPITCH,
}
_SIDE_OF_VIEW = {ViewDirection.LEFT: Side.LEFT, ViewDirection.RIGHT: Side.RIGHT, ViewDirection.REAR: Side.REAR}


# =============================================================================
# Small helpers
# =============================================================================
def _tv(value: float, unit: str, basis: Basis, low: Optional[float] = None, high: Optional[float] = None, *,
        group: Optional[str] = None, source: str = SOURCE, evidence: Iterable[str] = (), note: str = "",
        distribution: Distribution = Distribution.TRIANGULAR) -> TrackedValue:
    """TrackedValue whose range is sorted and always contains the value."""
    if low is not None and high is not None:
        low, high = min(low, high), max(low, high)
        low, high = min(low, value), max(high, value)
    if low is None or high is None or high - low <= 1e-12:
        low = high = None
        distribution = Distribution.FIXED
    return TrackedValue(value=value, unit=unit, basis=basis, low=low, high=high, distribution=distribution,
                        correlation_group=group, source=source, evidence_ids=list(dict.fromkeys(evidence)),
                        note=note)


def _lo(tv: TrackedValue) -> float:
    return tv.low if tv.low is not None else tv.value


def _hi(tv: TrackedValue) -> float:
    return tv.high if tv.high is not None else tv.value


def _datum(note: str) -> TrackedValue:
    return TrackedValue(value=0.0, unit="m", basis=Basis.INFERRED, distribution=Distribution.FIXED,
                        source="coordinate datum", note=note)


def _safe_id(text: str, used: set[str], fallback: str = "block", limit: int = 40) -> str:
    base = re.sub(r"[^A-Za-z0-9_.\-]", "_", text or "")[:limit].strip("_.-") or fallback
    out, n = base, 2
    while out in used:
        out = f"{base[:limit - 4]}_{n}"
        n += 1
    used.add(out)
    return out


def _opening_id(feature_id: str, used: set[str]) -> str:
    base = "obs:" + re.sub(r"[^A-Za-z0-9_.:\-]", "_", feature_id or "opening")[:70]
    out, n = base, 2
    while out in used:
        out = f"{base[:74]}~{n}"[:80]
        n += 1
    used.add(out)
    return out


def _copy_prior(tv: TrackedValue, note: str = "") -> TrackedValue:
    upd = {"basis": Basis.ASSUMED}
    if note:
        upd["note"] = (tv.note + " " + note).strip() if tv.note else note
    return tv.model_copy(update=upd, deep=True)


def _clamp_pitch(p: float) -> float:
    return min(max(p, PITCH_LIMITS[0]), PITCH_LIMITS[1])


# =============================================================================
# Scale
# =============================================================================
@dataclass(frozen=True)
class _Scale:
    image_id: str
    value: float
    rel_lo: float
    rel_hi: float
    basis: Basis
    group: str
    method: str
    calibrated: bool
    evidence: tuple[str, ...] = ()

    @classmethod
    def from_calibration(cls, cal: ScaleCalibration, image_id: Optional[str] = None) -> "_Scale":
        tv = cal.metres_per_pixel
        v = float(tv.value)
        lo, hi = _lo(tv), _hi(tv)
        return cls(image_id=image_id or cal.image_id, value=v, rel_lo=max(0.0, 1.0 - lo / v),
                   rel_hi=max(0.0, hi / v - 1.0), basis=tv.basis,
                   group=tv.correlation_group or scale_group(image_id or cal.image_id), method=cal.method,
                   calibrated=cal.method in ("reference_measurement", "dimensioned_plan"),
                   evidence=tuple(tv.evidence_ids))

    def linked(self, k: TrackedValue) -> "_Scale":
        """Scale for another image whose pixels convert to this image's pixels by ``k``."""
        ek = 0.5 * (_hi(k) - _lo(k)) / k.value
        return _Scale(self.image_id, self.value * k.value, math.hypot(self.rel_lo, ek), math.hypot(self.rel_hi, ek),
                      weakest_basis(self.basis, k.basis), self.group, self.method, self.calibrated, self.evidence)

    def m(self, px: float, band: float, *, px_basis: Basis = Basis.OBSERVED, evidence: Iterable[str] = (),
          note: str = "", source: str = SOURCE) -> TrackedValue:
        """Pixels -> metres with scale and pixel errors combined in quadrature."""
        v = px * self.value
        e = abs(band / px) if px else 0.0
        a = v * (1.0 - math.hypot(self.rel_lo, e))
        b = v * (1.0 + math.hypot(self.rel_hi, e))
        if px >= 0:
            a = max(a, 0.0)
        return _tv(v, "m", weakest_basis(self.basis, px_basis), a, b, group=self.group, source=source,
                   evidence=evidence, note=note)


def _effective_scale(analysis: AnalysisResult, cal: ScaleCalibration, front_img: str,
                     A: AssumptionLibrary) -> tuple[_Scale, list[str]]:
    notes: list[str] = []
    usable = cal.metres_per_pixel.value is not None and cal.metres_per_pixel.value > 0
    if usable and cal.image_id == front_img:
        return _Scale.from_calibration(cal), notes
    if usable:
        k = relative_scale(analysis, cal.image_id)
        if k is not None and (analysis.primary_image_id in (None, front_img)):
            base = _Scale.from_calibration(cal)
            inv = TrackedValue(value=1.0 / k.value, unit="ratio", basis=k.basis,
                               low=1.0 / _hi(k), high=1.0 / _lo(k))
            s = base.linked(inv)
            notes.append(f"Calibration of {cal.image_id} transferred to the front image {front_img} through the "
                         f"multi-view relative scale.")
            return _Scale(front_img, s.value, s.rel_lo, s.rel_hi, s.basis, scale_group(front_img), s.method,
                          s.calibrated, s.evidence), notes
        notes.append(f"Calibration applies to {cal.image_id}, not to the front image {front_img}; prior cues of "
                     "the front image are used instead.")
    fallback = prior_cue_calibration(analysis, front_img, assumptions=A)
    if fallback.metres_per_pixel.value is None:
        raise ValueError("No usable scale for the front elevation (no calibration and no prior scale cue). "
                         "Add a reference measurement, e.g. the confirmed frontage width.")
    notes.extend(n for n in fallback.notes if n.startswith("Warning"))
    return _Scale.from_calibration(fallback, front_img), notes


# =============================================================================
# Per-facade volumes
# =============================================================================
@dataclass
class _Vol:
    facade: FacadeObservation
    block_id: str
    role: BlockRole
    name: str
    width: TrackedValue
    storeys: TrackedValue
    ftf: TrackedValue
    ffl: TrackedValue
    form: RoofForm
    ridge_axis: str
    pitch_obs: Optional[TrackedValue]
    rise: Optional[TrackedValue]
    rise_factor: float
    eaves_overhang: TrackedValue
    verge_overhang: TrackedValue
    high_side: Optional[Side]
    left_px: Optional[float]
    visible_sides: list[Side] = field(default_factory=lambda: [Side.FRONT])
    notes: list[str] = field(default_factory=list)


def _role(hint: str, is_main: bool) -> BlockRole:
    if is_main:
        return BlockRole.MAIN
    h = (hint or "").lower()
    if "garage" in h:
        return BlockRole.GARAGE
    if "extension" in h or h.startswith("ext"):
        return BlockRole.EXTENSION
    return BlockRole.WING


def _storeys(obs: FacadeObservation, default: int) -> TrackedValue:
    st = obs.storeys
    if st.value is None:
        return assumed(float(default), "storeys", low=1.0, high=float(default + 1), source=SOURCE,
                       note=f"Storey count not observed; {default} assumed.")

    def r(x: Optional[float]) -> Optional[float]:
        return None if x is None else float(min(max(int(round(x)), 1), 6))

    n = r(st.value)
    return _tv(n, "storeys", st.basis, r(st.low), r(st.high), source=st.source or "facade observation",
               evidence=st.evidence_ids, note=st.note or "Storeys from the facade observation.")


def _ftf(obs: FacadeObservation, scale: _Scale, storeys: TrackedValue, ffl: TrackedValue,
         A: AssumptionLibrary, pu: float) -> tuple[TrackedValue, Optional[str]]:
    prior = A.floor_to_floor_m
    eh = obs.eaves_height_px
    if not scale.calibrated or eh.value is None or eh.value <= 0:
        return _copy_prior(prior), None
    plate = scale.m(eh.value, px_band(eh, pu), px_basis=eh.basis)
    n = storeys.value
    v = (plate.value - ffl.value) / n
    lo = (_lo(plate) - _hi(ffl)) / (storeys.high or n)
    hi = (_hi(plate) - _lo(ffl)) / (storeys.low or n)
    if not (FTF_PLAUSIBLE[0] <= v <= FTF_PLAUSIBLE[1]):
        return _copy_prior(prior), (f"{obs.block_hint}: floor-to-floor from the eaves height would be {v:.2f} m "
                                    "(implausible); the prior is used. Check storeys / eaves detection.")
    basis = weakest_basis(scale.basis, eh.basis, storeys.basis, ffl.basis, Basis.INFERRED)
    tv = _tv(v, "m", basis, lo, hi,
             group=scale.group, evidence=eh.evidence_ids,
             note=(f"(eaves {plate.value:.2f} m - assumed FFL {ffl.value:.2f} m) / {int(n)} storey(s). The wall-plate "
                   f"height above ground is {plate.basis.value} from the image; the value is {basis.value} because "
                   "the FFL is an assumed prior (its range is folded into this range)."))
    return tv, None


def _roof_overhang(analysis: AnalysisResult, obs: FacadeObservation, scale: _Scale,
                   pu: float) -> Optional[TrackedValue]:
    """Overhang beyond the facade at the image-left/right ends, from the roof outline."""
    if obs.left_x_px is None or not obs.width_px.value:
        return None
    xs: list[float] = []
    ids: list[str] = []
    sig = pu
    for fid in obs.feature_ids:
        f = find_feature(analysis, fid, obs.image_id)
        if f is None or f.feature_type.value != "roof":
            continue
        if f.polygon:
            xs += [p[0] for p in f.polygon]
        elif f.bbox:
            xs += [f.bbox[0], f.bbox[2]]
        else:
            continue
        ids.append(fid)
        sig = max(sig, float(f.pixel_uncertainty))
    if not xs:
        return None
    left = obs.left_x_px - min(xs)
    right = max(xs) - (obs.left_x_px + obs.width_px.value)
    band = length_band(sig)  # overhang = difference of two edges (roof outline, facade end)
    vals = [v for v in (left, right) if v > band]
    if not vals:
        return None
    px = sum(vals) / len(vals)
    tv = scale.m(px, band, evidence=ids,
                 note="Overhang beyond the wall ends measured from the roof outline in the front view.")
    if tv.value > MAX_OVERHANG_M:
        return None
    return tv


def _volume(analysis: AnalysisResult, obs: FacadeObservation, *, is_main: bool, block_id: str, scale: _Scale,
            A: AssumptionLibrary, confirmed_width: Optional[TrackedValue]) -> _Vol:
    pu = float(A.pixel_measurement_error_px)
    notes: list[str] = []
    hint = obs.block_hint
    role = _role(hint, is_main)
    if confirmed_width is not None:
        width = confirmed_width
    elif obs.width_px.value:
        width = scale.m(obs.width_px.value, px_band(obs.width_px, pu), px_basis=obs.width_px.basis,
                        evidence=obs.width_px.evidence_ids or obs.feature_ids[:1],
                        note=f"Facade width {obs.width_px.value:.1f} px x scale.")
    else:
        raise ValueError(f"facade '{hint}' has no measured width; cannot build a block from it")
    storeys = _storeys(obs, 2 if is_main else 1)
    ffl = _copy_prior(A.ground_floor_level_m, "Not observable from the elevation.")
    ftf, fnote = _ftf(obs, scale, storeys, ffl, A, pu)
    if fnote:
        notes.append(fnote)
    # roof form
    raw = (obs.roof_form or "").strip().lower()
    form = _FORMS.get(raw)
    if form is None:
        form = RoofForm.GABLE
        notes.append(f"{hint}: roof form {'not established' if not raw else repr(raw[:30]) + ' not modelled'}; "
                     "gable assumed.")
    pitch_obs = obs.apparent_pitch_deg if (obs.apparent_pitch_deg is not None
                                           and obs.apparent_pitch_deg.value is not None
                                           and 0 < obs.apparent_pitch_deg.value < 75) else None
    if pitch_obs is not None:
        pitch_obs = pitch_obs.model_copy(update={"low": max(PITCH_LIMITS[0], _lo(pitch_obs)),
                                                 "high": min(PITCH_LIMITS[1], _hi(pitch_obs))}, deep=True)
    if pitch_obs is not None or obs.ridge_axis_hint == "perpendicular_to_view":
        ridge_axis = "y"
    else:
        ridge_axis = "x"
        if obs.ridge_axis_hint is None and form in (RoofForm.GABLE, RoofForm.MONOPITCH):
            notes.append(f"{hint}: ridge orientation not reported; ridge parallel to the frontage assumed.")
    high_side: Optional[Side] = None
    rise_factor = 2.0
    if form == RoofForm.MONOPITCH:
        high_side = Side.REAR if ridge_axis == "x" else Side.LEFT
        rise_factor = 1.0
        notes.append(f"{hint}: monopitch high side assumed {high_side.value} (slope direction not observed).")
    rise: Optional[TrackedValue] = None
    eh, rh = obs.eaves_height_px, obs.ridge_height_px
    if (form != RoofForm.FLAT and ridge_axis == "x" and pitch_obs is None and eh.value and rh.value
            and rh.value - eh.value > 1.0):
        band = math.hypot(px_band(rh, pu), px_band(eh, pu))
        rise = scale.m(rh.value - eh.value, band, px_basis=weakest_basis(rh.basis, eh.basis),
                       evidence=[*rh.evidence_ids, *eh.evidence_ids] or list(obs.feature_ids),
                       note="Ridge rise above the wall plate seen as the roof band (ridge parallel to the view).")
    # overhangs
    eaves = _copy_prior(A.eaves_overhang_m)
    verge = _copy_prior(A.verge_overhang_m)
    if form == RoofForm.FLAT:
        eaves = assumed(0.10, "m", low=0.0, high=0.25, source=SOURCE, note="Flat roof edge overhang assumed.")
        verge = eaves.model_copy(deep=True)
    elif form != RoofForm.MONOPITCH:
        oh = _roof_overhang(analysis, obs, scale, pu)
        if oh is not None:
            if form == RoofForm.GABLE and ridge_axis == "x":
                verge = oh
                notes.append(f"{hint}: verge overhang {oh.value:.2f} m inferred from the roof outline.")
            else:
                eaves = oh
                notes.append(f"{hint}: eaves overhang {oh.value:.2f} m inferred from the roof outline.")
    name = {BlockRole.MAIN: "Main house", BlockRole.GARAGE: "Garage", BlockRole.EXTENSION: "Side extension",
            BlockRole.WING: "Wing"}[role]
    if not is_main and role == BlockRole.WING:
        name = f"Wing ({hint[:30]})"
    return _Vol(facade=obs, block_id=block_id, role=role, name=name, width=width, storeys=storeys, ftf=ftf,
                ffl=ffl, form=form, ridge_axis=ridge_axis, pitch_obs=pitch_obs, rise=rise,
                rise_factor=rise_factor, eaves_overhang=eaves, verge_overhang=verge, high_side=high_side,
                left_px=obs.left_x_px, notes=notes)


# =============================================================================
# Openings
# =============================================================================
def _openings(analysis: AnalysisResult, obs: FacadeObservation, vol: _Vol, side: Side, scale: _Scale,
              A: AssumptionLibrary, used: set[str]) -> tuple[list[Opening], list[str]]:
    pu_default = float(A.pixel_measurement_error_px)
    out: list[Opening] = []
    notes: list[str] = []
    n_storeys = int(vol.storeys.value)
    ffl, ftf = vol.ffl, vol.ftf
    for o in obs.openings:
        x0, y0, x1, y1 = o.bbox_px
        if x1 <= x0 or y1 <= y0:
            notes.append(f"Opening {o.feature_id}: empty bounding box; ignored.")
            continue
        feat = find_feature(analysis, o.feature_id, obs.image_id)
        pu = float(feat.pixel_uncertainty) if feat is not None else pu_default
        fb = feat.basis if feat is not None else Basis.OBSERVED
        band = length_band(pu)  # every opening dimension is a difference of two edges
        ev = [o.feature_id]
        width = scale.m(x1 - x0, band, px_basis=fb, evidence=ev, note="Opening width from its bounding box.")
        height = scale.m(y1 - y0, band, px_basis=fb, evidence=ev, note="Opening height from its bounding box.")
        if obs.left_x_px is not None:
            off_px = max(0.0, x0 - obs.left_x_px)
            offset = scale.m(off_px, band, px_basis=fb, evidence=ev,
                             note="From the wall's left end (as seen from outside) to the opening's left edge.")
        else:
            offset = TrackedValue(value=None, unit="m", basis=Basis.UNKNOWN,
                                  note="Facade left edge not measured; position unknown.")
        kind = OpeningKind(o.kind)
        if obs.ground_y_px is not None:
            zb = scale.m(obs.ground_y_px - y1, band, px_basis=fb, evidence=ev)
            storey = o.storey_index
            if storey is None:
                storey = int(math.floor((zb.value - ffl.value + 0.5) / ftf.value))
            storey = min(max(int(storey), 0), max(n_storeys - 1, 0))
            v = zb.value - ffl.value - storey * ftf.value
            lo = _lo(zb) - _hi(ffl) - storey * _hi(ftf)
            hi = _hi(zb) - _lo(ffl) - storey * _lo(ftf)
            v, lo, hi = max(v, 0.0), max(lo, 0.0), max(hi, 0.0)
            sill_basis = weakest_basis(scale.basis, fb, ffl.basis, *([ftf.basis] if storey else []))
            sill = _tv(v, "m", sill_basis, lo, hi, group=scale.group, evidence=ev,
                       note=(f"Opening bottom above ground ({zb.basis.value}) minus assumed FFL {ffl.value:.2f} m"
                             f"{f' minus {storey} x floor-to-floor ({ftf.basis.value})' if storey else ''}; "
                             f"clamped at 0. {sill_basis.value.capitalize()} because it depends on the assumed FFL."))
        else:
            storey = min(max(int(o.storey_index or 0), 0), max(n_storeys - 1, 0))
            sv = 0.0 if kind in (OpeningKind.DOOR, OpeningKind.GARAGE_DOOR, OpeningKind.PATIO_DOOR) else 0.9
            sill = assumed(sv, "m", source=SOURCE, note="Ground line not measured; typical sill assumed.")
        out.append(Opening(opening_id=_opening_id(o.feature_id, used), block_id=vol.block_id, side=side,
                           kind=kind, storey=storey, offset_m=offset, width_m=width, height_m=height,
                           sill_m=sill, feature_id=o.feature_id))
    return out, notes


# =============================================================================
# Depth / pitch options for the main block
# =============================================================================
@dataclass
class _DepthPitch:
    depth: TrackedValue
    pitch: TrackedValue
    notes: list[str]


def _atan_deg(x: float) -> float:
    return math.degrees(math.atan(x))


def _pitch_from_rise(vol: _Vol, depth: TrackedValue, basis: Basis, note: str) -> TrackedValue:
    f, r = vol.rise_factor, vol.rise
    v = _clamp_pitch(_atan_deg(f * r.value / depth.value))
    lo = _clamp_pitch(_atan_deg(f * _lo(r) / _hi(depth)))
    hi = _clamp_pitch(_atan_deg(f * _hi(r) / _lo(depth)))
    return _tv(v, "deg", basis, lo, hi, source=SOURCE, evidence=r.evidence_ids, note=note)


def _option_a(vol: _Vol, A: AssumptionLibrary, depth_obs: Optional[TrackedValue],
              pitch_known: Optional[TrackedValue], scale: _Scale) -> _DepthPitch:
    w = vol.width
    ratio, prior = A.depth_to_width_ratio, A.roof_pitch_deg
    clip_lo, clip_hi = ratio.low * w.value, ratio.high * w.value
    notes: list[str] = []
    if depth_obs is not None:
        if pitch_known is not None:
            pitch = pitch_known
            if vol.rise is not None:
                implied = _atan_deg(vol.rise_factor * vol.rise.value / depth_obs.value)
                notes.append(f"Consistency: pitch implied by the front-view rise and the observed depth is "
                             f"{implied:.1f} deg; observed {pitch.value:.1f} deg.")
        elif vol.rise is not None and vol.form != RoofForm.FLAT:
            pitch = _pitch_from_rise(vol, depth_obs, Basis.INFERRED,
                                     "Implied by the observed rise and the observed depth (scale cancels).")
        else:
            pitch = _copy_prior(prior)
        notes.append(f"Main depth {depth_obs.value:.2f} m observed in a linked side elevation (not hidden).")
        return _DepthPitch(depth_obs, pitch, notes)
    if vol.rise is not None and pitch_known is not None and vol.form != RoofForm.FLAT:
        f, r, p = vol.rise_factor, vol.rise, pitch_known
        t = lambda d: math.tan(math.radians(d))  # noqa: E731
        v = f * r.value / t(p.value)
        depth = _tv(v, "m", weakest_basis(r.basis, p.basis, Basis.INFERRED), f * _lo(r) / t(_hi(p)),
                    f * _hi(r) / t(_lo(p)), group=scale.group, evidence=[*r.evidence_ids, *p.evidence_ids],
                    note=f"depth = {f:g} x observed rise / tan(observed pitch {p.value:.1f} deg).")
        notes.append(f"Main depth {v:.2f} m from the observed rise and the observed pitch.")
        return _DepthPitch(depth, p, notes)
    if vol.rise is not None and pitch_known is None:
        f, r = vol.rise_factor, vol.rise
        t = lambda p: math.tan(math.radians(p))  # noqa: E731
        v = f * r.value / t(prior.value)
        lo = f * _lo(r) / t(_hi(prior))
        hi = f * _hi(r) / t(_lo(prior))
        clo, chi = max(lo, clip_lo), min(hi, clip_hi)
        clipped = False
        if clo <= chi:
            lo, hi = clo, chi
            v_c = min(max(v, lo), hi)
            clipped, v = abs(v_c - v) > 1e-9, v_c
        else:
            notes.append("Depth from rise and pitch prior falls outside the depth/width prior; not clipped.")
        depth = _tv(v, "m", weakest_basis(r.basis, Basis.ASSUMED), lo, hi, group=scale.group,
                    evidence=r.evidence_ids,
                    note=(f"depth = {f:g} x rise / tan(pitch) with observed rise {r.value:.2f} m and the assumed "
                          f"pitch {prior.value:.1f} deg ({_lo(prior):.1f}-{_hi(prior):.1f}); clipped to "
                          f"{ratio.low:.2f}-{ratio.high:.2f} x width."))
        p_lo = max(_lo(prior), _atan_deg(f * _lo(r) / hi))
        p_hi = min(_hi(prior), _atan_deg(f * _hi(r) / lo))
        p_v = prior.value
        if clipped:  # keep the roof on the observed rise: the pitch follows the clipped depth
            p_v = _clamp_pitch(_atan_deg(f * r.value / v))
            notes.append(f"Depth clipped to the depth/width prior; pitch {p_v:.1f} deg re-derived from the observed "
                         "rise so the roof still reproduces it.")
        pitch = _tv(p_v, "deg", Basis.ASSUMED, min(p_lo, p_v), max(p_hi, p_v),
                    source=prior.source,
                    note=("Pitch prior (not observed). Depth-pitch coupling: depth x tan(pitch) / "
                          f"{f:g} = observed rise; confirming the depth or the pitch re-derives the other."))
        notes.append(f"Depth-pitch coupling: main depth {v:.2f} m follows from the observed ridge rise "
                     f"{r.value:.2f} m and the ASSUMED pitch {p_v:.1f} deg; a different pitch gives a "
                     "different depth. Confirm either one: the other is re-derived from the rise.")
        return _DepthPitch(depth, pitch, notes)
    v = ratio.value * w.value
    depth = _tv(v, "m", weakest_basis(w.basis, Basis.ASSUMED), ratio.low * _lo(w), ratio.high * _hi(w),
                group=scale.group,
                note=f"depth = width x assumed depth/width ratio {ratio.value:.2f} ({ratio.low:.2f}-{ratio.high:.2f}).")
    pitch = pitch_known if pitch_known is not None else (
        _copy_prior(prior) if vol.form != RoofForm.FLAT else assumed(0.0, "deg", source=SOURCE, note="Flat roof."))
    notes.append(f"Main depth {v:.2f} m assumed from the depth/width prior (no depth evidence in the views).")
    return _DepthPitch(depth, pitch, notes)


def _option_b(vol: _Vol, a: _DepthPitch, A: AssumptionLibrary, pitch_known: Optional[TrackedValue],
              scale: _Scale) -> _DepthPitch:
    w = vol.width.value
    floor = MIN_DEPTH_FRACTION * w
    v = max(floor, a.depth.value - H_B_DEPTH_REDUCTION_M)
    lo = max(floor, _lo(a.depth) - H_B_DEPTH_REDUCTION_M)
    hi = max(lo, _hi(a.depth) - H_B_DEPTH_REDUCTION_M)
    depth = _tv(v, "m", Basis.ASSUMED, lo, hi, group=scale.group,
                note=(f"Shallower main block assumed: max({MIN_DEPTH_FRACTION:.1f} x width, H-A depth - "
                      f"{H_B_DEPTH_REDUCTION_M:.2f} m)."))
    notes = []
    if vol.rise is not None and pitch_known is None and vol.form != RoofForm.FLAT:
        pitch = _pitch_from_rise(vol, depth, Basis.ASSUMED,
                                 "Implied by the observed rise and the ASSUMED shallower depth.")
        notes.append(f"Main depth {v:.2f} m assumed; implied pitch {pitch.value:.1f} deg keeps the observed rise "
                     f"{vol.rise.value:.2f} m.")
    else:
        pitch = a.pitch.model_copy(deep=True)
        notes.append(f"Main depth {v:.2f} m assumed (shallower than H-A).")
    return _DepthPitch(depth, pitch, notes)


def _option_c(vol: _Vol, A: AssumptionLibrary, pitch_known: Optional[TrackedValue], scale: _Scale) -> _DepthPitch:
    ratio, prior = A.depth_to_width_ratio, A.roof_pitch_deg
    w = vol.width
    notes: list[str] = []
    if vol.rise is not None and pitch_known is None and vol.form != RoofForm.FLAT:
        f, r = vol.rise_factor, vol.rise
        t_lo = math.tan(math.radians(_lo(prior)))
        v = min(f * r.value / t_lo, ratio.high * w.value)
        lo = min(f * _lo(r) / t_lo, ratio.high * _lo(w))
        hi = min(f * _hi(r) / t_lo, ratio.high * _hi(w))
        depth = _tv(v, "m", Basis.ASSUMED, lo, hi, group=scale.group,
                    note=(f"Deep-plan variant: depth from the low pitch bound {_lo(prior):.1f} deg, capped at "
                          f"{ratio.high:.2f} x width."))
        pitch = _pitch_from_rise(vol, depth, Basis.ASSUMED, "Shallow pitch implied by the observed rise.")
        notes.append(f"Deep plan {v:.2f} m with shallow pitch {pitch.value:.1f} deg (same observed rise).")
    else:
        v = ratio.high * w.value
        depth = _tv(v, "m", Basis.ASSUMED, ratio.high * _lo(w), ratio.high * _hi(w), group=scale.group,
                    note=f"Deep-plan variant: width x {ratio.high:.2f} (upper depth/width prior).")
        if pitch_known is not None:
            pitch = pitch_known
        elif vol.form == RoofForm.FLAT:
            pitch = assumed(0.0, "deg", source=SOURCE, note="Flat roof.")
        else:
            pitch = _tv(_lo(prior), "deg", Basis.ASSUMED, _lo(prior), prior.value, source=prior.source,
                        note="Shallow-pitch variant: low bound of the pitch prior.")
        notes.append(f"Deep plan {v:.2f} m (upper depth/width prior).")
    return _DepthPitch(depth, pitch, notes)


# =============================================================================
# Block assembly
# =============================================================================
def _roof(vol: _Vol, pitch: TrackedValue) -> RoofSpec:
    parapet = assumed(0.0, "m", source=SOURCE, note="No parapet assumed.") if vol.form == RoofForm.FLAT else None
    return RoofSpec(form=vol.form, pitch_deg=pitch.model_copy(deep=True), ridge_axis=vol.ridge_axis,
                    eaves_overhang_m=vol.eaves_overhang.model_copy(deep=True),
                    verge_overhang_m=vol.verge_overhang.model_copy(deep=True), high_side=vol.high_side,
                    parapet_height_m=parapet)


def _block(vol: _Vol, x0: TrackedValue, depth: TrackedValue, pitch: TrackedValue, *, heated: bool,
           notes: str = "") -> Block:
    return Block(block_id=vol.block_id, name=vol.name, role=vol.role, origin_x=x0.model_copy(deep=True),
                 origin_y=_datum("Front faces assumed flush with the main block (setback not observable in a "
                                 "fronto-parallel elevation)."),
                 width=vol.width.model_copy(deep=True), depth=depth.model_copy(deep=True),
                 storeys=vol.storeys.model_copy(deep=True), floor_to_floor=vol.ftf.model_copy(deep=True),
                 ground_floor_level=vol.ffl.model_copy(deep=True), roof=_roof(vol, pitch), heated=heated,
                 visible_sides=list(vol.visible_sides), notes=notes)


def _place(vols: list[_Vol], main: _Vol, scale: _Scale, pu: float) -> tuple[dict[str, TrackedValue], list[str]]:
    """Origin x of every front block from left-x ordering, snapping small gaps."""
    notes: list[str] = []
    have_x = all(v.left_px is not None for v in vols)
    if not have_x:
        notes.append("Facade left edges not all measured; blocks assumed adjacent left-to-right in listed order.")
    order = sorted(vols, key=lambda v: v.left_px) if have_x else list(vols)
    im = order.index(main)
    xs: dict[str, TrackedValue] = {main.block_id: _datum("Plan datum: front-left corner of the main block.")}
    for j in range(im + 1, len(order)):
        prev, cur = order[j - 1], order[j]
        px0, pw = xs[prev.block_id], prev.width
        edge = px0.value + pw.value
        gap = (cur.left_px - main.left_px) * scale.value - edge if have_x else 0.0
        if gap < SNAP_GAP_M:
            xs[cur.block_id] = _tv(edge, "m", weakest_basis(px0.basis, pw.basis, Basis.INFERRED),
                                   _lo(px0) + _lo(pw), _hi(px0) + _hi(pw), group=scale.group,
                                   note=f"Snapped to the right edge of '{prev.block_id}' (gap {gap:+.2f} m < "
                                        f"{SNAP_GAP_M:.2f} m).")
        else:
            xs[cur.block_id] = scale.m(cur.left_px - main.left_px, length_band(pu),
                                       note="Offset of the facade's left edge from the main block's left edge.")
            notes.append(f"'{cur.block_id}' is {gap:.2f} m from '{prev.block_id}'; kept as a detached volume.")
    for j in range(im - 1, -1, -1):
        nxt, cur = order[j + 1], order[j]
        nx0, cw = xs[nxt.block_id], cur.width
        if have_x:
            right = (cur.left_px - main.left_px) * scale.value + cw.value
            gap = nx0.value - right
        else:
            gap = 0.0
        if gap < SNAP_GAP_M:
            xs[cur.block_id] = _tv(nx0.value - cw.value, "m", weakest_basis(nx0.basis, cw.basis, Basis.INFERRED),
                                   _lo(nx0) - _hi(cw), _hi(nx0) - _lo(cw), group=scale.group,
                                   note=f"Snapped to the left edge of '{nxt.block_id}' (gap {gap:+.2f} m).")
        else:
            xs[cur.block_id] = scale.m(cur.left_px - main.left_px, length_band(pu),
                                       note="Offset of the facade's left edge from the main block's left edge.")
            notes.append(f"'{cur.block_id}' is {gap:.2f} m from '{nxt.block_id}'; kept as a detached volume.")
    return xs, notes


def _extension(main_block: Block, ext_id: str, at_right: bool, A: AssumptionLibrary) -> Block:
    w = main_block.width.value
    fw, flo, fhi = EXT_WIDTH_FRACTION
    width = assumed(fw * w, "m", low=flo * w, high=fhi * w, source=SOURCE,
                    note=f"Rear extension width assumed {fw:.0%} of the main width (hidden).")
    dv, dlo, dhi = EXT_DEPTH_M
    depth = assumed(dv, "m", low=dlo, high=dhi, source=SOURCE, note="Rear extension depth assumed (hidden).")
    md = main_block.depth
    if at_right:
        x0 = assumed(main_block.origin_x.value + w - width.value, "m", source=SOURCE,
                     note="At the rear-right corner of the main block (assumed).")
    else:
        x0 = assumed(main_block.origin_x.value, "m", source=SOURCE,
                     note="At the rear-left corner of the main block (assumed).")
    y0 = TrackedValue(value=main_block.origin_y.value + md.value, unit="m", basis=Basis.ASSUMED,
                      low=main_block.origin_y.value + _lo(md), high=main_block.origin_y.value + _hi(md),
                      distribution=md.distribution if md.is_uncertain else Distribution.FIXED,
                      correlation_group=md.correlation_group, source=SOURCE,
                      note="Attached at the rear of the main block (origin_y = main depth).")
    roof = RoofSpec(form=RoofForm.FLAT, pitch_deg=assumed(0.0, "deg", source=SOURCE, note="Flat roof (assumed)."),
                    ridge_axis="x",
                    eaves_overhang_m=assumed(0.10, "m", low=0.0, high=0.25, source=SOURCE,
                                             note="Flat roof edge overhang assumed."),
                    verge_overhang_m=assumed(0.10, "m", low=0.0, high=0.25, source=SOURCE,
                                             note="Flat roof edge overhang assumed."),
                    parapet_height_m=assumed(0.0, "m", source=SOURCE, note="No parapet assumed."))
    mf, mg = main_block.floor_to_floor, main_block.ground_floor_level
    # the extension is hidden: its storey height and FFL are assumptions (copied from the main block), not
    # observations - basis ASSUMED and no evidence ids, whatever the main block's own basis is
    ftf = mf.model_copy(update={"basis": Basis.ASSUMED, "evidence_ids": [], "source": SOURCE,
                                "note": (f"Assumed equal to the main block's floor-to-floor {mf.value:.2f} m "
                                         f"({mf.basis.value} there); the extension is not visible in any view.")},
                        deep=True)
    ffl = mg.model_copy(update={"basis": Basis.ASSUMED, "evidence_ids": [], "source": SOURCE,
                                "note": f"Assumed equal to the main block's FFL {mg.value:.2f} m (hidden)."}, deep=True)
    return Block(block_id=ext_id, name="Rear extension (hypothetical)", role=BlockRole.EXTENSION, origin_x=x0,
                 origin_y=y0, width=width, depth=depth,
                 storeys=assumed(1.0, "storeys", source=SOURCE, note="Single storey assumed."),
                 floor_to_floor=ftf, ground_floor_level=ffl, roof=roof, heated=True,
                 visible_sides=[], notes="Entirely assumed: not visible in any view.")


def _attach_rise(block: Block, vol: _Vol) -> Optional[str]:
    """Store the observed roof rise on ``block`` (depth-pitch coupling); returns a consistency note or None."""
    if vol.rise is None or block.roof.form == RoofForm.FLAT:
        return None
    block.roof.observed_rise_m = vol.rise.model_copy(deep=True)
    c = block_coupling(block)
    if c is None or c.consistent:
        return None
    return (f"{block.block_id}: the stored roof does not reproduce the observed rise exactly "
            f"({c.span_field} x tan(pitch) / {c.factor:g} = {c.implied_rise_m:.2f} m vs observed {c.rise.value:.2f} m; "
            f"{'within' if c.within_observed_range else 'outside'} the observed range).")


def _hidden(A: AssumptionLibrary) -> HiddenSideAssumptions:
    return HiddenSideAssumptions(rear_glazing_ratio=_copy_prior(A.rear_glazing_ratio),
                                 side_glazing_ratio=_copy_prior(A.side_glazing_ratio))


# =============================================================================
# Public entry point
# =============================================================================
def generate_geometry_hypotheses(analysis: AnalysisResult, calibration: ScaleCalibration, *,
                                 assumptions: Optional[AssumptionLibrary] = None,
                                 settings: Optional[ProjectSettings] = None) -> list[GeometryHypothesis]:
    """Competing hidden-footprint hypotheses (see module docstring).

    Returns 2 hypotheses when the scale is calibrated (reference / plan) or the
    main depth is observed in a linked side view, 3 when uncalibrated.  Raises
    ``ValueError`` when there is no front facade observation or no usable scale.
    ``settings`` is accepted for interface symmetry; geometry is SI throughout.
    """
    A = assumptions or AssumptionLibrary()
    pu = float(A.pixel_measurement_error_px)
    primary = primary_image_id(analysis)
    front_img = calibration.image_id if front_facades(analysis, calibration.image_id) else primary
    fronts = front_facades(analysis, front_img)
    if not fronts:
        for f in analysis.facades:
            if f.view == ViewDirection.FRONT:
                front_img, fronts = f.image_id, front_facades(analysis, f.image_id)
                break
    if not fronts:
        raise ValueError("No front facade observation: hypotheses need a measured front elevation.")
    scale, common = _effective_scale(analysis, calibration, front_img, A)
    main_obs = main_facade(fronts)

    # --- confirmed main width (reference = main facade width)
    confirmed: Optional[TrackedValue] = None
    if calibration.method == "reference_measurement" and calibration.reference is not None:
        try:
            rr = resolve_reference(analysis, calibration.reference, assumptions=A)
        except ValueError:
            rr = None
        if rr is not None and rr.is_facade_width and rr.image_id == front_img \
                and rr.facade_block_hint == main_obs.block_hint:
            confirmed = TrackedValue(
                value=rr.real_m, unit="m", basis=Basis.USER_CONFIRMED,
                low=rr.real_m - rr.tolerance_m if rr.tolerance_m else None,
                high=rr.real_m + rr.tolerance_m if rr.tolerance_m else None,
                distribution=Distribution.UNIFORM if rr.tolerance_m else Distribution.FIXED,
                source=f"reference measurement ({calibration.reference.source})"[:120],
                evidence_ids=list(rr.evidence_ids),
                note=("Main frontage confirmed by the reference measurement. "
                      + calibration.reference.description[:200]).strip())

    # --- volumes per front facade
    used_ids: set[str] = set()
    vols: list[_Vol] = []
    main_vol: Optional[_Vol] = None
    for obs in [main_obs] + [f for f in fronts if f is not main_obs]:
        is_main = obs is main_obs
        if not is_main and not obs.width_px.value:
            common.append(f"Facade '{obs.block_hint}' has no measured width; not modelled.")
            continue
        bid = _safe_id("main" if is_main else obs.block_hint, used_ids)
        vol = _volume(analysis, obs, is_main=is_main, block_id=bid, scale=scale, A=A,
                      confirmed_width=confirmed if is_main else None)
        vols.append(vol)
        if is_main:
            main_vol = vol
    if main_vol is None:  # pragma: no cover - main facade always yields a volume or raises
        raise ValueError("main facade could not be modelled")
    for v in vols:
        common.extend(v.notes)

    # --- multi-view links (side elevations)
    linked = analysis.multiview.linked_measurements if analysis.multiview is not None else {}
    hint_to_vol = {v.facade.block_hint: v for v in vols}
    depth_obs: dict[str, TrackedValue] = {}
    pitch_side: dict[str, TrackedValue] = {}
    for hint, v in hint_to_vol.items():
        d = linked.get(f"{hint}.depth_front_px_equiv")
        if d is not None and d.value and d.value > 0:
            depth_obs[v.block_id] = scale.m(d.value, px_band(d, pu), px_basis=weakest_basis(d.basis, Basis.INFERRED),
                                            evidence=d.evidence_ids,
                                            note="Depth seen in a linked side elevation (front-scale pixels x scale).")
        p = linked.get(f"{hint}.pitch_side_view_deg")
        if p is not None and p.value is not None and 0 < p.value < 75:
            pitch_side[v.block_id] = p.model_copy(update={"low": max(PITCH_LIMITS[0], _lo(p)),
                                                          "high": min(PITCH_LIMITS[1], _hi(p))}, deep=True)
    side_openings: list[Opening] = []
    for f in analysis.facades:
        side = _SIDE_OF_VIEW.get(f.view)
        if side is None or f.image_id == front_img:
            continue
        v = hint_to_vol.get(f.block_hint)
        if v is None:
            common.append(f"{f.view.value} view of '{f.block_hint}' ({f.image_id}) matches no front block; ignored.")
            continue
        k = relative_scale(analysis, f.image_id)
        if k is None:
            common.append(f"{f.view.value} view {f.image_id} is not scale-linked to the front view; its "
                          f"openings are not used and the {side.value} side stays hidden (rule-filled).")
            continue
        ops, onotes = _openings(analysis, f, v, side, scale.linked(k), A, used_ids)
        side_openings += ops
        common += onotes
        if side not in v.visible_sides:
            v.visible_sides.append(side)

    # --- front openings
    front_ops: list[Opening] = []
    for v in vols:
        ops, onotes = _openings(analysis, v.facade, v, Side.FRONT, scale, A, used_ids)
        front_ops += ops
        common += onotes

    xs, pnotes = _place(vols, main_vol, scale, pu)
    common += pnotes

    # --- options for the main block
    m_depth_obs = depth_obs.get(main_vol.block_id)
    m_pitch_known = pitch_side.get(main_vol.block_id) or main_vol.pitch_obs
    opt_a = _option_a(main_vol, A, m_depth_obs, m_pitch_known, scale)
    options: list[tuple[str, str, str, _DepthPitch, bool]] = [
        ("H-A", "Rectangular plan", "Single rectangular main block; hidden depth from the observed roof rise and "
         "the pitch prior (or observed in a side view).", opt_a, False)]
    if m_depth_obs is not None:
        options.append(("H-B", "Rectangular main + hidden single-storey rear extension",
                        "Observed main depth plus an assumed single-storey flat-roofed rear extension on a side "
                        "not seen in any view.", _DepthPitch(opt_a.depth, opt_a.pitch,
                                                             ["Main depth as observed; rear extension assumed."]),
                        True))
        weights = PLAUSIBILITY_DEPTH_OBSERVED
    else:
        options.append(("H-B", "L-shaped: shallower main + single-storey rear extension",
                        "Shallower main block with the same observed rise (steeper implied pitch) plus an assumed "
                        "single-storey flat-roofed rear extension at the rear-left.",
                        _option_b(main_vol, opt_a, A, m_pitch_known, scale), True))
        if scale.calibrated:
            weights = PLAUSIBILITY_CALIBRATED
        else:
            options.append(("H-C", "Deep plan / shallow pitch",
                            "Single rectangular main block at the deep end of the prior with a shallow pitch "
                            "(same observed rise).", _option_c(main_vol, A, m_pitch_known, scale), False))
            weights = PLAUSIBILITY_UNCALIBRATED

    # --- side blocks (garage, front-visible extension / wing)
    side_blocks: list[Block] = []
    side_notes: list[str] = []
    for v in vols:
        if v is main_vol:
            continue
        if v.block_id in depth_obs:
            depth = depth_obs[v.block_id]
            dnote = f"{v.name}: depth {depth.value:.2f} m observed in a linked side elevation."
        elif v.role == BlockRole.GARAGE:
            dv, dlo, dhi = GARAGE_DEPTH_M
            depth = assumed(dv, "m", low=dlo, high=dhi, source=SOURCE, note="Garage depth assumed (hidden).")
            dnote = f"{v.name}: depth assumed {dv:.2f} m ({dlo:.2f}-{dhi:.2f}); unheated assumed."
        else:
            fv, flo, fhi = WING_DEPTH_FRACTION
            md = opt_a.depth.value
            depth = assumed(round(fv * md, 2), "m", low=flo * md, high=fhi * md, source=SOURCE,
                            note=f"Depth assumed {fv:.0%} of the H-A main depth (hidden).")
            dnote = f"{v.name}: depth assumed {depth.value:.2f} m (hidden)."
        pitch = pitch_side.get(v.block_id) or v.pitch_obs
        if pitch is None:
            pitch = _copy_prior(A.roof_pitch_deg) if v.form != RoofForm.FLAT else assumed(
                0.0, "deg", source=SOURCE, note="Flat roof.")
        heated = v.role != BlockRole.GARAGE
        side_blocks.append(_block(v, xs[v.block_id], depth, pitch, heated=heated, notes=dnote))
        side_notes.append(dnote)
        if pitch.basis == Basis.OBSERVED:
            side_notes.append(f"{v.name}: pitch {pitch.value:.1f} deg observed from the visible gable.")

    hidden_sides = sorted({f"{v.block_id}:{s.value}" for v in vols for s in Side if s not in v.visible_sides})
    evidence = list(dict.fromkeys([*scale.evidence, *[i for v in vols for i in v.facade.feature_ids],
                                   *[o.feature_id for o in side_openings if o.feature_id]]))
    base_notes = [
        f"Scale: {scale.method} ({scale.basis.value}); every dimension scaled from {front_img} shares correlation group "
        f"'{scale.group}'.",
        f"FFL assumed {main_vol.ffl.value:.2f} m ({_lo(main_vol.ffl):.2f}-{_hi(main_vol.ffl):.2f}) for all blocks.",
        f"Floor-to-floor {main_vol.ftf.value:.2f} m ({main_vol.ftf.basis.value}).",
        "Front faces of all blocks assumed flush (setback not observable in a fronto-parallel elevation).",
        f"Hidden facades ({', '.join(hidden_sides) or 'none'}) are filled by hidden-side rules (rear glazing "
        f"{A.rear_glazing_ratio.value:.0%}, side glazing {A.side_glazing_ratio.value:.0%}, rear patio door) - "
        "assumptions to be replaced by observations.",
        "Geometry only: no structural, compliance or survey claim; construction assemblies are chosen separately "
        "and never inferred from appearance.",
    ]

    out: list[GeometryHypothesis] = []
    for hid, name, desc, opt, with_ext in options:
        main_block = _block(main_vol, xs[main_vol.block_id], opt.depth, opt.pitch, heated=True,
                            notes="; ".join(opt.notes))
        rise_note = _attach_rise(main_block, main_vol)
        blocks = [main_block] + [b.model_copy(deep=True) for b in side_blocks]
        notes = list(opt.notes) + ([rise_note] if rise_note else []) + side_notes + base_notes
        if with_ext:
            seen = set(main_vol.visible_sides)
            at_right = Side.LEFT in seen and Side.RIGHT not in seen
            ext_id = _safe_id("rear_ext", {b.block_id for b in blocks}, fallback="rear_ext")
            ext = _extension(main_block, ext_id, at_right, A)
            blocks.append(ext)
            corner = "rear-right" if at_right else "rear-left"
            notes.append(f"Rear extension {ext.width.value:.2f} x {ext.depth.value:.2f} m, single storey, flat roof, "
                         f"heated, at the {corner} corner: entirely ASSUMED (hidden in all views).")
            if Side.REAR in seen or (Side.LEFT in seen and Side.RIGHT in seen):
                notes.append("Warning: the extension would probably have been visible in the available side/rear "
                             "views; this hypothesis is unlikely.")
        try:
            validate_rects([Rect(b.block_id, b.origin_x.value, b.origin_y.value, b.origin_x.value + b.width.value,
                                 b.origin_y.value + b.depth.value) for b in blocks])
        except GeometryError as exc:
            raise ValueError(f"hypothesis {hid} produced an invalid footprint: {exc}") from exc
        openings = [o.model_copy(deep=True) for o in front_ops + side_openings]
        notes.append(f"Plausibility {weights[hid]:.2f} is a subjective prior weight, not a calibrated probability.")
        out.append(GeometryHypothesis(
            hypothesis_id=hid, name=name, description=desc, plausibility=weights[hid], blocks=blocks,
            openings=openings, hidden=_hidden(A), evidence_ids=evidence,
            notes=notes + list(dict.fromkeys(common)), calibration_method=calibration.method))
    return out


__all__ = ["generate_geometry_hypotheses", "PLAUSIBILITY_CALIBRATED", "PLAUSIBILITY_UNCALIBRATED",
           "PLAUSIBILITY_DEPTH_OBSERVED", "GARAGE_DEPTH_M", "EXT_DEPTH_M", "EXT_WIDTH_FRACTION", "SNAP_GAP_M"]
