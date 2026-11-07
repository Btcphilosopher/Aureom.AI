"""Line segments and vanishing points with NumPy/SciPy only.

Purpose: decide whether a view is close enough to fronto-parallel for pixel
ratios on the facade plane to be meaningful, and attach a *fractional
foreshortening uncertainty* that downstream calibration can carry.  It does
not rectify images and does not recover metric 3D.

``detect_line_segments_numpy(rgb)``
    Downscale to <= 800 px, light Gaussian smoothing, Sobel gradients
    (``scipy.ndimage``), non-maximum suppression, magnitude threshold, then
    *orientation-binned connected-component line fitting*: edge pixels are
    grouped by edge orientation (overlapping +/-15 degree windows every
    7.5 degrees, tolerant of texture-induced orientation noise),
    8-connected components (after a 1 px gap-bridging dilation) are fitted by
    PCA on the original edge pixels and kept when straight (perpendicular RMS
    <= 1.2 px), long enough and aligned with their window.  Duplicates from
    overlapping windows are merged.  Returns ``N x 4`` float
    ``(x0, y0, x1, y1)`` in original-image pixels.

``estimate_vanishing_points(segments, image_size, *, rng)``
    RANSAC over pairwise segment intersections (homogeneous coordinates,
    normalised by the long image side), length-weighted sampling and scoring,
    least-squares refinement, then a model-selection test between a finite
    VP and a VP at infinity (parallel lines): the infinite model is preferred
    unless the finite one explains the segment directions clearly better.
    Done for the vertical direction and up to two horizontal directions.

Interpretation (documented assumptions):

* Segments within 22.5 deg of the image vertical are vertical candidates; only
  segments within 25 deg of the image horizontal are horizontal candidates, so
  roof rakes and hips (typically 30-50 deg in elevation) never define a
  horizontal vanishing point.  Very strong two-point perspective (horizontal
  edges steeper than 25 deg) is therefore reported as "direction unknown"
  rather than mis-estimated.

* ``vertical_tilt_deg`` is the largest angle between the image vertical and
  the vertical-VP direction at the image centre and left/right edge midpoints
  (camera roll plus keystone convergence).
* ``facade_obliqueness_deg`` uses the horizontal VP with the most support
  (assumed to belong to the principal facade): ``atan(f / |x_vp - c_x|)``
  with the principal point at the image centre and focal length ``f`` from
  EXIF ``FocalLengthIn35mmFilm`` when available, otherwise an assumed
  ``1.2 x`` long image side (stated in the notes).  An infinite horizontal
  VP gives 0 degrees.
* ``is_near_fronto_parallel``: obliqueness <= 5 deg and tilt <= 2.5 deg.
* ``foreshortening_uncertainty``: 0.02 when near fronto-parallel; otherwise
  ``0.02 + (1 - cos(obliqueness)) + 0.004 x tilt`` clipped to [0.03, 0.5];
  0.08 when the facade direction could not be established.
"""

from __future__ import annotations

import math
from typing import Optional, Sequence

import numpy as np
from scipy import ndimage

from ..core.models import ImageAsset, PerspectiveEstimate, VanishingPoint
from .adapters import AdapterSkipped, Capability

METHOD = "numpy-ransac-vp"
METHOD_VERSION = "1.0"
LINES_METHOD = "numpy-sobel-binned-cc"

FRONTO_PARALLEL_MAX_OBLIQUENESS_DEG = 5.0
FRONTO_PARALLEL_MAX_TILT_DEG = 2.5
ASSUMED_FOCAL_FACTOR = 1.2


# =============================================================================
# Line segment detection
# =============================================================================
def _to_gray(rgb: np.ndarray) -> np.ndarray:
    a = np.asarray(rgb)
    if a.ndim == 2:
        return a.astype(np.float64)
    if a.ndim == 3 and a.shape[2] >= 3:
        return a[..., :3].astype(np.float64) @ np.array([0.299, 0.587, 0.114])
    raise ValueError("expected an HxW or HxWx3 image array")


