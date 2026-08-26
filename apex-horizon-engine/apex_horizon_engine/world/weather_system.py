"""
Dynamic weather + day/night cycle.

Not in the original module skeleton by name, but required by the brief's
"Dynamic World System" section and referenced by ``rendering.weather_renderer``
/ ``rendering.lighting_system`` -- this is its one authoritative home so
grip, visibility, and AI behaviour all read the same state.

Weather transitions probabilistically per zone (``ZoneSpec.weather_bias``)
on a Markov-chain-ish timer, and wetness is a *continuous* value that
rises while it's raining/storming and dries out afterward, rather than a
binary flag -- so a track can still be greasy a few minutes after a
storm passes, exactly like grip actually behaves in Forza/ACC-style sims.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict

from apex_horizon_engine.utils.config import ZoneSpec


class WeatherKind(str, Enum):
    CLEAR = "clear"
    RAIN = "rain"
    STORM = "storm"
    FOG = "fog"
    SANDSTORM = "sandstorm"
    SNOW = "snow"


_WETTING = {WeatherKind.CLEAR: -0.10, WeatherKind.FOG: -0.02, WeatherKind.RAIN: 0.18,
            WeatherKind.STORM: 0.32, WeatherKind.SANDSTORM: -0.05, WeatherKind.SNOW: 0.06}
_VISIBILITY = {WeatherKind.CLEAR: 1.0, WeatherKind.FOG: 0.35, WeatherKind.RAIN: 0.75,
               WeatherKind.STORM: 0.5, WeatherKind.SANDSTORM: 0.3, WeatherKind.SNOW: 0.55}


@dataclass
class ZoneWeatherState:
    kind: WeatherKind = WeatherKind.CLEAR
    wetness: float = 0.0
    time_to_next_check_s: float = 120.0
    wind_mps: float = 3.0


@dataclass
class WorldClock:
    day_length_minutes: float = 24.0
    elapsed_s: float = 0.0

    def advance(self, dt: float) -> None:
        self.elapsed_s += dt

    @property
    def time_of_day_frac(self) -> float:
        """0..1 fraction through the day, 0 = midnight, 0.5 = noon."""
        period_s = max(60.0, self.day_length_minutes * 60.0)
        return (self.elapsed_s % period_s) / period_s

    @property
    def is_night(self) -> bool:
        return self.time_of_day_frac < 0.22 or self.time_of_day_frac > 0.80

    @property
    def sun_elevation_deg(self) -> float:
        """Simple sinusoidal sun arc: -90 at midnight, +90 at noon-ish."""
        return 90.0 * math.sin(2 * math.pi * (self.time_of_day_frac - 0.25))


class WeatherSystem:
    """Owns one :class:`ZoneWeatherState` per zone plus the shared world
    clock. ``update`` should be called once per engine tick."""

    def __init__(self, zones: Dict[str, ZoneSpec], seed: int = 0, day_length_minutes: float = 24.0):
        self._rng = random.Random(seed)
        self.clock = WorldClock(day_length_minutes=day_length_minutes)
        self.zone_states: Dict[str, ZoneWeatherState] = {zid: ZoneWeatherState() for zid in zones}
        self._zones = zones
        for zid, state in self.zone_states.items():
            state.kind = self._roll_weather(zid)

    def _roll_weather(self, zone_id: str) -> WeatherKind:
        bias = self._zones[zone_id].weather_bias
        options = list(bias.keys())
        weights = list(bias.values())
        choice = self._rng.choices(options, weights=weights, k=1)[0]
        return WeatherKind(choice)

    def update(self, dt: float) -> None:
        self.clock.advance(dt)
        for zone_id, state in self.zone_states.items():
            state.time_to_next_check_s -= dt
            if state.time_to_next_check_s <= 0:
                new_kind = self._roll_weather(zone_id)
                state.kind = new_kind
                state.time_to_next_check_s = self._rng.uniform(180.0, 480.0)
                state.wind_mps = max(0.5, self._rng.gauss(6.0, 3.0))

            target_delta = _WETTING.get(state.kind, 0.0)
            state.wetness = max(0.0, min(1.0, state.wetness + target_delta * dt / 60.0))

    def condition_for(self, zone_id: str) -> ZoneWeatherState:
        return self.zone_states.get(zone_id, ZoneWeatherState())

    def visibility_for(self, zone_id: str) -> float:
        state = self.condition_for(zone_id)
        base = _VISIBILITY.get(state.kind, 1.0)
        night_penalty = 0.65 if self.clock.is_night else 1.0
        return max(0.15, base * night_penalty)
