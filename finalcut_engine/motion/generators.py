"""Generator clips: synthetic video sources with no underlying media file
(solid colours, gradients, noise) — used for backgrounds, mattes, and as
placeholders in the demo project.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np

from finalcut_engine.core.timebase import Time


@dataclass
class SolidGenerator:
    colour: Tuple[float, float, float] = (0.0, 0.0, 0.0)

    def render(self, size: Tuple[int, int], t: Time) -> np.ndarray:
        h, w = size
        return np.tile(np.array(self.colour, dtype=np.float64), (h, w, 1))


@dataclass
class GradientGenerator:
    start_colour: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    end_colour: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    angle_degrees: float = 90.0  # 90 = top-to-bottom

    def render(self, size: Tuple[int, int], t: Time) -> np.ndarray:
        h, w = size
        theta = np.radians(self.angle_degrees)
        ys, xs = np.mgrid[0:h, 0:w].astype(np.float64)
        xs, ys = xs / max(1, w - 1), ys / max(1, h - 1)
        projection = xs * np.cos(theta) + ys * np.sin(theta)
        projection = (projection - projection.min()) / max(1e-9, projection.max() - projection.min())
        start, end = np.array(self.start_colour), np.array(self.end_colour)
        return start[None, None, :] + (end - start)[None, None, :] * projection[..., None]


@dataclass
class NoiseGenerator:
    seed: int = 0
    monochrome: bool = True

    def render(self, size: Tuple[int, int], t: Time) -> np.ndarray:
        h, w = size
        rng = np.random.default_rng(self.seed)
        if self.monochrome:
            plane = rng.uniform(0, 1, (h, w))
            return np.stack([plane, plane, plane], axis=-1)
        return rng.uniform(0, 1, (h, w, 3))
