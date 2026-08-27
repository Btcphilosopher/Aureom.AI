"""The high-level, UI-facing API.

Every mutating call here goes through the undo/redo engine (spec section 23)
as a named :class:`~finalcut_engine.core.state.Command`, and every subsystem
stays reachable directly (``api.engine.library``, ``api.engine.render_engine``,
...) for anything this façade doesn't wrap. The intent is that a UI —
SwiftUI, a CLI, a test — only ever needs to import this module.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, List, Optional

import numpy as np

from finalcut_engine.core.engine import FinalCutEngine
from finalcut_engine.core.state import Command
from finalcut_engine.core.timebase import Time
from finalcut_engine.library.event import Event
from finalcut_engine.timeline.clip import Clip, TimelineItem
from finalcut_engine.timeline.compound_clip import CompoundClip
from finalcut_engine.timeline.connected_clip import ConnectedClip
from finalcut_engine.timeline.magnetic_timeline import MagneticTimeline
from finalcut_engine.timeline.storyline import Storyline
from finalcut_engine.timeline.transitions import Transition, TransitionKind


# -- generic, snapshot-based timeline command -------------------------------
@dataclass
class TimelineCommand(Command):
    """Wraps one :class:`MagneticTimeline` mutation as a reversible command.

    Rather than hand-writing an inverse for every timeline operation, this
    snapshots the primary storyline and connected-clip state before applying
    ``action`` and restores it verbatim on undo — correct by construction for
    any mutation, at the cost of an O(n) copy per edit (fine at editorial
    timescales; a native implementation could switch to structural diffing).
    """

    label: str
    timeline: MagneticTimeline
    action: Callable[[MagneticTimeline], Any]
    result: Any = field(default=None, init=False)
    _saved_items: list = field(default_factory=list, init=False)
    _saved_connected: dict = field(default_factory=dict, init=False)

    def do(self) -> None:
        self._saved_items = copy.deepcopy(self.timeline.primary.items)
        self._saved_connected = copy.deepcopy(self.timeline.connected)
        self.result = self.action(self.timeline)

    def undo(self) -> None:
        self.timeline.primary.items = self._saved_items
        self.timeline.connected = self._saved_connected


def InsertClipCommand(timeline: MagneticTimeline, index: int, item: TimelineItem) -> TimelineCommand:
    return TimelineCommand("Insert Clip", timeline, lambda tl: tl.insert_clip(index, item))


def AppendClipCommand(timeline: MagneticTimeline, item: TimelineItem) -> TimelineCommand:
    return TimelineCommand("Append Clip", timeline, lambda tl: tl.append_clip(item))


def TrimClipCommand(timeline: MagneticTimeline, item_id: str, delta: Time) -> TimelineCommand:
    return TimelineCommand("Trim Clip", timeline, lambda tl: tl.trim_clip(item_id, delta))


def RippleTrimCommand(timeline: MagneticTimeline, item_id: str, new_duration: Time, edge: str = "end") -> TimelineCommand:
    return TimelineCommand("Ripple Trim", timeline, lambda tl: tl.ripple_trim(item_id, new_duration, edge=edge))


def DeleteClipCommand(timeline: MagneticTimeline, item_id: str, ripple: bool = True) -> TimelineCommand:
    return TimelineCommand("Delete Clip", timeline, lambda tl: tl.delete_clip(item_id, ripple=ripple))


def ReplaceClipCommand(timeline: MagneticTimeline, item_id: str, new_clip: Clip) -> TimelineCommand:
    return TimelineCommand("Replace Clip", timeline, lambda tl: tl.replace_clip(item_id, new_clip))


def MoveClipCommand(timeline: MagneticTimeline, item_id: str, target_index: int) -> TimelineCommand:
    return TimelineCommand("Move Clip", timeline, lambda tl: tl.move_clip(item_id, target_index))


def ConnectClipCommand(timeline: MagneticTimeline, anchor_item_id: str, item: TimelineItem, offset: Time, lane: int = 1) -> TimelineCommand:
    return TimelineCommand("Connect Clip", timeline, lambda tl: tl.connect_clip(anchor_item_id, item, offset, lane=lane))


def DisconnectClipCommand(timeline: MagneticTimeline, connected_clip_id: str) -> TimelineCommand:
    return TimelineCommand("Disconnect Clip", timeline, lambda tl: tl.disconnect_clip(connected_clip_id))


def AddTransitionCommand(timeline: MagneticTimeline, before_item_id: str, duration: Time, kind: TransitionKind = TransitionKind.CROSS_DISSOLVE) -> TimelineCommand:
    return TimelineCommand("Add Transition", timeline, lambda tl: tl.add_transition(before_item_id, duration, kind=kind))


def CreateCompoundClipCommand(timeline: MagneticTimeline, item_ids: List[str], name: str = "Compound Clip") -> TimelineCommand:
    return TimelineCommand("Create Compound Clip", timeline, lambda tl: tl.create_compound_clip(item_ids, name=name))


@dataclass
class ApplyEffectCommand(Command):
    """Appends an effect to a clip's stack; undo pops exactly what was added."""

    label: str = field(default="Apply Effect", init=False)
    clip: Clip = None  # type: ignore[assignment]
    effect: Any = None

    def do(self) -> None:
        self.clip.effects.append(self.effect)

    def undo(self) -> None:
        self.clip.effects.remove(self.effect)


