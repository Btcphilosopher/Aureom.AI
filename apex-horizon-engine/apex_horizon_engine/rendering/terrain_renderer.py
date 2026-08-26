"""
Procedural terrain description: a layered-sine height/friction field per
zone. APEX HORIZON ENGINE is headless (see the package README for why),
so "rendering" here means producing the structured numeric data a real
renderer -- or this repo's own matplotlib debug view -- would need, not
drawing pixels. Height and fine-grained surface friction are queried by
world position and used by ``physics.traction_model`` (surface variation
within a zone) and ``ui.minimap`` (elevation shading).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from apex_horizon_engine.utils.config import ZoneSpec


@dataclass
class TerrainSample:
    height_m: float
    slope: float          # 0..1, steepness magnitude
    fine_grip_mult: float  # local variation around the zone's base_grip


def _value_noise(x: float, y: float, seed: int, scale: float) -> float:
    """Cheap deterministic pseudo-noise via summed sine waves -- avoids a
    numpy/perlin-noise dependency while still giving continuous,
    seed-varied terrain instead of a flat plane."""
    sx, sy = x / scale, y / scale
    n = 0.0
    n += math.sin(sx * 1.7 + seed * 0.31) * math.cos(sy * 1.3 - seed * 0.17)
    n += 0.5 * math.sin(sx * 3.1 - seed * 0.11 + 1.0) * math.cos(sy * 2.7 + seed * 0.23)
    n += 0.25 * math.sin(sx * 6.3 + seed) * math.cos(sy * 5.9 - seed)
    return n / 1.75  # roughly in [-1, 1]


class TerrainField:
    def __init__(self, zone: ZoneSpec, seed: int = 0):
        self.zone = zone
        self.seed = seed

    def sample(self, x: float, y: float) -> TerrainSample:
        z = self.zone
        base_noise = _value_noise(x, y, self.seed, scale=max(50.0, z.radius_m / 6))
        height = base_noise * z.elevation_variance_m

        eps = 8.0
        h_dx = _value_noise(x + eps, y, self.seed, scale=max(50.0, z.radius_m / 6)) * z.elevation_variance_m
        h_dy = _value_noise(x, y + eps, self.seed, scale=max(50.0, z.radius_m / 6)) * z.elevation_variance_m
        slope = min(1.0, math.hypot(h_dx - height, h_dy - height) / (eps * 4.0))

        fine_variation = 1.0 + 0.06 * _value_noise(x, y, self.seed + 97, scale=120.0)
        return TerrainSample(height_m=height, slope=slope, fine_grip_mult=max(0.85, min(1.1, fine_variation)))

    def profile_along(self, x0: float, y0: float, x1: float, y1: float, steps: int = 20) -> list[TerrainSample]:
        return [
            self.sample(x0 + (x1 - x0) * t / steps, y0 + (y1 - y0) * t / steps)
            for t in range(steps + 1)
        ]