def _nms(mag: np.ndarray, gx: np.ndarray, gy: np.ndarray) -> np.ndarray:
    """Keep pixels that are local maxima of gradient magnitude across the edge."""
    ang = (np.degrees(np.arctan2(gy, gx)) + 180.0) % 180.0
    p = np.pad(mag, 1, mode="constant")
    c = p[1:-1, 1:-1]
    left, right = p[1:-1, :-2], p[1:-1, 2:]
    up, down = p[:-2, 1:-1], p[2:, 1:-1]
    ul, dr = p[:-2, :-2], p[2:, 2:]
    ur, dl = p[:-2, 2:], p[2:, :-2]
    q0 = (ang < 22.5) | (ang >= 157.5)
    q45 = (ang >= 22.5) & (ang < 67.5)
    q90 = (ang >= 67.5) & (ang < 112.5)
    q135 = (ang >= 112.5) & (ang < 157.5)
    keep = np.zeros_like(mag, dtype=bool)
    keep |= q0 & (c >= left) & (c >= right)
    keep |= q45 & (c >= ul) & (c >= dr)  # gradient along (+x,+y): neighbours down-right / up-left
    keep |= q90 & (c >= up) & (c >= down)
    keep |= q135 & (c >= ur) & (c >= dl)
    return keep


