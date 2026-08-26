"""
Ambient environmental audio layering by zone kind + weather + time of
day: traffic hum, wind, rain, crowd murmur, wildlife -- a volume mix per
layer, consumed the same way ``audio.engine_audio`` output is.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from apex_horizon_engine.utils.config import ZoneKind, ZoneSpec
from apex_horizon_engine.world.weather_system import WeatherKind

_BASE_LAYERS: Dict[ZoneKind, Dict[str, float]] = {
    ZoneKind.MEGACITY: {"traffic_hum": 0.7, "crowd_murmur": 0.4, "sirens_distant": 0.15, "wind": 0.1},
    ZoneKind.INDUSTRIAL_DESERT: {"wind": 0.5, "insects": 0.15, "machinery_hum": 0.2},
    ZoneKind.FOREST_MOUNTAIN: {"wind": 0.35, "wildlife": 0.4, "creek": 0.2},
    ZoneKind.COASTAL_HIGHWAY: {"surf": 0.6, "wind": 0.45, "gulls": 0.2},
    ZoneKind.LOGISTICS_ZONE: {"machinery_hum": 0.55, "rail_clatter": 0.25, "wind": 0.15},
}

_WEATHER_ADD: Dict[WeatherKind, Dict[str, float]] = {
    WeatherKind.RAIN: {"rain": 0.6},
    WeatherKind.STORM: {"rain": 0.85, "thunder_distant": 0.3},
    WeatherKind.SANDSTORM: {"wind": 0.9, "grit_hiss": 0.5},
    WeatherKind.SNOW: {"wind": 0.3, "muffled_ambience": 0.4},
}


@dataclass
class AmbientMix:
    layers: Dict[str, float]
    night_low_pass: float  # 0..1, simulates muffled ambience at night


def compute_ambient_mix(zone: ZoneSpec, weather: WeatherKind, is_night: bool,
                         crowd_cheer_intensity: float = 0.0) -> AmbientMix:
    layers = dict(_BASE_LAYERS.get(zone.kind, {}))
    for key, value in _WEATHER_ADD.get(weather, {}).items():
        layers[key] = max(layers.get(key, 0.0), value)

    if crowd_cheer_intensity > 0.0:
        layers["crowd_cheer"] = round(crowd_cheer_intensity, 3)

    layers = {k: round(min(1.0, v), 3) for k, v in layers.items()}
    return AmbientMix(layers=layers, night_low_pass=0.35 if is_night else 0.0)
