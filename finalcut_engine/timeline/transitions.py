"""Transitions between adjacent primary-storyline clips.

Modelled on how professional NLEs keep a dissolve from rippling the rest of
the timeline: the transition *borrows* half its duration from each
neighbour's existing edit point rather than requiring unused source handle.
A production renderer would prefer extending into real handle first (frames
beyond the currently-used in/out points) and only borrow visible duration as
a fallback; that extra step is left as a render-graph concern (see
``render.render_graph``) since it needs the source media's full duration,
which the timeline layer intentionally does not track.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum

from finalcut_engine.core.timebase import Time
from finalcut_engine.timeline.clip import TimelineItem


class TransitionKind(str, Enum):
    CROSS_DISSOLVE = "cross_dissolve"
    DIP_TO_BLACK = "dip_to_black"
    WIPE = "wipe"


@dataclass
class Transition(TimelineItem):
    """Occupies the overlap region between the two clips it joins."""

    _duration: Time
    outgoing_item_id: str
    incoming_item_id: str
    kind: TransitionKind = TransitionKind.CROSS_DISSOLVE
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    @property
    def duration(self) -> Time:
        return self._duration
