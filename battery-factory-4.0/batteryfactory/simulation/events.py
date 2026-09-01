"""
A minimal, dependency-free discrete-event simulation kernel (spec item 19).

Built from scratch (no simpy) so the platform has no hidden dependency for
its core simulation loop: a priority-queue calendar plus generator-based
"processes" that `yield env.timeout(delay)` to advance simulated time, in
the same idiom as classic DES libraries.
"""
from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass, field
from typing import Any, Callable, Generator, Optional


@dataclass(order=True)
class _QueueItem:
    time: float
    seq: int
    generator: Any = field(compare=False)


class Timeout:
    """Yielded by a process to suspend itself for `delay` simulated time units."""

    __slots__ = ("delay",)

    def __init__(self, delay: float) -> None:
        self.delay = max(delay, 0.0)


@dataclass
class Event:
    """A named, timestamped fact recorded on the simulation calendar."""

    time: float
    name: str
    payload: dict = field(default_factory=dict)


class Environment:
    def __init__(self) -> None:
        self.now: float = 0.0
        self._heap: list[_QueueItem] = []
        self._counter = itertools.count()
        self.event_log: list[Event] = []
        self.on_event: Optional[Callable[[Event], None]] = None

    def process(self, gen: Generator) -> None:
        self._resume(gen, None)

    def _resume(self, gen: Generator, value) -> None:
        try:
            yielded = gen.send(value)
        except StopIteration:
            return
        delay = yielded.delay if isinstance(yielded, Timeout) else 0.0
        heapq.heappush(self._heap, _QueueItem(self.now + delay, next(self._counter), gen))

    def log(self, name: str, **payload) -> None:
        evt = Event(self.now, name, payload)
        self.event_log.append(evt)
        if self.on_event is not None:
            self.on_event(evt)

    def run(self, until: float) -> None:
        while self._heap and self._heap[0].time <= until:
            item = heapq.heappop(self._heap)
            self.now = item.time
            self._resume(item.generator, None)
        self.now = until
