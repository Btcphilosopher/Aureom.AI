"""Connected clips: B-roll/audio attached to a point on the primary storyline.

A connected clip's timeline position is ``anchor.start + offset`` where
``anchor.start`` is *derived* (see :mod:`finalcut_engine.timeline.storyline`),
never stored absolutely. That is the entire mechanism behind "connected clips
stay logically attached to their anchor when it moves or resizes."
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from finalcut_engine.core.timebase import Time
from finalcut_engine.timeline.clip import TimelineItem


@dataclass
class ConnectedClip:
    """Wraps a :class:`TimelineItem` (usually a ``Clip``) anchored to a storyline item."""

    item: TimelineItem
    anchor_item_id: str
    offset: Time  # from the anchor's start
    lane: int = 1  # positive: video/B-roll lanes above primary; negative: audio lanes below
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    @property
    def duration(self) -> Time:
        return self.item.duration

    def clamped_offset(self, anchor_duration: Time) -> Time:
        """Offset clamped so the connection never starts past its anchor's end."""
        if self.offset > anchor_duration:
            return anchor_duration
        return self.offset
