"""Object detection: a pluggable interface plus a dependency-free reference detector.

The reference implementation is a colour-threshold connected-components
detector — genuinely functional (it finds and boxes real blobs matching a
colour range) but not a learned model. A production build points
``ObjectDetector`` at a real network (e.g. a CoreML/Vision model on-device,
or a PyTorch model when ``torch`` is installed) without changing any caller.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Protocol, Tuple

import numpy as np


@dataclass
class Detection:
    label: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # x0, y0, x1, y1 in pixels


class ObjectDetector(Protocol):
    def detect(self, frame: np.ndarray) -> List[Detection]: ...


def _connected_components(mask: np.ndarray) -> List[Tuple[int, int, int, int]]:
    """Minimal flood-fill connected-components labelling; returns bounding boxes."""
    visited = np.zeros_like(mask, dtype=bool)
    h, w = mask.shape
    boxes = []
    for y in range(h):
        for x in range(w):
            if not mask[y, x] or visited[y, x]:
                continue
            stack = [(y, x)]
            visited[y, x] = True
            min_y = max_y = y
            min_x = max_x = x
            size = 0
            while stack:
                cy, cx = stack.pop()
                size += 1
                min_y, max_y = min(min_y, cy), max(max_y, cy)
                min_x, max_x = min(min_x, cx), max(max_x, cx)
                for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = True
                        stack.append((ny, nx))
            if size >= 4:  # ignore single-pixel noise
                boxes.append((min_x, min_y, max_x + 1, max_y + 1))
    return boxes


@dataclass
class ColourThresholdObjectDetector:
    """Detects blobs whose colour falls within an RGB range (0-1 float image)."""

    label: str
    low: Tuple[float, float, float]
    high: Tuple[float, float, float]

    def detect(self, frame: np.ndarray) -> List[Detection]:
        low, high = np.array(self.low), np.array(self.high)
        mask = np.all((frame >= low) & (frame <= high), axis=-1)
        boxes = _connected_components(mask)
        total_pixels = mask.shape[0] * mask.shape[1]
        detections = []
        for box in boxes:
            x0, y0, x1, y1 = box
            area = (x1 - x0) * (y1 - y0)
            confidence = min(1.0, area / max(1, total_pixels) * 8)
            detections.append(Detection(label=self.label, confidence=confidence, bbox=box))
        return detections


def load_torch_detector(model_name: str) -> ObjectDetector:
    """Extension point for a real learned detector; raises clearly if torch isn't installed."""
    try:
        import torch  # noqa: F401
    except ImportError as exc:  # pragma: no cover - exercised only without torch installed
        raise RuntimeError(
            f"Loading '{model_name}' requires PyTorch, which is not installed in this environment. "
            "Install torch or use ColourThresholdObjectDetector for the dependency-free reference path."
        ) from exc
    raise NotImplementedError("Native model loading is an integration point for a real deployment.")
