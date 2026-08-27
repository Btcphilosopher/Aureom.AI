"""Compound clips: a nested, independently editable storyline that behaves
like a single clip from the outside.

Editing inside a compound clip (trimming, adding a transition) changes the
compound clip's outer duration automatically, since its ``duration`` is
computed from the nested storyline rather than cached.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from finalcut_engine.core.timebase import Time
from finalcut_engine.timeline.clip import TimelineItem
from finalcut_engine.timeline.storyline import Storyline


@dataclass
class CompoundClip(TimelineItem):
    name: str
    nested: Storyline
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    @property
    def duration(self) -> Time:
        return self.nested.duration
