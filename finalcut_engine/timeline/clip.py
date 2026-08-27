"""Timeline items: the base interface, and the primary :class:`Clip` type.

A ``Clip`` never stores its own timeline position. Positions are always
*derived* by summing the durations of preceding items in a storyline — this
is what makes the timeline "magnetic": ripple a clip's duration and every
item after it (and anything connected to those items) is automatically in
the right place, with nothing extra to update.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, List, Optional

from finalcut_engine.core.timebase import Time, TimeRange
from finalcut_engine.timeline.roles import DEFAULT_VIDEO_ROLE, Role


class TimelineItem(ABC):
    """Anything that can occupy a slot in a :class:`~finalcut_engine.timeline.storyline.Storyline`."""

    id: str

    @property
    @abstractmethod
    def duration(self) -> Time: ...


@dataclass
class Clip(TimelineItem):
    """An edited instance of a media asset (or generator/title) on the timeline.

    ``source_range`` is expressed in the *source media's* timebase (its native
    frame rate); the clip's timeline duration is exactly ``source_range.duration``
    — this prototype does not implement speed retiming.
    """

    asset_id: str
    source_range: TimeRange
    name: str = ""
    role: Role = field(default_factory=lambda: DEFAULT_VIDEO_ROLE)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    #: Non-destructive processing stacks. Left duck-typed (rather than
    #: importing finalcut_engine.effects/.colour/.motion here) so the timeline
    #: module has no compile-time dependency on those subsystems.
    effects: List[Any] = field(default_factory=list)
    colour_grade: Optional[Any] = None
    transform: Optional[Any] = None

    #: Per-clip audio trim (independent gain riding on top of the mixer graph).
    gain_db: float = 0.0

    @property
    def duration(self) -> Time:
        return self.source_range.duration

    def trimmed(self, *, new_in: Optional[Time] = None, new_out: Optional[Time] = None) -> "Clip":
        """Return a copy of this clip with an adjusted source range."""
        start = new_in if new_in is not None else self.source_range.start
        end = new_out if new_out is not None else self.source_range.end
        clone = Clip(
            asset_id=self.asset_id,
            source_range=TimeRange.from_start_end(start, end),
            name=self.name,
            role=self.role,
            id=self.id,
            effects=list(self.effects),
            colour_grade=self.colour_grade,
            transform=self.transform,
            gain_db=self.gain_db,
        )
        return clone

    def split_at(self, offset: Time) -> tuple["Clip", "Clip"]:
        """Split into two clips at ``offset`` (relative to this clip's start)."""
        if not (Time.zero(offset.timescale) < offset < self.duration):
            raise ValueError("split offset must fall strictly inside the clip")
        cut_point = self.source_range.start + offset
        left = self.trimmed(new_out=cut_point)
        right = Clip(
            asset_id=self.asset_id,
            source_range=TimeRange.from_start_end(cut_point, self.source_range.end),
            name=self.name,
            role=self.role,
            effects=list(self.effects),
            colour_grade=self.colour_grade,
            transform=self.transform,
            gain_db=self.gain_db,
        )
        left.id = self.id
        return left, right
