"""Optional OpenCV line-segment detector feeding :func:`estimate_vanishing_points`.

``cv2`` is imported lazily inside the adapter; this module imports cleanly
without OpenCV and the adapter then reports ``is_available() == False``.

Detection: grayscale image downscaled to <= 1200 px, then the LSD line
segment detector (``cv2.createLineSegmentDetector``) when the installed build
provides it, otherwise Canny + probabilistic Hough (``cv2.HoughLinesP``).
Segments shorter than 3 % of the long side are discarded; coordinates are
returned in original-image pixels.  The vanishing-point interpretation is the
same NumPy RANSAC as :mod:`.perspective` (same assumptions and notes).
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from ..core.models import ImageAsset, PerspectiveEstimate
from .adapters import AdapterSkipped, AdapterUnavailable, Capability, package_available
from .perspective import METHOD as VP_METHOD
from .perspective import estimate_vanishing_points, focal_length_px_from_exif, rng_for


def detect_line_segments_cv2(rgb: np.ndarray, *, max_dim: int = 1200, min_length_frac: float = 0.03,
                             max_segments: int = 600) -> tuple[np.ndarray, str]:
    """Return (``N x 4`` segments in original pixels, detector name)."""
    try:
        import cv2  # lazy optional import
    except ImportError as exc:
        raise AdapterUnavailable(f"OpenCV not installed: {exc}") from exc
    a = np.asarray(rgb)
    gray = a if a.ndim == 2 else cv2.cvtColor(np.ascontiguousarray(a[..., :3]).astype(np.uint8), cv2.COLOR_RGB2GRAY)
    h, w = gray.shape[:2]
    s = min(1.0, float(max_dim) / float(max(h, w)))
    if s < 1.0:
        gray = cv2.resize(gray, (max(1, int(round(w * s))), max(1, int(round(h * s)))), interpolation=cv2.INTER_AREA)
    min_len = min_length_frac * max(gray.shape[:2])
    segs = None
    detector = "cv2.HoughLinesP"
    if hasattr(cv2, "createLineSegmentDetector"):
        try:
            lsd = cv2.createLineSegmentDetector(0)
            found = lsd.detect(gray)[0]
            segs = np.zeros((0, 4)) if found is None else found.reshape(-1, 4).astype(np.float64)
            detector = "cv2.LSD"
        except cv2.error:
            segs = None
    if segs is None:
        edges = cv2.Canny(gray, 60, 160)
        found = cv2.HoughLinesP(edges, 1, np.pi / 360.0, threshold=40, minLineLength=int(min_len), maxLineGap=4)
        segs = np.zeros((0, 4)) if found is None else found.reshape(-1, 4).astype(np.float64)
    if len(segs):
        L = np.hypot(segs[:, 2] - segs[:, 0], segs[:, 3] - segs[:, 1])
        segs = segs[L >= min_len]
        L = L[L >= min_len]
        segs = segs[np.argsort(-L, kind="stable")][:max_segments]
    return segs / s, detector


class OpenCVLinePerspective:
    """Perspective adapter using OpenCV line segments (optional)."""

    name = "opencv-lines-vp"
    version = "1.0"
    capability = Capability.PERSPECTIVE.value

    def is_available(self) -> bool:
        return package_available("cv2")

    def run(self, asset: ImageAsset, rgb: Optional[np.ndarray], *, seed: int = 0) -> PerspectiveEstimate:
        if rgb is None:
            raise AdapterSkipped("no pixel data")
        segs, detector = detect_line_segments_cv2(rgb)
        h, w = np.asarray(rgb).shape[:2]
        est = estimate_vanishing_points(segs, (w, h), rng=rng_for(asset, seed),
                                        focal_length_px=focal_length_px_from_exif(asset),
                                        method=f"{detector}+{VP_METHOD}")
        try:
            import cv2

            est.method_version = f"{est.method_version}/opencv-{cv2.__version__}"
        except ImportError:  # pragma: no cover
            pass
        return est


__all__ = ["detect_line_segments_cv2", "OpenCVLinePerspective"]
