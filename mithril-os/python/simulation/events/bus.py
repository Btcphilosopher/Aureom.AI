"""
Event bus.

Spec ref: 68 (event bus), 34 (world history engine consumes these events).

Every meaningful state change in the simulation is published as an Event
here. Systems never call each other directly to report "something
happened" — they publish an event, and any interested system (notably
`history.chronicle.Chronicle`) subscribes. This keeps causality legible:
the event log IS the audit trail of section 108's causal graph.

Determinism: publish() delivers synchronously and in subscription order,
which is itself insertion order (a plain list) — no dict/set iteration of
handlers, so replay (section 61) reproduces identical handler ordering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List


@dataclass
class Event:
    type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    tick: int = -1
    year: int = -1
    day: int = -1


Handler = Callable[[Event], None]


class EventBus:
    def __init__(self) -> None:
        self._handlers: Dict[str, List[Handler]] = {}
        self._wildcard: List[Handler] = []
        self.log: List[Event] = []

    def subscribe(self, event_type: str, handler: Handler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    def subscribe_all(self, handler: Handler) -> None:
        self._wildcard.append(handler)

    def publish(self, event: Event) -> None:
        self.log.append(event)
        for handler in self._handlers.get(event.type, []):
            handler(event)
        for handler in self._wildcard:
            handler(event)


# Canonical event type names (section 68).
UNIT_CREATED = "UNIT_CREATED"
UNIT_MOVED = "UNIT_MOVED"
UNIT_ATTACKED = "UNIT_ATTACKED"
UNIT_DIED = "UNIT_DIED"
ARMY_CREATED = "ARMY_CREATED"
ARMY_DESTROYED = "ARMY_DESTROYED"
BATTLE_STARTED = "BATTLE_STARTED"
BATTLE_ENDED = "BATTLE_ENDED"
CITY_FOUNDED = "CITY_FOUNDED"
CITY_CAPTURED = "CITY_CAPTURED"
BUILDING_COMPLETED = "BUILDING_COMPLETED"
RESOURCE_DEPLETED = "RESOURCE_DEPLETED"
TRADE_ROUTE_CREATED = "TRADE_ROUTE_CREATED"
WAR_DECLARED = "WAR_DECLARED"
PEACE_SIGNED = "PEACE_SIGNED"
HERO_DIED = "HERO_DIED"
HERO_PROMOTED = "HERO_PROMOTED"
AGE_CHANGED = "AGE_CHANGED"
KINGDOM_COLLAPSED = "KINGDOM_COLLAPSED"
SETTLEMENT_GREW = "SETTLEMENT_GREW"
SETTLEMENT_STARVING = "SETTLEMENT_STARVING"
