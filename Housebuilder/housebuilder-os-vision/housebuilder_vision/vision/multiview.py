"""Combining orthogonal elevation views (and the SfM interface).

:func:`combine_orthogonal_views` links a FRONT elevation of a block with
LEFT/RIGHT (gable/side) and REAR elevations of the *same block hint* in other
images.  It is an **orthogonal-elevation combination, not photogrammetric
structure-from-motion**: each view is treated as a near fronto-parallel image
of one facade plane, and the relative scale between images is recovered from
heights that both views share — the wall-plate (eaves) height and the ridge
height above ground.  For each shared height ``h``::

    k_h = h_front_px / h_side_px            (side px -> front px)
    sigma(k_h)/k_h = sqrt((s_f/h_f)^2 + (s_s/h_s)^2)

and the eaves/ridge estimates are combined by inverse-variance weighting
(their disagreement, if larger than expected, widens the uncertainty and is
noted).  Pixel sigmas come from the facade ``TrackedValue`` bounds, which the
analysis sets to +/- 2 sigma.

Outputs (all ``INFERRED`` — derived by rule from observations; weaker input
bases propagate through :func:`weakest_basis`):

* ``relative_scales[<image_id>]``: factor converting that image's pixels to
  primary-image (front) pixels.
* ``linked_measurements["<block>.depth_front_px_equiv"]``: side-view facade
  width expressed in front-image pixels — the plan depth of the block on the
  front scale (convert with the front calibration, e.g. ``/ (px per m)``).
* ``linked_measurements["<block>.pitch_side_view_deg"]``: gable pitch observed
  in the side view (copied with its own basis, OBSERVED when the gable
  triangle was measured directly).
* ``linked_measurements["<block>.rear_width_front_px_equiv"]``: rear facade
  width on the front scale (a consistency check against the front width).

Assumptions: both views are near fronto-parallel elevations; eaves and ridge
are level and the same physical lines in both views; ground is level across
the building.  Notes record when these are doubtful.

:class:`ColmapSfMReconstructor` documents the interface for true multi-view
reconstruction (COLMAP / pycolmap).  It is unavailable by default; an
implementation is injected as ``runner``.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Callable, Optional, Sequence

import numpy as np

from ..core.models import AnalysisResult, FacadeObservation, ImageAsset, MultiViewResult, ViewDirection
from ..core.provenance import Basis, Distribution, TrackedValue, weakest_basis
from .adapters import AdapterSkipped, AdapterUnavailable, Capability

METHOD = "orthogonal-elevation-scale-link"
METHOD_VERSION = "1.0"
NOT_SFM_NOTE = ("Orthogonal-elevation combination, not photogrammetric SfM: relative scale between views "
                "comes from shared eaves/ridge heights; both views are assumed near fronto-parallel.")

SIDE_VIEWS = (ViewDirection.LEFT, ViewDirection.RIGHT)


def _sigma(tv: Optional[TrackedValue], default_px: float = 2.0) -> Optional[float]:
    """1-sigma from a TrackedValue whose low/high are +/- 2 sigma."""
    if tv is None or tv.value is None:
        return None
    if tv.low is not None and tv.high is not None and tv.high > tv.low:
        return (tv.high - tv.low) / 4.0
    return default_px


def _ratio(num: TrackedValue, den: TrackedValue) -> Optional[tuple[float, float]]:
    if num is None or den is None or not num.value or not den.value or num.value <= 0 or den.value <= 0:
        return None
    k = num.value / den.value
    rel = math.hypot(_sigma(num) / num.value, _sigma(den) / den.value)
    return k, k * rel


def _combine(estimates: Sequence[tuple[float, float]]) -> tuple[float, float, bool]:
    """Inverse-variance mean; returns (value, sigma, consistent)."""
    ws = [1.0 / max(s, 1e-12) ** 2 for _, s in estimates]
    v = sum(w * x for w, (x, _) in zip(ws, estimates)) / sum(ws)
    s = math.sqrt(1.0 / sum(ws))
    consistent = True
    if len(estimates) > 1:
        spread = max(x for x, _ in estimates) - min(x for x, _ in estimates)
        expect = 3.0 * math.sqrt(sum(sd ** 2 for _, sd in estimates))
        if spread > expect:
            consistent = False
            s = max(s, spread / 2.0)
    return v, s, consistent


def _tv(value: float, sigma: float, unit: str, basis: Basis, *, source: str, evidence: Sequence[str],
        note: str) -> TrackedValue:
    lo, hi = value - 2.0 * sigma, value + 2.0 * sigma
    return TrackedValue(value=value, unit=unit, basis=basis, low=lo, high=hi,
                        distribution=Distribution.TRIANGULAR if hi > lo else Distribution.FIXED,
                        source=source, evidence_ids=list(dict.fromkeys(evidence)), note=note)


def _scale_between(ref: FacadeObservation, other: FacadeObservation) -> Optional[dict[str, Any]]:
    ests, used, bases = [], [], []
    for name in ("eaves_height_px", "ridge_height_px"):
        a, b = getattr(ref, name), getattr(other, name)
        r = _ratio(a, b)
        if r is not None:
            ests.append(r)
            used.append(name.replace("_px", ""))
            bases += [a.basis, b.basis]
    if not ests:
        return None
    k, s, consistent = _combine(ests)
    return {"k": k, "sigma": s, "used": used, "consistent": consistent, "estimates": ests,
            "basis": weakest_basis(bases, Basis.INFERRED)}


def combine_orthogonal_views(facades: Sequence[FacadeObservation] | AnalysisResult, *,
                             primary_image_id: Optional[str] = None) -> Optional[MultiViewResult]:
    """Link front and side/rear elevations of the same block (see module docstring).

    Accepts a list of facade observations or an :class:`AnalysisResult`.
    Returns ``None`` when no block has a front view plus another view.
    """
    if isinstance(facades, AnalysisResult):
        primary_image_id = primary_image_id or facades.primary_image_id
        facades = facades.facades
    by_block: dict[str, list[FacadeObservation]] = defaultdict(list)
    for f in facades:
        by_block[f.block_hint].append(f)
    linked: dict[str, TrackedValue] = {}
    scale_parts: dict[str, list[tuple[float, float, Basis, list[str]]]] = defaultdict(list)
    notes: list[str] = [NOT_SFM_NOTE]
    image_ids: list[str] = []
    for block in sorted(by_block):
        fs = by_block[block]
        fronts = [f for f in fs if f.view == ViewDirection.FRONT]
        if not fronts:
            continue
        ref = next((f for f in fronts if f.image_id == primary_image_id), fronts[0])
        others = [f for f in fs if f.view in (*SIDE_VIEWS, ViewDirection.REAR) and f.image_id != ref.image_id]
        depth_parts: list[tuple[float, float]] = []
        depth_bases: list[Basis] = []
        depth_ev: list[str] = []
        used_heights: set[str] = set()
        for o in others:
            sc = _scale_between(ref, o)
            if sc is None:
                notes.append(f"{block}: {o.view.value} view {o.image_id} shares no measurable eaves/ridge height "
                             "with the front view; not linked.")
                continue
            if not sc["consistent"]:
                e = ", ".join(f"{x:.4f}" for x, _ in sc["estimates"])
                notes.append(f"{block}: eaves- and ridge-based scales for {o.image_id} disagree ({e}); views may "
                             "not be true orthogonal elevations or heights may be mis-detected. Uncertainty widened.")
            ev = [*ref.feature_ids, *o.feature_ids]
            used_heights.update(sc["used"])
            scale_parts[o.image_id].append((sc["k"], sc["sigma"], sc["basis"], ev))
            for iid in (ref.image_id, o.image_id):
                if iid not in image_ids:
                    image_ids.append(iid)
            k, sk = sc["k"], sc["sigma"]
            if o.view in SIDE_VIEWS and o.width_px.value:
                w = o.width_px.value
                d = w * k
                sd = d * math.hypot((_sigma(o.width_px) or 2.0) / w, sk / k)
                depth_parts.append((d, sd))
                depth_bases += [sc["basis"], o.width_px.basis]
                depth_ev += ev
                if o.apparent_pitch_deg is not None and o.apparent_pitch_deg.value is not None:
                    key = f"{block}.pitch_side_view_deg"
                    if key not in linked:
                        linked[key] = o.apparent_pitch_deg.model_copy(update={
                            "note": (o.apparent_pitch_deg.note + " " if o.apparent_pitch_deg.note else "")
                            + f"Gable pitch seen in the {o.view.value} view ({o.image_id})."}, deep=True)
                # consistency: rise seen from the front vs side span
                if ref.ridge_height_px.value and ref.eaves_height_px.value and o.apparent_pitch_deg:
                    rise_f = ref.ridge_height_px.value - ref.eaves_height_px.value
                    if rise_f > 0 and d > 0:
                        implied = math.degrees(math.atan2(2.0 * rise_f, d))
                        obs = o.apparent_pitch_deg.value
                        notes.append(f"{block}: pitch implied by front-view rise and side-view depth = "
                                     f"{implied:.1f} deg; observed in side view = {obs:.1f} deg.")
            elif o.view == ViewDirection.REAR and o.width_px.value:
                w = o.width_px.value
                rw = w * k
                srw = rw * math.hypot((_sigma(o.width_px) or 2.0) / w, sk / k)
                linked[f"{block}.rear_width_front_px_equiv"] = _tv(
                    rw, srw, "px", weakest_basis(sc["basis"], o.width_px.basis), source=METHOD, evidence=ev,
                    note=f"Rear facade width on the front-image scale (front width {ref.width_px.value:.1f} px).")
        if depth_parts:
            d, sd, consistent = _combine(depth_parts)
            note = ("Side-view facade width converted to front-image pixels via shared heights "
                    f"(scale via {', '.join(sorted(used_heights))}); "
                    "divide by the front calibration (px per m) for metres. Low/high = +/- 2 sigma.")
            if not consistent:
                note += " Left and right views disagree; uncertainty widened."
            linked[f"{block}.depth_front_px_equiv"] = _tv(d, sd, "px", weakest_basis(depth_bases, Basis.INFERRED),
                                                          source=METHOD, evidence=depth_ev, note=note)
    if not scale_parts:
        return None
    rel: dict[str, TrackedValue] = {}
    for iid, parts in scale_parts.items():
        k, s, _ = _combine([(p[0], p[1]) for p in parts])
        rel[iid] = _tv(k, s, "ratio", weakest_basis([p[2] for p in parts], Basis.INFERRED), source=METHOD,
                       evidence=[e for p in parts for e in p[3]],
                       note="Multiply this image's pixel lengths (on the linked facade plane) by this factor to "
                            "express them in primary-image pixels. Low/high = +/- 2 sigma.")
    return MultiViewResult(method=METHOD, method_version=METHOD_VERSION, image_ids=image_ids,
                           linked_measurements=linked, relative_scales=rel, notes=notes)


# =============================================================================
# Adapters
# =============================================================================
class OrthogonalViewCombiner:
    """``MultiViewReconstructor`` wrapping :func:`combine_orthogonal_views` (always available)."""

    name = "orthogonal-view-combiner"
    version = METHOD_VERSION
    capability = Capability.MULTIVIEW.value

    def is_available(self) -> bool:
        return True

    def run(self, assets: Sequence[ImageAsset], facades: Sequence[FacadeObservation], *,
            primary_image_id: Optional[str] = None,
            load_rgb: Optional[Callable[[ImageAsset], np.ndarray]] = None, seed: int = 0) -> Optional[MultiViewResult]:
        res = combine_orthogonal_views(list(facades), primary_image_id=primary_image_id)
        if res is None:
            raise AdapterSkipped("no block has a front elevation plus a side or rear elevation in another image")
        return res


class ColmapSfMReconstructor:
    """Interface for photogrammetric multi-view reconstruction (COLMAP / pycolmap).

    Intended contract for an implementation (injected as ``runner``)::

        runner(assets: Sequence[ImageAsset], load_rgb: Callable[[ImageAsset], np.ndarray], *, seed: int)
            -> MultiViewResult

    Requirements: >= 3 overlapping photographs of the same building with
    sufficient parallax (not orthogonal elevations), ideally with EXIF focal
    lengths.  SfM recovers camera poses and a sparse point cloud up to an
    unknown similarity transform, so one confirmed real dimension is still
    required for metric scale.  Measurements it reports (e.g.
    ``"<block>.depth_m"``) must carry reprojection-error-based uncertainty and
    ``basis=INFERRED`` until scaled by a user-confirmed reference.

    Without a runner (the default) ``is_available()`` is False and the
    registry records the adapter as ``unavailable``; no SfM is attempted.
    """

    name = "colmap-sfm"
    version = "interface-1.0"
    capability = Capability.MULTIVIEW.value

    def __init__(self, runner: Optional[Callable[..., MultiViewResult]] = None) -> None:
        self.runner = runner

    def is_available(self) -> bool:
        return self.runner is not None

    def run(self, assets: Sequence[ImageAsset], facades: Sequence[FacadeObservation], *,
            primary_image_id: Optional[str] = None,
            load_rgb: Optional[Callable[[ImageAsset], np.ndarray]] = None, seed: int = 0) -> Optional[MultiViewResult]:
        if self.runner is None:
            raise AdapterUnavailable("no COLMAP/SfM runner configured")
        if len(assets) < 3:
            raise AdapterSkipped("SfM needs at least 3 overlapping photographs")
        if load_rgb is None:
            raise AdapterSkipped("pixel loader not provided")
        res = self.runner(assets, load_rgb, seed=seed)
        if not isinstance(res, MultiViewResult):
            raise TypeError("SfM runner must return a MultiViewResult")
        return res


__all__ = ["METHOD", "METHOD_VERSION", "NOT_SFM_NOTE", "combine_orthogonal_views", "OrthogonalViewCombiner",
           "ColmapSfMReconstructor"]