@dataclass
class ColourAdjustmentCommand(Command):
    """Swaps a clip's colour pipeline; undo restores the previous one exactly."""

    label: str = field(default="Colour Adjustment", init=False)
    clip: Clip = None  # type: ignore[assignment]
    new_pipeline: Any = None
    _previous: Any = field(default=None, init=False)

    def do(self) -> None:
        self._previous = self.clip.colour_grade
        self.clip.colour_grade = self.new_pipeline

    def undo(self) -> None:
        self.clip.colour_grade = self._previous


# -- the façade itself --------------------------------------------------------
@dataclass
class EngineAPI:
    engine: FinalCutEngine

    # -- media / library -----------------------------------------------
    def import_media(self, event: Event, paths: List[Path]) -> list:
        return self.engine.library.import_media(event, paths, self.engine.importer)

    def search_library(self, query: str) -> list:
        return self.engine.library.search(query)

    # -- editing (all go through undo/redo) ---------------------------------
    def insert_clip(self, timeline: MagneticTimeline, index: int, item: TimelineItem) -> TimelineItem:
        cmd = InsertClipCommand(timeline, index, item)
        self.engine.undo.execute(cmd)
        return cmd.result

    def append_clip(self, timeline: MagneticTimeline, item: TimelineItem) -> TimelineItem:
        cmd = AppendClipCommand(timeline, item)
        self.engine.undo.execute(cmd)
        return cmd.result

    def trim_clip(self, timeline: MagneticTimeline, item_id: str, delta: Time) -> None:
        self.engine.undo.execute(TrimClipCommand(timeline, item_id, delta))

    def ripple_trim(self, timeline: MagneticTimeline, item_id: str, new_duration: Time, edge: str = "end") -> None:
        self.engine.undo.execute(RippleTrimCommand(timeline, item_id, new_duration, edge=edge))

    def delete_clip(self, timeline: MagneticTimeline, item_id: str, ripple: bool = True) -> None:
        self.engine.undo.execute(DeleteClipCommand(timeline, item_id, ripple=ripple))

    def replace_clip(self, timeline: MagneticTimeline, item_id: str, new_clip: Clip) -> None:
        self.engine.undo.execute(ReplaceClipCommand(timeline, item_id, new_clip))

    def move_clip(self, timeline: MagneticTimeline, item_id: str, target_index: int) -> None:
        self.engine.undo.execute(MoveClipCommand(timeline, item_id, target_index))

    def connect_clip(self, timeline: MagneticTimeline, anchor_item_id: str, item: TimelineItem, offset: Time, lane: int = 1) -> ConnectedClip:
        cmd = ConnectClipCommand(timeline, anchor_item_id, item, offset, lane=lane)
        self.engine.undo.execute(cmd)
        return cmd.result

    def disconnect_clip(self, timeline: MagneticTimeline, connected_clip_id: str) -> TimelineItem:
        cmd = DisconnectClipCommand(timeline, connected_clip_id)
        self.engine.undo.execute(cmd)
        return cmd.result

    def create_storyline(self, timeline: MagneticTimeline, name: str = "Secondary Storyline") -> Storyline:
        # Creating a fresh, empty, unattached storyline has nothing to undo.
        return timeline.create_storyline(name)

    def create_compound_clip(self, timeline: MagneticTimeline, item_ids: List[str], name: str = "Compound Clip") -> CompoundClip:
        cmd = CreateCompoundClipCommand(timeline, item_ids, name=name)
        self.engine.undo.execute(cmd)
        return cmd.result

    def add_transition(self, timeline: MagneticTimeline, before_item_id: str, duration: Time, kind: TransitionKind = TransitionKind.CROSS_DISSOLVE) -> Transition:
        cmd = AddTransitionCommand(timeline, before_item_id, duration, kind=kind)
        self.engine.undo.execute(cmd)
        return cmd.result

    def apply_effect(self, clip: Clip, effect: Any) -> None:
        self.engine.undo.execute(ApplyEffectCommand(clip=clip, effect=effect))

    def adjust_colour(self, clip: Clip, pipeline: Any) -> None:
        self.engine.undo.execute(ColourAdjustmentCommand(clip=clip, new_pipeline=pipeline))

    def undo(self) -> Optional[str]:
        return self.engine.undo.undo()

    def redo(self) -> Optional[str]:
        return self.engine.undo.redo()

    # -- render / export -----------------------------------------------
    def render_frame(self, timeline: MagneticTimeline, t: Time) -> np.ndarray:
        if self.engine.render_engine is None:
            raise RuntimeError("EngineAPI was constructed without a frame_loader; no render engine is available")
        return self.engine.render_engine.render_frame(timeline, t)
