"""A minimal synchronous publish/subscribe event bus.

Every subsystem (timeline, render engine, background scheduler, undo manager)
publishes structured events here instead of holding direct references to a UI
layer. This keeps the engine usable headless (scripts, tests, a future Swift
UI over a bridge) since nothing subscribes unless something chooses to.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, DefaultDict, List

logger = logging.getLogger("finalcut_engine.events")


@dataclass
class Event:
    name: str
    payload: dict = field(default_factory=dict)
    source: object | None = None


Listener = Callable[[Event], None]


class EventBus:
    """Synchronous fan-out event bus. Listener exceptions never propagate."""

    def __init__(self) -> None:
        self._listeners: DefaultDict[str, List[Listener]] = defaultdict(list)
        self._wildcard_listeners: List[Listener] = []

    def subscribe(self, name: str, listener: Listener) -> Callable[[], None]:
        """Subscribe to events named ``name``. Returns an unsubscribe callable."""
        self._listeners[name].append(listener)
        return lambda: self._listeners[name].remove(listener)

    def subscribe_all(self, listener: Listener) -> Callable[[], None]:
        self._wildcard_listeners.append(listener)
        return lambda: self._wildcard_listeners.remove(listener)

    def publish(self, name: str, source: object | None = None, **payload: Any) -> None:
        event = Event(name=name, payload=payload, source=source)
        for listener in list(self._listeners.get(name, ())):
            self._safe_call(listener, event)
        for listener in list(self._wildcard_listeners):
            self._safe_call(listener, event)

    @staticmethod
    def _safe_call(listener: Listener, event: Event) -> None:
        try:
            listener(event)
        except Exception:  # noqa: BLE001 - a bad listener must never break the engine
            logger.exception("Unhandled exception in listener for event %r", event.name)
