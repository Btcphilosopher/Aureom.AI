"""
World History Engine.

Spec ref: 34 (world history engine), 88 (historical time machine), 37
(alternate history — divergence is just "the chronicle differs from the
historical baseline").

The Chronicle subscribes to the EventBus and turns raw events into a
readable, queryable timeline. It never mutates simulation state — it is a
pure observer, which is what lets section 61 (replay) and section 88
(time machine) trust it as a faithful record.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..events.bus import Event, EventBus

# Event types the chronicle considers "historically notable" — i.e. worth
# a human-readable line, per section 34's example list.
NOTABLE_TYPES = {
    "CITY_FOUNDED", "KING_BORN", "KING_DIED", "BATTLE_STARTED", "BATTLE_ENDED",
    "CITY_CAPTURED", "FORTRESS_BUILT", "ROAD_BUILT", "ALLIANCE_FORMED",
    "WAR_DECLARED", "WAR_ENDED", "PEACE_SIGNED", "HERO_DIED", "HERO_PROMOTED",
    "ARTIFACT_DISCOVERED", "KINGDOM_COLLAPSED", "SETTLEMENT_GREW",
    "AGE_CHANGED", "ARMY_DESTROYED",
}


@dataclass
class HistoricalEvent:
    year: int
    day: int
    type: str
    description: str
    payload: Dict = field(default_factory=dict)


class Chronicle:
    def __init__(self, bus: EventBus) -> None:
        self.entries: List[HistoricalEvent] = []
        bus.subscribe_all(self._on_event)

    def _on_event(self, event: Event) -> None:
        if event.type not in NOTABLE_TYPES:
            return
        self.entries.append(
            HistoricalEvent(
                year=event.year,
                day=event.day,
                type=event.type,
                description=_describe(event),
                payload=dict(event.payload),
            )
        )

    def timeline(self, start_year: Optional[int] = None, end_year: Optional[int] = None) -> List[HistoricalEvent]:
        entries = self.entries
        if start_year is not None:
            entries = [e for e in entries if e.year >= start_year]
        if end_year is not None:
            entries = [e for e in entries if e.year <= end_year]
        return entries

    def compare_years(self, year_a: int, year_b: int) -> Dict[str, List[HistoricalEvent]]:
        """Section 88: 'compare YEAR X versus YEAR Y'."""
        return {
            str(year_a): [e for e in self.entries if e.year == year_a],
            str(year_b): [e for e in self.entries if e.year == year_b],
        }

    def to_dict(self) -> List[dict]:
        return [
            {"year": e.year, "day": e.day, "type": e.type, "description": e.description, "payload": e.payload}
            for e in self.entries
        ]


def _describe(event: Event) -> str:
    p = event.payload
    templates = {
        "CITY_FOUNDED": "{settlement} was founded in {region} by the {faction}.",
        "CITY_CAPTURED": "{settlement} fell to the {faction}.",
        "WAR_DECLARED": "The {faction} declared war upon the {enemy}.",
        "WAR_ENDED": "The war between the {faction} and the {enemy} ended.",
        "PEACE_SIGNED": "The {faction} and the {enemy} signed a peace.",
        "ALLIANCE_FORMED": "The {faction} and the {enemy} formed an alliance.",
        "BATTLE_STARTED": "Battle was joined near {location}.",
        "BATTLE_ENDED": "The battle near {location} ended: {outcome}.",
        "HERO_DIED": "{hero} of the {faction} has fallen.",
        "HERO_PROMOTED": "{hero} was raised to level {level}.",
        "KINGDOM_COLLAPSED": "The realm of the {faction} has collapsed.",
        "SETTLEMENT_GREW": "{settlement} grew to {tier}.",
        "AGE_CHANGED": "The world entered the {age}.",
        "ARMY_DESTROYED": "The army '{army}' of the {faction} was destroyed.",
        "FORTRESS_BUILT": "A fortress rose at {settlement}.",
        "ROAD_BUILT": "A road was completed linking {a} and {b}.",
        "ARTIFACT_DISCOVERED": "The artifact '{artifact}' was discovered.",
        "KING_BORN": "{name} was born to the {faction}.",
        "KING_DIED": "{name} of the {faction} has died.",
    }
    template = templates.get(event.type)
    if not template:
        return f"{event.type}: {p}"
    try:
        return template.format(**p)
    except KeyError:
        return f"{event.type}: {p}"
