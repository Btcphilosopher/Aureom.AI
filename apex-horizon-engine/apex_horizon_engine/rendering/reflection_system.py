"""
Reflective-surface bookkeeping: wet roads and megacity glass towers both
raise local reflectivity, which feeds the renderer's reflection pass
(or, headless, just the numeric intensity a debug view/HUD can show).
"""

from __future__ import annotations

from dataclasses import dataclass

from apex_horizon_engine.utils.config import ZoneKind, ZoneSpec
from apex_horizon_engine.world.weather_system import ZoneWeatherState


@dataclass
class ReflectionProfile:
    road_reflectivity: float     # 0..1, wet asphalt sheen
    architectural_reflectivity: float  # 0..1, glass/chrome density for the zone kind
    neon_bounce: float           # 0..1, night-time neon reflection strength (megacity signature look)


_ARCH_REFLECTIVITY = {
    ZoneKind.MEGACITY: 0.85, ZoneKind.LOGISTICS_ZONE: 0.35, ZoneKind.COASTAL_HIGHWAY: 0.4,
    ZoneKind.INDUSTRIAL_DESERT: 0.15, ZoneKind.FOREST_MOUNTAIN: 0.1,
}


def compute_reflection_profile(zone: ZoneSpec, weather: ZoneWeatherState, is_night: bool) -> ReflectionProfile:
    road = min(1.0, weather.wetness * 1.3)
    arch = _ARCH_REFLECTIVITY.get(zone.kind, 0.2)
    neon = arch * (0.9 if is_night else 0.1) * (0.6 + 0.4 * road)
    return ReflectionProfile(
        road_reflectivity=round(road, 3), architectural_reflectivity=round(arch, 3), neon_bounce=round(neon, 3),
    )
