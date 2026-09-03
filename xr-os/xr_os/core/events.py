"""
A small synchronous event bus shared by every subsystem.

XR-OS deliberately avoids a heavyweight message broker for in-process
communication: this is the same pattern used to fan out tracking updates,
input events, haptic triggers and notifications to whichever services and
applications subscribed to them.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, TypeVar

T = TypeVar("T")
Handler = Callable[[Any], None]


class EventBus:
    """Topic-based synchronous publish/subscribe bus."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, topic: str, handler: Handler) -> Callable[[], None]:
        """Register ``handler`` for ``topic``. Returns an unsubscribe callable."""
        self._handlers[topic].append(handler)

        def unsubscribe() -> None:
            handlers = self._handlers.get(topic, [])
            if handler in handlers:
                handlers.remove(handler)

        return unsubscribe

    def unsubscribe_all(self, topic: str) -> None:
        self._handlers.pop(topic, None)

    def publish(self, topic: str, payload: Any = None) -> int:
        """Synchronously deliver ``payload`` to every subscriber of ``topic``.

        Returns the number of handlers invoked. A handler exception is
        swallowed (spatial/input systems must not be brought down by one
        misbehaving subscriber) but recorded via ``on_handler_error``.
        """
        handlers = list(self._handlers.get(topic, ()))
        for handler in handlers:
            try:
                handler(payload)
            except Exception as exc:  # noqa: BLE001 - isolate subscriber faults
                self.on_handler_error(topic, handler, exc)
        return len(handlers)

    def on_handler_error(self, topic: str, handler: Handler, exc: Exception) -> None:
        """Override or monkeypatch to route subscriber errors to logging/telemetry."""
        import logging

        logging.getLogger("xr_os.events").exception(
            "handler %r for topic %r raised", handler, topic, exc_info=exc
        )

    def topic_count(self, topic: str) -> int:
        return len(self._handlers.get(topic, ()))
