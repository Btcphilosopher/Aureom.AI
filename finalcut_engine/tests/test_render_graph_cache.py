from __future__ import annotations

import numpy as np

from finalcut_engine.colour.colour_board import ColourBoard
from finalcut_engine.colour.colour_pipeline import ColourPipeline
from finalcut_engine.colour.exposure import ExposureParams
from finalcut_engine.core.timebase import Time, TimeRange
from finalcut_engine.render.cache import RenderCache
from finalcut_engine.render.render_engine import RenderEngine
from finalcut_engine.render.render_graph import ColourNode, OutputNode, RenderGraph, SourceNode
from finalcut_engine.timeline.clip import Clip
from finalcut_engine.timeline.magnetic_timeline import MagneticTimeline


def _counting_loader():
    calls = {"count": 0}

    def loader(asset_id, t):
        calls["count"] += 1
        return np.full((4, 4, 3), 0.5)

    return loader, calls


def test_render_cache_avoids_redundant_source_decode():
    loader, calls = _counting_loader()
    source = SourceNode("A", loader)
    graph = RenderGraph(OutputNode(source))
    cache = RenderCache()

    graph.evaluate(Time.from_seconds(1.0), cache)
    graph.evaluate(Time.from_seconds(1.0), cache)  # identical time -> should hit cache
    assert calls["count"] == 1

    graph.evaluate(Time.from_seconds(2.0), cache)  # different time -> new decode
    assert calls["count"] == 2


def test_changing_downstream_colour_does_not_invalidate_upstream_source_cache():
    loader, calls = _counting_loader()
    source = SourceNode("A", loader)
    pipeline_1 = ColourPipeline(colour=ColourBoard(exposure=ExposureParams(exposure_stops=0.1)))
    pipeline_2 = ColourPipeline(colour=ColourBoard(exposure=ExposureParams(exposure_stops=0.5)))

    cache = RenderCache()
    t = Time.from_seconds(1.0)

    graph1 = RenderGraph(OutputNode(ColourNode(source, pipeline_1)))
    frame1 = graph1.evaluate(t, cache)
    assert calls["count"] == 1

    # Same source, different colour pipeline object: the source decode is
    # reused from cache (still 1 call) even though the final frame differs.
    graph2 = RenderGraph(OutputNode(ColourNode(source, pipeline_2)))
    frame2 = graph2.evaluate(t, cache)
    assert calls["count"] == 1
    assert not np.allclose(frame1, frame2)


def test_render_engine_transition_crossfades_between_neighbours(synthetic_frame_loader):
    engine = RenderEngine(frame_loader=synthetic_frame_loader, frame_size=(4, 4))
    tl = MagneticTimeline()
    x = Clip(asset_id="X", source_range=TimeRange(Time.zero(), Time.from_seconds(3)))
    y = Clip(asset_id="Y", source_range=TimeRange(Time.zero(), Time.from_seconds(3)))
    tl.append_clip(x)
    tl.append_clip(y)
    tl.add_transition(x.id, Time.from_seconds(1.0))  # transition occupies [2.5, 3.5)

    pure_x = engine.render_frame(tl, Time.from_seconds(0.5))[0, 0]
    pure_y = engine.render_frame(tl, Time.from_seconds(5.0))[0, 0]
    mid = engine.render_frame(tl, Time.from_seconds(3.0))[0, 0]

    assert np.allclose(pure_x, [1, 0, 0])
    assert np.allclose(pure_y, [0, 1, 0])
    assert np.allclose(mid, [0.5, 0.5, 0.0], atol=1e-6)


def test_render_engine_composites_connected_broll_overlay(synthetic_frame_loader):
    engine = RenderEngine(frame_loader=synthetic_frame_loader, frame_size=(4, 4))
    tl = MagneticTimeline()
    base = Clip(asset_id="X", source_range=TimeRange(Time.zero(), Time.from_seconds(4)))
    tl.append_clip(base)
    overlay = Clip(asset_id="Y", source_range=TimeRange(Time.zero(), Time.from_seconds(1)))
    tl.connect_clip(base.id, overlay, Time.from_seconds(1.0), lane=1)

    under_overlay = engine.render_frame(tl, Time.from_seconds(1.5))[0, 0]
    outside_overlay = engine.render_frame(tl, Time.from_seconds(3.0))[0, 0]
    assert np.allclose(under_overlay, [0, 1, 0])  # overlay fully covers, opaque
    assert np.allclose(outside_overlay, [1, 0, 0])
