"""Tone/RGB curves defined by user control points.

Implemented as a monotonic piecewise-linear interpolation over ``[0, 1]``. A
native build would use a monotone cubic (matching Final Cut Pro's smooth
curve handles); piecewise-linear is a deliberate, documented simplification
that keeps the math dependency-free and trivially correct to test.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

import numpy as np


@dataclass
class Curve:
    """Control points as (x, y) pairs in [0, 1], sorted by x. Defaults to identity."""

    points: List[Tuple[float, float]] = field(default_factory=lambda: [(0.0, 0.0), (1.0, 1.0)])

    def __post_init__(self) -> None:
        self.points = sorted(self.points, key=lambda p: p[0])

    def add_point(self, x: float, y: float) -> None:
        self.points = sorted([p for p in self.points if p[0] != x] + [(x, y)], key=lambda p: p[0])

    def evaluate(self, x: np.ndarray) -> np.ndarray:
        xs = np.array([p[0] for p in self.points])
        ys = np.array([p[1] for p in self.points])
        return np.interp(x, xs, ys)

    def apply(self, channel: np.ndarray) -> np.ndarray:
        """Apply to a single-channel float array in [0, 1]."""
        return np.clip(self.evaluate(channel), 0.0, 1.0)


@dataclass
class RGBCurves:
    """Independent curves for the master luma channel and each RGB channel."""

    master: Curve = field(default_factory=Curve)
    red: Curve = field(default_factory=Curve)
    green: Curve = field(default_factory=Curve)
    blue: Curve = field(default_factory=Curve)

    def apply(self, image: np.ndarray) -> np.ndarray:
        out = image.astype(np.float64).copy()
        out[..., 0] = self.red.apply(out[..., 0])
        out[..., 1] = self.green.apply(out[..., 1])
        out[..., 2] = self.blue.apply(out[..., 2])
        out = self.master.apply(out)
        return np.clip(out, 0.0, 1.0)
