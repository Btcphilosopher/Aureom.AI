"""The magnetic timeline: a primary storyline plus clips connected to it.

```
PRIMARY STORYLINE

[ A ] [ B ] [ C ] [ D ]

          |
          +-- Connected B-roll
          |
          +-- Audio
```

Connected clips (and connected secondary storylines) are stored keyed by
their own id, each remembering only *which primary-storyline item it is
anchored to* and its offset from that item's start. Their absolute timeline
position is computed on demand from the anchor's (also derived) position, so
they automatically "ride along" when the primary storyline changes shape.
"""
from __future__ import annotations

import logging
import uuid
from typing import Dict, List, Optional, Tuple

from finalcut_engine.core.events import EventBus
from finalcut_engine.core.timebase import FPS_24, FrameRate, Time
from finalcut_engine.timeline.clip import Clip, TimelineItem
from finalcut_engine.timeline.compound_clip import CompoundClip
from finalcut_engine.timeline.connected_clip import ConnectedClip
from finalcut_engine.timeline.storyline import Storyline, StorylineError
from finalcut_engine.timeline.transitions import Transition, TransitionKind

logger = logging.getLogger("finalcut_engine.timeline")


class MagneticTimeline:
    """A complete magnetic-timeline sequence: one primary storyline plus
    everything connected to it.
    """

    def __init__(self, name: str = "Timeline", frame_rate: FrameRate = FPS_24, events: Optional[EventBus] = None):
        self.id = uuid.uuid4().hex
        self.name = name
        self.frame_rate = frame_rate
        self.primary = Storyline(name="Primary Storyline")
        self.connected: Dict[str, ConnectedClip] = {}
        self.secondary_storylines: Dict[str, Storyline] = {}
        self.events = events or EventBus()

    # -- primary storyline: composition -----------------------------------
    def append_clip(self, item: TimelineItem) -> TimelineItem:
        result = self.primary.append_clip(item)
        self._changed("append_clip", item_id=item.id)
        return result

    def insert_clip(self, index: int, item: TimelineItem) -> TimelineItem:
        result = self.primary.insert_clip(index, item)
        self._changed("insert_clip", item_id=item.id, index=index)
        return result

    def move_clip(self, item_id: str, target_index: int) -> None:
        self.primary.move_clip(item_id, target_index)
        self._changed("move_clip", item_id=item_id, target_index=target_index)

    def split_clip(self, item_id: str, offset: Time) -> Tuple[Clip, Clip]:
        result = self.primary.split_clip(item_id, offset)
        self._changed("split_clip", item_id=item_id)
        return result

    # -- primary storyline: trimming -----------------------------------------
    def trim_clip(self, item_id: str, delta: Time) -> None:
        """Roll trim: see :meth:`Storyline.trim_clip`. Never ripples downstream."""
        self.primary.trim_clip(item_id, delta)
        self._changed("trim_clip", item_id=item_id, delta_seconds=delta.seconds())

    def ripple_trim(self, item_id: str, new_duration: Time, edge: str = "end") -> TimelineItem:
        """Single-sided trim that ripples everything after ``item_id``.

        Connected clips anchored further down the primary storyline need no
        adjustment: their position is derived from the (now different)
        cumulative duration automatically.
        """
        result = self.primary.ripple_trim(item_id, new_duration, edge=edge)
        self._changed("ripple_trim", item_id=item_id, new_duration_seconds=new_duration.seconds())
        return result

    # -- primary storyline: deletion / replacement --------------------------
    def delete_clip(self, item_id: str, ripple: bool = True) -> TimelineItem:
        """Delete a primary-storyline item.

        If ``ripple`` fully removes the item, any clips connected to it are
        re-anchored (never silently dropped) to the item that now precedes
        where it was — or to the following item if it was first — at an
        offset clamped to that anchor's duration.
        """
        idx = self.primary.index_of(item_id)
        removed = self.primary.delete_clip(item_id, ripple=ripple)
        if ripple:
            self._reanchor_orphans(item_id, idx)
        self._changed("delete_clip", item_id=item_id, ripple=ripple)
        return removed

    def _reanchor_orphans(self, removed_id: str, removed_index: int) -> None:
        orphans = [c for c in self.connected.values() if c.anchor_item_id == removed_id]
        if not orphans:
            return
        if removed_index > 0:
            new_anchor = self.primary.items[removed_index - 1]
            new_offset = new_anchor.duration
        elif self.primary.items:
            new_anchor = self.primary.items[0]
            new_offset = Time.zero()
        else:
            logger.warning("Deleted the last item on an empty primary storyline; %d connected clip(s) orphaned", len(orphans))
            for c in orphans:
                del self.connected[c.id]
            return
        for c in orphans:
            logger.info("Re-anchoring connected clip %s from deleted %s to %s", c.id, removed_id, new_anchor.id)
            c.anchor_item_id = new_anchor.id
            c.offset = new_offset

    def replace_clip(self, item_id: str, new_clip: Clip) -> TimelineItem:
        result = self.primary.replace_clip(item_id, new_clip)
        self._changed("replace_clip", item_id=item_id)
        return result

    def add_transition(
        self, before_item_id: str, duration: Time, kind: TransitionKind = TransitionKind.CROSS_DISSOLVE
    ) -> Transition:
        result = self.primary.add_transition(before_item_id, duration, kind=kind)
        self._changed("add_transition", before_item_id=before_item_id)
        return result

    # -- connections -------------------------------------------------------
    def connect_clip(self, anchor_item_id: str, item: TimelineItem, offset: Time, lane: int = 1) -> ConnectedClip:
        """Attach ``item`` (a clip, or a whole secondary storyline) to a point
        on the primary storyline.
        """
        self.primary.index_of(anchor_item_id)  # validates the anchor exists
        connected = ConnectedClip(item=item, anchor_item_id=anchor_item_id, offset=offset, lane=lane)
        self.connected[connected.id] = connected
        self._changed("connect_clip", connected_id=connected.id, anchor_item_id=anchor_item_id)
        return connected

    def disconnect_clip(self, connected_clip_id: str) -> TimelineItem:
        connected = self.connected.pop(connected_clip_id)
        self._changed("disconnect_clip", connected_id=connected_clip_id)
        return connected.item

    def create_storyline(self, name: str = "Secondary Storyline") -> Storyline:
        storyline = Storyline(name=name)
        self.secondary_storylines[storyline.id] = storyline
        return storyline

    def create_compound_clip(self, item_ids: List[str], name: str = "Compound Clip") -> CompoundClip:
        """Group a *contiguous* run of primary-storyline items into one nested clip."""
        indices = sorted(self.primary.index_of(i) for i in item_ids)
        if indices != list(range(indices[0], indices[0] + len(indices))):
            raise StorylineError("create_compound_clip requires a contiguous run of items")
        start, end = indices[0], indices[-1]
        extracted = self.primary.extract_range(start, end)
        nested = Storyline(name=f"{name} (nested)", items=list(extracted))
        compound = CompoundClip(name=name, nested=nested)
        self.primary.items[start : end + 1] = [compound]

        # Anything connected to one of the absorbed items now anchors to the compound.
        absorbed_ids = {item.id for item in extracted}
        for connected in self.connected.values():
            if connected.anchor_item_id in absorbed_ids:
                inner_offset = nested.item_start(connected.anchor_item_id)
                connected.anchor_item_id = compound.id
                connected.offset = inner_offset + connected.offset

        self._changed("create_compound_clip", compound_id=compound.id, item_ids=item_ids)
        return compound

    # -- queries -------------------------------------------------------------
    @property
    def duration(self) -> Time:
        return self.primary.duration

    def absolute_position_of_connected(self, connected_clip_id: str) -> Time:
        connected = self.connected[connected_clip_id]
        anchor = self.primary.get(connected.anchor_item_id)
        anchor_start = self.primary.item_start(connected.anchor_item_id)
        return anchor_start + connected.clamped_offset(anchor.duration)

    def connected_at_lane(self, lane: int) -> List[ConnectedClip]:
        return [c for c in self.connected.values() if c.lane == lane]

    def _changed(self, op: str, **payload) -> None:
        self.events.publish("timeline_changed", source=self, op=op, **payload)