def _fit_components(mask: np.ndarray, min_pixels: int, min_length: float, max_perp_rms: float) -> list[tuple]:
    """PCA line fit per connected component.  Components are found on a slightly dilated mask
    (bridging 1-2 px gaps caused by texture) but fitted on the original edge pixels only."""
    bridged = ndimage.binary_dilation(mask, structure=np.ones((3, 3), dtype=bool))
    lab, n = ndimage.label(bridged, structure=np.ones((3, 3), dtype=bool))
    if n == 0:
        return []
    ys, xs = np.nonzero(mask)
    ids = lab[ys, xs]
    cnt = np.bincount(ids, minlength=n + 1).astype(np.float64)
    ok = cnt >= min_pixels
    ok[0] = False
    if not ok.any():
        return []
    sx = np.bincount(ids, xs, minlength=n + 1)
    sy = np.bincount(ids, ys, minlength=n + 1)
    sxx = np.bincount(ids, xs * xs.astype(np.float64), minlength=n + 1)
    syy = np.bincount(ids, ys * ys.astype(np.float64), minlength=n + 1)
    sxy = np.bincount(ids, xs * ys.astype(np.float64), minlength=n + 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        mx, my = sx / cnt, sy / cnt
        cxx = sxx / cnt - mx * mx
        cyy = syy / cnt - my * my
        cxy = sxy / cnt - mx * my
    tr = cxx + cyy
    det = cxx * cyy - cxy * cxy
    disc = np.sqrt(np.maximum(tr * tr / 4.0 - det, 0.0))
    l1 = tr / 2.0 + disc
    l2 = np.maximum(tr / 2.0 - disc, 0.0)
    theta = 0.5 * np.arctan2(2.0 * cxy, cxx - cyy)
    length = np.sqrt(np.maximum(12.0 * l1, 0.0))
    good = ok & (length >= min_length) & (np.sqrt(l2) <= max_perp_rms)
    out = []
    for k in np.nonzero(good)[0]:
        dx, dy = math.cos(theta[k]), math.sin(theta[k])
        h = 0.5 * length[k]
        out.append((mx[k] - h * dx, my[k] - h * dy, mx[k] + h * dx, my[k] + h * dy, length[k]))
    return out


def _dedupe(segs: np.ndarray, angle_tol_deg: float = 4.0, dist_tol: float = 2.0) -> np.ndarray:
    if len(segs) == 0:
        return segs
    d = segs[:, 2:4] - segs[:, 0:2]
    lengths = np.hypot(d[:, 0], d[:, 1])
    order = np.argsort(-lengths, kind="stable")
    kept: list[int] = []
    for i in order:
        if lengths[i] <= 0:
            continue
        ui = d[i] / lengths[i]
        mi = 0.5 * (segs[i, 0:2] + segs[i, 2:4])
        dup = False
        for j in kept:
            uj = d[j] / lengths[j]
            if abs(ui[0] * uj[0] + ui[1] * uj[1]) < math.cos(math.radians(angle_tol_deg)):
                continue
            rel = mi - segs[j, 0:2]
            perp = abs(rel[0] * uj[1] - rel[1] * uj[0])
            if perp > dist_tol:
                continue
            # overlap of i's projection on j
            t0 = (segs[i, 0:2] - segs[j, 0:2]) @ uj
            t1 = (segs[i, 2:4] - segs[j, 0:2]) @ uj
            lo, hi = min(t0, t1), max(t0, t1)
            ov = max(0.0, min(hi, lengths[j]) - max(lo, 0.0))
            if ov >= 0.5 * lengths[i]:
                dup = True
                break
        if not dup:
            kept.append(int(i))
    return segs[kept]


def detect_line_segments_numpy(rgb: np.ndarray, *, max_dim: int = 800, min_length_frac: float = 0.04,
                               magnitude_quantile: float = 0.90, bin_step_deg: float = 7.5,
                               bin_half_width_deg: float = 15.0, max_perp_rms: float = 1.2,
                               max_segments: int = 500) -> np.ndarray:
    """Detect straight line segments (pure NumPy/SciPy).  Returns ``N x 4`` float64."""
    gray = _to_gray(rgb)
    H, W = gray.shape
    if H < 8 or W < 8:
        return np.zeros((0, 4))
    s = min(1.0, float(max_dim) / float(max(H, W)))
    if s < 1.0:
        g = ndimage.gaussian_filter(gray, sigma=0.5 / s)
        g = ndimage.zoom(g, s, order=1)
    else:
        g = gray
    g = ndimage.gaussian_filter(g, sigma=1.0)
    gx = ndimage.sobel(g, axis=1)
    gy = ndimage.sobel(g, axis=0)
    mag = np.hypot(gx, gy)
    if not np.isfinite(mag).all() or mag.max() <= 0:
        return np.zeros((0, 4))
    thr = max(float(np.quantile(mag, magnitude_quantile)), 0.08 * float(mag.max()), 12.0)
    edges = (mag >= thr) & _nms(mag, gx, gy)
    # border pixels are unreliable after filtering
    edges[:2, :] = edges[-2:, :] = False
    edges[:, :2] = edges[:, -2:] = False
    phi = (np.degrees(np.arctan2(gy, gx)) + 90.0) % 180.0  # edge (line) direction
    min_len = max(12.0, min_length_frac * max(g.shape))
    min_pix = int(max(8, 0.6 * min_len))
    found: list[tuple] = []
    ey, ex = np.nonzero(edges)
    ephi = phi[ey, ex]
    for centre in np.arange(0.0, 180.0, bin_step_deg):
        dphi = np.abs((ephi - centre + 90.0) % 180.0 - 90.0)
        sel = dphi <= bin_half_width_deg
        if sel.sum() < min_pix:
            continue
        m = np.zeros_like(edges)
        m[ey[sel], ex[sel]] = True
        for seg in _fit_components(m, min_pix, min_len, max_perp_rms):
            ang = math.degrees(math.atan2(seg[3] - seg[1], seg[2] - seg[0])) % 180.0
            if abs((ang - centre + 90.0) % 180.0 - 90.0) <= bin_half_width_deg:
                found.append(seg)
    if not found:
        return np.zeros((0, 4))
    arr = np.array(found, dtype=np.float64)
    arr = arr[np.argsort(-arr[:, 4], kind="stable")][: 4 * max_segments, :4]
    arr = _dedupe(arr)[:max_segments]
    return arr / s


# =============================================================================
# Vanishing points
# =============================================================================
def _angular_error_deg(v: np.ndarray, mids: np.ndarray, dirs: np.ndarray) -> np.ndarray:
    """Angle between each segment direction and the direction towards VP ``v`` (homogeneous)."""
    u = v[None, :2] - v[2] * mids
    nu = np.hypot(u[:, 0], u[:, 1])
    with np.errstate(invalid="ignore", divide="ignore"):
        c = np.abs(u[:, 0] * dirs[:, 0] + u[:, 1] * dirs[:, 1]) / nu
    c = np.where(nu > 1e-12, np.clip(c, 0.0, 1.0), 0.0)
    return np.degrees(np.arccos(c))


def _refine(lines: np.ndarray, w: np.ndarray) -> np.ndarray:
    a = lines * np.sqrt(w)[:, None]
    _, _, vt = np.linalg.svd(a, full_matrices=False)
    v = vt[-1]
    return v / np.linalg.norm(v)


def _principal_direction(dirs: np.ndarray, w: np.ndarray) -> np.ndarray:
    m = (dirs * w[:, None]).T @ dirs
    evals, evecs = np.linalg.eigh(m)
    d = evecs[:, int(np.argmax(evals))]
    return np.array([d[0], d[1], 0.0])


def _ransac_vp(idx: np.ndarray, lines: np.ndarray, mids: np.ndarray, dirs: np.ndarray, lengths: np.ndarray,
               thr: np.ndarray, rng: np.random.Generator, n_iter: int, min_support: int):
    if len(idx) < max(2, min_support):
        return None
    w = lengths[idx]
    p = w / w.sum()
    best_v, best_score = None, -1.0
    n_pairs = len(idx) * (len(idx) - 1) // 2
    iters = min(n_iter, max(n_pairs * 2, 10))
    for _ in range(iters):
        i, j = rng.choice(idx, size=2, replace=False, p=p)
        v = np.cross(lines[i], lines[j])
        nv = np.linalg.norm(v)
        if nv < 1e-12:
            continue
        v = v / nv
        err = _angular_error_deg(v, mids[idx], dirs[idx])
        score = float(w[err <= thr[idx]].sum())
        if score > best_score:
            best_v, best_score = v, score
    if best_v is None:
        return None
    v = best_v
    inl = idx[_angular_error_deg(v, mids[idx], dirs[idx]) <= thr[idx]]
    for _ in range(3):
        if len(inl) < 2:
            break
        v = _refine(lines[inl], lengths[inl])
        new = idx[_angular_error_deg(v, mids[idx], dirs[idx]) <= thr[idx]]
        if len(new) < 2:
            break
        inl = new
    if len(inl) < min_support:
        return None
    # model selection: VP at infinity (parallel lines) vs finite VP
    ww = lengths[inl]
    err_f = _angular_error_deg(v, mids[inl], dirs[inl])
    v_inf = _principal_direction(dirs[inl], ww)
    err_i = _angular_error_deg(v_inf, mids[inl], dirs[inl])
    rms_f = math.sqrt(float((ww * err_f ** 2).sum() / ww.sum()))
    rms_i = math.sqrt(float((ww * err_i ** 2).sum() / ww.sum()))
    infinite = abs(v[2]) < 1e-9 or rms_i <= max(1.25 * rms_f, rms_f + 0.15)
    if infinite:
        v = v_inf
        inl = idx[_angular_error_deg(v, mids[idx], dirs[idx]) <= thr[idx]]
    return v, inl, infinite, (rms_i if infinite else rms_f)


def focal_length_px_from_exif(asset: ImageAsset) -> Optional[float]:
    """Focal length in pixels from EXIF ``FocalLengthIn35mmFilm`` (36 mm frame width)."""
    try:
        f35 = float(asset.exif.get("FocalLengthIn35mmFilm", ""))
    except (TypeError, ValueError):
        return None
    if not (8.0 <= f35 <= 2000.0):
        return None
    return f35 / 36.0 * float(max(asset.width_px, asset.height_px))


def estimate_vanishing_points(segments: np.ndarray, image_size: Sequence[float], *,
                              rng: Optional[np.random.Generator] = None, n_iterations: int = 600,
                              inlier_angle_deg: float = 1.5, vertical_tolerance_deg: float = 22.5,
                              horizontal_tolerance_deg: float = 25.0, focal_length_px: Optional[float] = None,
                              min_support: int = 3, method: str = METHOD) -> PerspectiveEstimate:
    """Estimate vertical and up to two horizontal vanishing points (see module docstring)."""
    rng = rng if rng is not None else np.random.default_rng(0)
    W, H = float(image_size[0]), float(image_size[1])
    notes: list[str] = []
    segs = np.asarray(segments, dtype=np.float64).reshape(-1, 4) if np.size(segments) else np.zeros((0, 4))
    segs = segs[np.isfinite(segs).all(axis=1)]
    scale = max(W, H)
    cx, cy = W / 2.0, H / 2.0
    p0 = (segs[:, 0:2] - [cx, cy]) / scale
    p1 = (segs[:, 2:4] - [cx, cy]) / scale
    d = p1 - p0
    lengths = np.hypot(d[:, 0], d[:, 1])
    keep = lengths * scale >= 4.0
    p0, p1, d, lengths = p0[keep], p1[keep], d[keep], lengths[keep]
    n = len(lengths)
    if n < 2 * min_support:
        notes.append(f"Only {n} usable line segments; perspective could not be established.")
        return PerspectiveEstimate(method=method, method_version=METHOD_VERSION, foreshortening_uncertainty=0.10,
                                   notes=notes)
    dirs = d / lengths[:, None]
    mids = 0.5 * (p0 + p1)
    ones = np.ones((n, 1))
    lines = np.cross(np.hstack([p0, ones]), np.hstack([p1, ones]))
    lines /= np.linalg.norm(lines[:, :2], axis=1)[:, None]
    len_px = lengths * scale
    thr = np.maximum(inlier_angle_deg, np.degrees(np.arctan2(2.0, len_px)))
    ang_v = np.degrees(np.arccos(np.clip(np.abs(dirs[:, 1]), 0.0, 1.0)))
    all_idx = np.arange(n)
    vps: list[VanishingPoint] = []

    def to_vp(v: np.ndarray, infinite: bool, direction: str, support: int) -> VanishingPoint:
        if infinite:
            return VanishingPoint(direction=direction, finite=False, support=support)
        return VanishingPoint(direction=direction, finite=True, support=support,
                              x=float(v[0] / v[2] * scale + cx), y=float(v[1] / v[2] * scale + cy))

    # ---- vertical
    # two long parallel verticals (e.g. both wall edges) are enough support for the vertical direction
    vert = _ransac_vp(all_idx[ang_v <= vertical_tolerance_deg], lines, mids, dirs, lengths, thr, rng,
                      n_iterations, max(2, min_support - 1))
    used = np.zeros(n, dtype=bool)
    tilt: Optional[float] = None
    if vert is not None:
        v, inl, inf, _ = vert
        used[inl] = True
        vps.append(to_vp(v, inf, "vertical", len(inl)))
        probes = np.array([[0.0, 0.0], [-0.5 * W / scale, 0.0], [0.5 * W / scale, 0.0]])
        tilt = float(_angular_error_deg(v, probes, np.tile([[0.0, 1.0]], (3, 1))).max())
    else:
        notes.append("No consistent vertical direction found.")

    # ---- horizontals
    hz: list[tuple] = []
    # steeply inclined segments (roof rakes, hips) are not horizontal building edges: excluded
    rest = all_idx[(~used) & (ang_v >= 90.0 - horizontal_tolerance_deg)]
    for label in ("horizontal_a", "horizontal_b"):
        res = _ransac_vp(rest, lines, mids, dirs, lengths, thr, rng, n_iterations, min_support)
        if res is None:
            break
        v, inl, inf, _ = res
        if label == "horizontal_b" and lengths[inl].sum() < 0.1 * lengths.sum():
            break
        hz.append((label, v, inl, inf))
        vps.append(to_vp(v, inf, label, len(inl)))
        rest = np.setdiff1d(rest, inl)

    # ---- interpretation
    f_px = focal_length_px
    if f_px is None:
        f_px = ASSUMED_FOCAL_FACTOR * scale
        focal_note = f"focal length assumed {ASSUMED_FOCAL_FACTOR:.1f} x long side (no EXIF 35 mm focal length)"
    else:
        focal_note = "focal length from EXIF 35 mm-equivalent"
    obliq: Optional[float] = None
    horizon: Optional[float] = None
    if hz:
        label, v, inl, inf = max(hz, key=lambda t: lengths[t[2]].sum())
        if inf:
            obliq = 0.0
            notes.append("Principal horizontal edges are parallel in the image (vanishing point at infinity).")
        else:
            x_px = abs(v[0] / v[2]) * scale
            obliq = math.degrees(math.atan2(f_px, x_px))
            notes.append(f"Principal facade obliqueness from {label} ({focal_note}).")
        finite_y = [h[1][1] / h[1][2] * scale + cy for h in hz if not h[3]]
        if finite_y:
            horizon = float(np.mean(finite_y))
    else:
        notes.append("No consistent horizontal direction found; facade obliqueness unknown.")
    near: Optional[bool] = None
    if obliq is not None and tilt is not None:
        near = obliq <= FRONTO_PARALLEL_MAX_OBLIQUENESS_DEG and tilt <= FRONTO_PARALLEL_MAX_TILT_DEG
    elif obliq is not None:
        near = obliq <= FRONTO_PARALLEL_MAX_OBLIQUENESS_DEG
    if near:
        fu = 0.02
    elif obliq is not None:
        fu = 0.02 + (1.0 - math.cos(math.radians(obliq))) + 0.004 * (tilt or 0.0)
        fu = float(min(0.5, max(0.03, fu)))
    else:
        fu = 0.08
    if tilt is not None and tilt > FRONTO_PARALLEL_MAX_TILT_DEG:
        notes.append(f"Verticals converge or lean by up to {tilt:.1f} deg (camera tilt/roll); "
                     "heights measured away from the image centre are less reliable.")
    notes.append(f"{n} segments; RANSAC with length-weighted scoring (seeded); pixel VPs relative to "
                 "the uploaded image. Not a rectification or metric reconstruction.")
    return PerspectiveEstimate(
        method=method, method_version=METHOD_VERSION, vanishing_points=vps, horizon_y=horizon,
        vertical_tilt_deg=None if tilt is None else round(tilt, 3),
        facade_obliqueness_deg=None if obliq is None else round(obliq, 3),
        is_near_fronto_parallel=near, foreshortening_uncertainty=round(fu, 4), notes=notes)


def rng_for(asset: ImageAsset, seed: int = 0) -> np.random.Generator:
    """Deterministic generator per (seed, image content)."""
    return np.random.default_rng([int(seed) & 0xFFFFFFFF, int(asset.sha256[:8], 16)])


class NumpyLinePerspective:
    """Perspective adapter: NumPy line detection + RANSAC vanishing points (always available)."""

    name = "numpy-lines-vp"
    version = METHOD_VERSION
    capability = Capability.PERSPECTIVE.value

    def is_available(self) -> bool:
        return True

    def run(self, asset: ImageAsset, rgb: Optional[np.ndarray], *, seed: int = 0) -> PerspectiveEstimate:
        if rgb is None:
            raise AdapterSkipped("no pixel data")
        segs = detect_line_segments_numpy(rgb)
        h, w = np.asarray(rgb).shape[:2]
        est = estimate_vanishing_points(segs, (w, h), rng=rng_for(asset, seed),
                                        focal_length_px=focal_length_px_from_exif(asset),
                                        method=f"{LINES_METHOD}+{METHOD}")
        return est


__all__ = ["detect_line_segments_numpy", "estimate_vanishing_points", "focal_length_px_from_exif",
           "NumpyLinePerspective", "rng_for", "METHOD", "METHOD_VERSION"]
