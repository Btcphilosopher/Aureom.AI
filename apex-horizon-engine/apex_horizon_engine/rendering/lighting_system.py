"""
Day/night lighting description derived from ``world.weather_system.WorldClock``.
Produces the numeric parameters a renderer would feed to its sun/sky/
ambient pass; also read by ``ai.racer_ai`` indirectly through
``rendering.weather_renderer`` visibility, and by ``audio`` for
time-of-day ambience selection.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from apex_horizon_engine.world.weather_system import WorldClock


@dataclass
class LightingState:
    sun_elevation_deg: float
    sun_intensity: float      # 0..1
    ambient_intensity: float  # 0..1, never fully zero (moon/city glow)
    color_temperature_k: float
    sky_tint: tuple[float, float, float]  # RGB 0..1, warm sunset to cool night


def compute_lighting(clock: WorldClock) -> LightingState:
    elevation = clock.sun_elevation_deg
    sun_intensity = max(0.0, math.sin(math.radians(elevation)))
    ambient = 0.08 + 0.5 * sun_intensity

    # Warmer color temperature near the horizon (sunrise/sunset), cooler
    # at midday, coolest at night (moonlight-ish blue).
    if elevation > 5:
        golden = max(0.0, 1.0 - elevation / 20.0)
        color_temp = 5500 + 3000 * (1.0 - golden) - 1800 * golden
        tint = (1.0, 0.85 + 0.15 * (1 - golden), 0.75 + 0.25 * (1 - golden))
    else:
        night_depth = min(1.0, (-elevation) / 30.0) if elevation < 0 else 0.3
        color_temp = 9000 + 3000 * night_depth
        tint = (0.55 - 0.15 * night_depth, 0.62 - 0.1 * night_depth, 0.85)

    return LightingState(
        sun_elevation_deg=elevation, sun_intensity=round(sun_intensity, 3),
        ambient_intensity=round(min(1.0, ambient), 3), color_temperature_k=round(color_temp),
        sky_tint=tuple(round(c, 3) for c in tint),
    )
