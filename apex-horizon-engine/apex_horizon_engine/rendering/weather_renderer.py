"""
Translates ``world.weather_system.ZoneWeatherState`` into the numeric
parameters a presentation layer would need: particle density, fog
density, screen-wetness overlay, camera droplet intensity. Never touches
physics grip -- that's ``physics.traction_model``'s job exclusively, so
weather can never accidentally have two different effective intensities
in two different systems.
"""

from __future__ import annotations

from dataclasses import dataclass

from apex_horizon_engine.world.weather_system import WeatherKind, ZoneWeatherState

_PARTICLE_DENSITY = {WeatherKind.CLEAR: 0.0, WeatherKind.FOG: 0.05, WeatherKind.RAIN: 0.55,
                     WeatherKind.STORM: 0.9, WeatherKind.SANDSTORM: 0.75, WeatherKind.SNOW: 0.5}
_FOG_DENSITY = {WeatherKind.CLEAR: 0.02, WeatherKind.FOG: 0.85, WeatherKind.RAIN: 0.25,
                WeatherKind.STORM: 0.4, WeatherKind.SANDSTORM: 0.6, WeatherKind.SNOW: 0.3}


@dataclass
class WeatherVisuals:
    particle_density: float
    fog_density: float
    screen_wetness: float
    lightning_chance_per_min: float
    wind_streaks: float


def compute_weather_visuals(state: ZoneWeatherState) -> WeatherVisuals:
    particle = _PARTICLE_DENSITY.get(state.kind, 0.0)
    fog = _FOG_DENSITY.get(state.kind, 0.02)
    wetness_overlay = min(1.0, state.wetness * 1.1)
    lightning = 4.0 if state.kind == WeatherKind.STORM else 0.0
    wind_streaks = min(1.0, state.wind_mps / 20.0)
    return WeatherVisuals(
        particle_density=round(particle, 3), fog_density=round(fog, 3),
        screen_wetness=round(wetness_overlay, 3), lightning_chance_per_min=lightning,
        wind_streaks=round(wind_streaks, 3),
    )
