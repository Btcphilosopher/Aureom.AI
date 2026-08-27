"""An explicit empty span in a storyline.

Deleting a clip with "lift" (as opposed to ripple delete) replaces it with a
``Gap`` of the same duration, so everything else on the timeline — including
connected clips anchored to later items — does not move.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from finalcut_engine.core.timebase import Time
from finalcut_engine.timeline.clip import TimelineItem


@dataclass
class Gap(TimelineItem):
    _duration: Time
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    @property
    def duration(self) -> Time:
        return self._duration

    def resized(self, new_duration: Time) -> "Gap":
        return Gap(_duration=new_duration, id=self.id)
