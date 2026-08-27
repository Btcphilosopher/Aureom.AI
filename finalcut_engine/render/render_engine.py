"""Ties the magnetic timeline to the render graph: "render me the frame at time t".

This is the integration point between ``timeline``, ``colour``, ``effects``,
``motion`` and ``render`` — the render engine itself contains almost no
pixel-processing logic; it just figures out *which* clip(s) are active at a
given time and builds/evaluates the right graph for each.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from finalcut_engine.core.timebase import Time
from finalcut_engine.effects.compositing import composite
from finalcut_engine.effects.filters import FilterStack
from finalcut_engine.render.cache import RenderCache
from finalcut_engine.render.render_graph import ColourNode, EffectNode, OutputNode, RenderGraph, SourceNode, TransformNode
from finalcut_engine.timeline.clip import Clip
from finalcut_engine.timeline.compound_clip import CompoundClip
from finalcut_engine.timeline.magnetic_timeline import MagneticTimeline
from finalcut_engine.timeline.transitions import Transition

FrameLoader = Callable[[str, Time], np.ndarray]


def blank_frame(size: tuple[int, int]) -> np.ndarray:
    h, w = size
    return np.zeros((h, w, 3), dtype=np.float64)


@dataclass
class RenderEngine:
    frame_loader: FrameLoader
    frame_size: tuple[int, int] = (1080, 1920)  # (height, width)
    cache: RenderCache = field(default_factory=RenderCache)

    # -- per-clip graph construction -----------------------------------
    def build_clip_graph(self, clip: Clip) -> RenderGraph:
        node = SourceNode(clip.asset_id, self.frame_loader)
        if clip.transform is not None:
            transform_at = clip.transform.as_callable() if hasattr(clip.transform, "as_callable") else (lambda t, tr=clip.transform: tr)
            node = TransformNode(node, transform_at)
        if clip.colour_grade is not None:
            node = ColourNode(node, clip.colour_grade)
        if clip.effects:
            stack = clip.effects if isinstance(clip.effects, FilterStack) else FilterStack(list(clip.effects))
            node = EffectNode(node, stack)
        return RenderGraph(OutputNode(node))

    def render_clip_at(self, clip: Clip, source_time: Time) -> np.ndarray:
        graph = self.build_clip_graph(clip)
        return graph.evaluate(source_time, self.cache)

    # -- whole-timeline rendering --------------------------------------
    def render_frame(self, timeline: MagneticTimeline, t: Time) -> np.ndarray:
        found = timeline.primary.item_at_time(t)
        if found is None:
            return blank_frame(self.frame_size)
        item, local_t = found
        frame = self._render_item(timeline, item, local_t)

        for connected in timeline.connected.values():
            if connected.lane <= 0 or not isinstance(connected.item, Clip):
                continue  # lane <= 0 reserved for audio-only attachments
            abs_start = timeline.absolute_position_of_connected(connected.id)
            if abs_start <= t < abs_start + connected.duration:
                overlay = self.render_clip_at(connected.item, connected.item.source_range.start + (t - abs_start))
                frame = composite(frame, overlay, opacity=1.0)

        return frame

    def _render_item(self, timeline: MagneticTimeline, item, local_t: Time) -> np.ndarray:
        if isinstance(item, Clip):
            return self.render_clip_at(item, item.source_range.start + local_t)

        if isinstance(item, CompoundClip):
            inner = item.nested.item_at_time(local_t)
            if inner is None:
                return blank_frame(self.frame_size)
            inner_item, inner_local_t = inner
            return self._render_item(timeline, inner_item, inner_local_t)

        if isinstance(item, Transition):
            return self._render_transition(timeline, item, local_t)

        return blank_frame(self.frame_size)

    def _render_transition(self, timeline: MagneticTimeline, transition: Transition, local_t: Time) -> np.ndarray:
        """Crossfade the outgoing and incoming clips across the transition window.

        Each neighbour was shortened by half the transition's duration at the
        shared edge when the transition was created (see
        ``Storyline.add_transition``); the transition itself replays a
        ``duration``-length window straddling that cut from each side —
        exactly the footage the shortening borrowed — so both sides supply a
        full ``duration`` of source content to dissolve between.
        """
        outgoing = timeline.primary.get(transition.outgoing_item_id)
        incoming = timeline.primary.get(transition.incoming_item_id)
        half = transition.duration / 2

        outgoing_time = outgoing.source_range.end - half + local_t
        incoming_time = incoming.source_range.start - half + local_t

        outgoing_frame = self.render_clip_at(outgoing, outgoing_time)
        incoming_frame = self.render_clip_at(incoming, incoming_time)

        alpha = local_t.seconds() / transition.duration.seconds() if transition.duration.value > 0 else 1.0
        return composite(outgoing_frame, incoming_frame, opacity=alpha)

    def node_count_for(self, clip: Clip) -> int:
        return self.build_clip_graph(clip).node_count()
