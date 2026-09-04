"""
World clock: ages, calendar, seasons, weather.

Spec ref: 02 (age engine), 29 (seasons), 30 (day/night), 28 (weather).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

DAYS_PER_SEASON = 30
DAYS_PER_YEAR = DAYS_PER_SEASON * 4
HOURS_PER_DAY = 24


class Age(str, Enum):
    FIRST_AGE = "FIRST_AGE"
    SECOND_AGE = "SECOND_AGE"
    THIRD_AGE = "THIRD_AGE"
    FOURTH_AGE = "FOURTH_AGE"


class Season(str, Enum):
    SPRING = "SPRING"
    SUMMER = "SUMMER"
    AUTUMN = "AUTUMN"
    WINTER = "WINTER"


_SEASON_ORDER = [Season.SPRING, Season.SUMMER, Season.AUTUMN, Season.WINTER]

# Section 29: seasonal multipliers applied to food production, movement
# speed and construction speed. Data-driven-enough to retune without
# touching system code (section 103).
SEASON_MODIFIERS = {
    Season.SPRING: {"food": 1.1, "movement": 1.0, "construction": 1.0},
    Season.SUMMER: {"food": 1.25, "movement": 1.0, "construction": 1.1},
    Season.AUTUMN: {"food": 1.0, "movement": 0.95, "construction": 1.0},
    Season.WINTER: {"food": 0.4, "movement": 0.6, "construction": 0.6},
}


class WeatherState(str, Enum):
    CLEAR = "CLEAR"
    RAIN = "RAIN"
    FOG = "FOG"
    STORM = "STORM"
    SNOW = "SNOW"

# section 28: weather affects movement, visibility, ranged accuracy,
# agriculture, construction, supply, morale.
WEATHER_MODIFIERS = {
    WeatherState.CLEAR: {"movement": 1.0, "visibility": 1.0, "ranged_accuracy": 1.0},
    WeatherState.RAIN: {"movement": 0.85, "visibility": 0.8, "ranged_accuracy": 0.85},
    WeatherState.FOG: {"movement": 0.9, "visibility": 0.4, "ranged_accuracy": 0.6},
    WeatherState.STORM: {"movement": 0.55, "visibility": 0.5, "ranged_accuracy": 0.5},
    WeatherState.SNOW: {"movement": 0.5, "visibility": 0.6, "ranged_accuracy": 0.7},
}


@dataclass
class Calendar:
    age: Age
    year: int
    day_of_year: int = 0  # 0..DAYS_PER_YEAR-1
    hour: int = 6
    tick: int = 0

    @property
    def season(self) -> Season:
        idx = min(self.day_of_year // DAYS_PER_SEASON, 3)
        return _SEASON_ORDER[idx]

    @property
    def is_night(self) -> bool:
        return self.hour < 6 or self.hour >= 20

    def advance(self, hours: int = 1) -> None:
        self.tick += 1
        self.hour += hours
        while self.hour >= HOURS_PER_DAY:
            self.hour -= HOURS_PER_DAY
            self.day_of_year += 1
            if self.day_of_year >= DAYS_PER_YEAR:
                self.day_of_year = 0
                self.year += 1


class WeatherSystem:
    """Deterministic Markov-chain weather driven by the world RNG, never
    Python's global random module, so replays (section 61) reproduce
    identical weather."""

    _TRANSITIONS = {
        WeatherState.CLEAR: [(WeatherState.CLEAR, 0.6), (WeatherState.RAIN, 0.25), (WeatherState.FOG, 0.15)],
        WeatherState.RAIN: [(WeatherState.RAIN, 0.4), (WeatherState.CLEAR, 0.35), (WeatherState.STORM, 0.25)],
        WeatherState.FOG: [(WeatherState.FOG, 0.4), (WeatherState.CLEAR, 0.6)],
        WeatherState.STORM: [(WeatherState.STORM, 0.2), (WeatherState.RAIN, 0.5), (WeatherState.CLEAR, 0.3)],
        WeatherState.SNOW: [(WeatherState.SNOW, 0.55), (WeatherState.CLEAR, 0.45)],
    }

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.state = WeatherState.CLEAR

    def step(self, season: Season) -> WeatherState:
        if season == Season.WINTER:
            # Winter overrides the normal chain with snow-biased weather.
            self.state = self.rng.choices(
                [WeatherState.SNOW, WeatherState.CLEAR, WeatherState.STORM],
                weights=[0.5, 0.35, 0.15],
            )[0]
            return self.state
        options = self._TRANSITIONS[self.state if self.state != WeatherState.SNOW else WeatherState.CLEAR]
        states = [o[0] for o in options]
        weights = [o[1] for o in options]
        self.state = self.rng.choices(states, weights=weights)[0]
        return self.state
