"""Logical playback clock and playhead.

This models the timing contract a real AVFoundation/CoreMedia playback layer
would fulfil (a monotonic host clock mapped to timeline time at a rate), so
the render/playback engine can be built and tested without real audio/video
hardware, and later swapped for a native `CMClock`-backed implementation
without changing callers.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, List

from finalcut_engine.core.timebase import Time


@dataclass
class Clock:
    """Maps wall-clock time to timeline time at a configurable rate.

    ``rate`` of 1.0 is normal forward playback, 0.0 is paused, negative values
    play in reverse, and values like 2.0 / 0.5 model fast-forward / slow-mo
    scrubbing — all without touching timeline data.
    """

    timescale: int = 600_600
    _position: Time = field(default_factory=lambda: Time.zero())
    rate: float = 0.0
    _host_reference: float = field(default_factory=time.monotonic)
    _listeners: List[Callable[[Time], None]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._position = Time.zero(self.timescale)

    # -- transport ------------------------------------------------------
    def play(self, rate: float = 1.0) -> None:
        self._sync()
        self.rate = rate

    def pause(self) -> None:
        self._sync()
        self.rate = 0.0

    def seek(self, position: Time) -> None:
        self._position = position.rescaled(self.timescale)
        self._host_reference = time.monotonic()
        self._notify()

    def _sync(self) -> None:
        """Fold elapsed wall-clock time into ``_position`` before a rate change."""
        self._position = self.position
        self._host_reference = time.monotonic()

    @property
    def position(self) -> Time:
        if self.rate == 0.0:
            return self._position
        elapsed = time.monotonic() - self._host_reference
        delta = Time.from_seconds(elapsed * self.rate, self.timescale)
        return self._position + delta

    def is_playing(self) -> bool:
        return self.rate != 0.0

    def on_tick(self, callback: Callable[[Time], None]) -> None:
        self._listeners.append(callback)

    def _notify(self) -> None:
        for cb in self._listeners:
            cb(self.position)

    def tick(self) -> Time:
        """Call periodically from a UI/render loop; fires listeners with the current position."""
        pos = self.position
        self._notify()
        return pos
