"""
Procedural event generation.

Deliberately decoupled from ``progression`` and ``ai.adaptive_ai`` --
this module takes plain dicts (reputation-by-discipline, player style
preference weights) rather than importing those subsystems directly, so
``core.engine`` is the only place that wires the full loop together.
Event *type* weighting is influenced by: the zone kind (a drift comp
doesn't spawn in the middle of a dry lake), current weather, the
player's reputation tier in that discipline (gates harder events in),
and the adaptive AI's read on what the player actually enjoys.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from apex_horizon_engine.utils.config import ZoneKind, ZoneSpec
from apex_horizon_engine.world.weather_system import WeatherKind


class EventType(str, Enum):
    STREET_RACE = "street_race"
    CIRCUIT_RACE = "circuit_race"
    CANYON_RUN = "canyon_run"
    DRIFT_COMP = "drift_competition"
    OFFROAD_RALLY = "offroad_rally"
    SPRINT = "sprint"
    ENDURANCE = "endurance"
    SHOWCASE = "showcase"


# Discipline each event type feeds reputation into (progression.reputation).
EVENT_DISCIPLINE = {
    EventType.STREET_RACE: "street",
    EventType.CIRCUIT_RACE: "circuit",
    EventType.CANYON_RUN: "circuit",
    EventType.DRIFT_COMP: "drift",
    EventType.OFFROAD_RALLY: "offroad",
    EventType.SPRINT: "street",
    EventType.ENDURANCE: "endurance",
    EventType.SHOWCASE: "street",
}

_ZONE_AFFINITY: Dict[ZoneKind, Dict[EventType, float]] = {
    ZoneKind.MEGACITY: {EventType.STREET_RACE: 1.6, EventType.SPRINT: 1.1, EventType.DRIFT_COMP: 1.2,
                         EventType.SHOWCASE: 1.4, EventType.CIRCUIT_RACE: 0.6},
    ZoneKind.INDUSTRIAL_DESERT: {EventType.SPRINT: 1.7, EventType.ENDURANCE: 1.3, EventType.OFFROAD_RALLY: 1.1,
                                  EventType.CIRCUIT_RACE: 0.8},
    ZoneKind.FOREST_MOUNTAIN: {EventType.CANYON_RUN: 1.8, EventType.OFFROAD_RALLY: 1.6, EventType.ENDURANCE: 1.0},
    ZoneKind.COASTAL_HIGHWAY: {EventType.SPRINT: 1.4, EventType.CANYON_RUN: 1.2, EventType.CIRCUIT_RACE: 1.0,
                                EventType.SHOWCASE: 1.1},
    ZoneKind.LOGISTICS_ZONE: {EventType.STREET_RACE: 1.2, EventType.DRIFT_COMP: 1.3, EventType.OFFROAD_RALLY: 0.9},
}

_WEATHER_MULT: Dict[WeatherKind, Dict[EventType, float]] = {
    WeatherKind.RAIN: {EventType.DRIFT_COMP: 1.3, EventType.CIRCUIT_RACE: 0.75},
    WeatherKind.STORM: {EventType.ENDURANCE: 0.6, EventType.SPRINT: 0.7},
    WeatherKind.FOG: {EventType.CANYON_RUN: 0.6, EventType.SHOWCASE: 0.5},
    WeatherKind.SANDSTORM: {EventType.OFFROAD_RALLY: 0.7, EventType.SPRINT: 0.6},
}

TIER_REQUIREMENT = {
    EventType.STREET_RACE: 1, EventType.SPRINT: 1, EventType.SHOWCASE: 1,
    EventType.DRIFT_COMP: 2, EventType.CANYON_RUN: 2, EventType.OFFROAD_RALLY: 2,
    EventType.CIRCUIT_RACE: 3, EventType.ENDURANCE: 4,
}


@dataclass
class EventSpec:
    event_id: str
    event_type: EventType
    zone_id: str
    discipline: str
    difficulty: float          # 0..1, scales AI rival skill + reward
    rival_count: int
    reward_credits: int
    reward_reputation: float
    laps: int = 1
    length_km: float = 3.5


class EventGenerator:
    def __init__(self, seed: int = 0):
        self._rng = random.Random(seed)
        self._next_id = 0

    def generate(
        self,
        zone: ZoneSpec,
        weather: WeatherKind,
        reputation_by_discipline: Dict[str, float],
        style_preferences: Optional[Dict[str, float]] = None,
    ) -> EventSpec:
        style_preferences = style_preferences or {}
        affinity = _ZONE_AFFINITY.get(zone.kind, {})
        weather_mult = _WEATHER_MULT.get(weather, {})

        candidates: List[EventType] = []
        weights: List[float] = []
        for etype in EventType:
            discipline = EVENT_DISCIPLINE[etype]
            rep = reputation_by_discipline.get(discipline, 0.0)
            tier_needed = TIER_REQUIREMENT[etype]
            if rep < (tier_needed - 1) * 8.0:  # roughly 8 rep points per tier
                continue
            weight = affinity.get(etype, 0.5) * weather_mult.get(etype, 1.0)
            # Adaptive AI hook: player style preference (e.g. "drift": 0.8)
            # multiplies the matching event type's weight directly.
            style_key = {"drift_competition": "drift", "offroad_rally": "offroad",
                         "street_race": "street", "sprint": "street",
                         "circuit_race": "circuit", "canyon_run": "circuit",
                         "endurance": "endurance", "showcase": "street"}[etype.value]
            weight *= 0.6 + 1.4 * style_preferences.get(style_key, 0.3)
            candidates.append(etype)
            weights.append(max(0.01, weight))

        if not candidates:
            candidates, weights = [EventType.STREET_RACE], [1.0]

        chosen = self._rng.choices(candidates, weights=weights, k=1)[0]
        difficulty = min(1.0, 0.25 + reputation_by_discipline.get(EVENT_DISCIPLINE[chosen], 0.0) / 60.0)
        rival_count = 3 + int(difficulty * 5)
        length_km = self._rng.uniform(1.8, 6.0)
        laps = 1 if chosen in (EventType.SPRINT, EventType.CANYON_RUN, EventType.OFFROAD_RALLY) else self._rng.randint(2, 4)
        base_reward = 900 + int(difficulty * 4200)

        spec = EventSpec(
            event_id=f"evt_{self._next_id}",
            event_type=chosen,
            zone_id=zone.zone_id,
            discipline=EVENT_DISCIPLINE[chosen],
            difficulty=difficulty,
            rival_count=rival_count,
            reward_credits=base_reward,
            reward_reputation=4.0 + difficulty * 10.0,
            laps=laps,
            length_km=round(length_km, 2),
        )
        self._next_id += 1
        return spec
