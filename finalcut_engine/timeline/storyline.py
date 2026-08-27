"""The magnetic storyline: an ordered, gap-aware, position-free sequence of clips.

The key architectural decision is that **no item stores its own timeline
position**. A position is always derived by summing the durations of the
items before it. Every ripple-style edit (``ripple_trim``, ``delete_clip``
with ``ripple=True``, ``move_clip``) therefore needs to touch nothing but the
edited item itself — everything downstream is automatically in the right
place the next time its position is asked for. This is what the spec calls
clips "remaining logically attached to their anchor positions".
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from finalcut_engine.core.timebase import Time
from finalcut_engine.timeline.clip import Clip, TimelineItem
from finalcut_engine.timeline.gap import Gap
from finalcut_engine.timeline.transitions import Transition, TransitionKind


class StorylineError(ValueError):
    pass


@dataclass
class Storyline(TimelineItem):
    """An ordered sequence of :class:`TimelineItem`.

    A ``Storyline`` is itself a ``TimelineItem`` (it has an ``id`` and a
    ``duration``), so a whole secondary storyline can be connected to the
    primary storyline as a single attached unit, exactly like a clip.
    """

    name: str = "Storyline"
    items: List[TimelineItem] = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    # -- derived positions ---------------------------------------------------
    @property
    def duration(self) -> Time:
        total = Time.zero()
        for item in self.items:
            total = total + item.duration
        return total

    def item_start(self, item_id: str) -> Time:
        offset = Time.zero()
        for item in self.items:
            if item.id == item_id:
                return offset
            offset = offset + item.duration
        raise StorylineError(f"no item with id {item_id!r}")

    def item_at_time(self, t: Time) -> Optional[Tuple[TimelineItem, Time]]:
        """The item covering ``t``, and ``t``'s offset within that item."""
        offset = Time.zero()
        for item in self.items:
            end = offset + item.duration
            if offset <= t < end:
                return item, t - offset
            offset = end
        return None

    def index_of(self, item_id: str) -> int:
        for i, item in enumerate(self.items):
            if item.id == item_id:
                return i
        raise StorylineError(f"no item with id {item_id!r}")

    def get(self, item_id: str) -> TimelineItem:
        return self.items[self.index_of(item_id)]

    # -- basic composition ----------------------------------------------
    def append_clip(self, item: TimelineItem) -> TimelineItem:
        self.items.append(item)
        return item

    def insert_clip(self, index: int, item: TimelineItem) -> TimelineItem:
        index = max(0, min(index, len(self.items)))
        self.items.insert(index, item)
        return item

    def move_clip(self, item_id: str, target_index: int) -> None:
        idx = self.index_of(item_id)
        item = self.items.pop(idx)
        target_index = max(0, min(target_index, len(self.items)))
        self.items.insert(target_index, item)

    def split_clip(self, item_id: str, offset: Time) -> Tuple[Clip, Clip]:
        idx = self.index_of(item_id)
        item = self.items[idx]
        if not isinstance(item, Clip):
            raise TypeError("only Clip items can be split")
        left, right = item.split_at(offset)
        self.items[idx : idx + 1] = [left, right]
        return left, right

    # -- trimming ------------------------------------------------------------
    @staticmethod
    def _resized(item: TimelineItem, new_duration: Time, grow_at_end: bool) -> TimelineItem:
        if new_duration.value <= 0:
            raise StorylineError("resize would collapse an item to zero or negative duration")
        if isinstance(item, Clip):
            if grow_at_end:
                return item.trimmed(new_out=item.source_range.start + new_duration)
            return item.trimmed(new_in=item.source_range.end - new_duration)
        if isinstance(item, Gap):
            return item.resized(new_duration)
        raise TypeError(f"cannot resize items of type {type(item).__name__}")

    def ripple_trim(self, item_id: str, new_duration: Time, edge: str = "end") -> TimelineItem:
        """Change one item's duration; every later item shifts implicitly.

        ``edge='end'`` keeps the in-point fixed and moves the out-point
        (classic ripple trim); ``edge='start'`` keeps the out-point fixed.
        """
        idx = self.index_of(item_id)
        resized = self._resized(self.items[idx], new_duration, grow_at_end=(edge == "end"))
        self.items[idx] = resized
        return resized

    def trim_clip(self, item_id: str, delta: Time) -> None:
        """Roll the edit point between ``item_id`` and the next item by ``delta``.

        Positive ``delta`` extends ``item_id`` and shortens its neighbour by
        the same amount, so the storyline's *total* duration — and everything
        after the pair — is unaffected. This is the "trim" tool; use
        :meth:`ripple_trim` for a single-sided trim that shifts everything
        downstream instead.
        """
        idx = self.index_of(item_id)
        if idx >= len(self.items) - 1:
            raise StorylineError("no following item to roll the edit point against")
        a, b = self.items[idx], self.items[idx + 1]
        new_a_duration = a.duration + delta
        new_b_duration = b.duration - delta
        self.items[idx] = self._resized(a, new_a_duration, grow_at_end=True)
        self.items[idx + 1] = self._resized(b, new_b_duration, grow_at_end=False)

    # -- deletion / replacement -----------------------------------------
    def delete_clip(self, item_id: str, ripple: bool = True) -> TimelineItem:
        """Remove an item. ``ripple=False`` ("lift") leaves a same-sized Gap in its place."""
        idx = self.index_of(item_id)
        removed = self.items[idx]
        if ripple:
            del self.items[idx]
        else:
            self.items[idx] = Gap(_duration=removed.duration)
        return removed

    def replace_clip(self, item_id: str, new_clip: Clip) -> TimelineItem:
        """Swap a clip's content. If the new clip is longer it is fitted (trimmed)
        to the old duration so the timeline does not ripple; if shorter, the
        storyline ripples down to the new, shorter duration.
        """
        idx = self.index_of(item_id)
        old = self.items[idx]
        if not isinstance(old, Clip):
            raise TypeError("can only replace a Clip")
        if new_clip.duration >= old.duration:
            fitted = new_clip.trimmed(new_out=new_clip.source_range.start + old.duration)
        else:
            fitted = new_clip
        fitted.id = old.id
        self.items[idx] = fitted
        return old

    # -- transitions -----------------------------------------------------
    def add_transition(
        self, before_item_id: str, duration: Time, kind: TransitionKind = TransitionKind.CROSS_DISSOLVE
    ) -> Transition:
        """Insert a transition at the boundary after ``before_item_id``.

        Each neighbouring clip is shortened by half the transition length at
        the shared edge (borrowed from its existing visible duration), so the
        storyline's total duration is unchanged.
        """
        idx = self.index_of(before_item_id)
        if idx >= len(self.items) - 1:
            raise StorylineError("no following clip to transition into")
        a, b = self.items[idx], self.items[idx + 1]
        if not isinstance(a, Clip) or not isinstance(b, Clip):
            raise TypeError("transitions require a Clip on both sides")

        half_seconds = min(duration.seconds() / 2, a.duration.seconds() / 2, b.duration.seconds() / 2)
        half = Time.from_seconds(half_seconds, duration.timescale)
        actual_duration = half * 2

        new_a = a.trimmed(new_out=a.source_range.end - half)
        new_b = b.trimmed(new_in=b.source_range.start + half)
        transition = Transition(_duration=actual_duration, outgoing_item_id=a.id, incoming_item_id=b.id, kind=kind)
        self.items[idx : idx + 2] = [new_a, transition, new_b]
        return transition

    # -- extraction --------------------------------------------------------
    def extract_range(self, start_index: int, end_index: int) -> List[TimelineItem]:
        """Items in ``[start_index, end_index]`` inclusive — used by compound clips."""
        if not (0 <= start_index <= end_index < len(self.items)):
            raise StorylineError("invalid item range")
        return self.items[start_index : end_index + 1]
