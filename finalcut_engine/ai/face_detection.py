"""Face *presence* detection (not identity recognition, per spec section 13).

Reuses the same connected-components approach as ``object_detection`` with a
skin-tone colour heuristic as the dependency-free reference path.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np

from finalcut_engine.ai.object_detection import ColourThresholdObjectDetector, Detection


@dataclass
class FaceDetector:
    """A heuristic stand-in for a real face detector (e.g. Vision's face landmarks API)."""

    _inner: ColourThresholdObjectDetector = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self._inner is None:
            # A generous approximate skin-tone range in normalised RGB.
            self._inner = ColourThresholdObjectDetector(label="face", low=(0.35, 0.2, 0.15), high=(1.0, 0.8, 0.7))

    def detect(self, frame: np.ndarray) -> List[Detection]:
        detections = self._inner.detect(frame)
        h, w = frame.shape[:2]
        # A face-ish blob is roughly as tall as it is wide; filter out obviously
        # non-face shapes (e.g. a wide skin-toned wall) to reduce false positives.
        plausible = []
        for d in detections:
            x0, y0, x1, y1 = d.bbox
            box_w, box_h = x1 - x0, y1 - y0
            aspect = box_w / max(1, box_h)
            if 0.5 <= aspect <= 1.8 and box_w >= w * 0.03:
                plausible.append(d)
        return plausible
