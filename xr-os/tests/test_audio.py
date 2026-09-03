"""Spatial audio tests: attenuation, panning, occlusion."""

import pytest

from xr_os.audio.spatial_audio import AudioSource, SpatialAudioEngine
from xr_os.core.math3d import Quaternion, Vector3
from xr_os.scene.graph import XRSceneGraph
from xr_os.scene.nodes import WallNode


def test_closer_source_has_higher_gain():
    engine = SpatialAudioEngine()
    near = engine.add_source(AudioSource("beep", position=Vector3(1, 0, 0)))
    far = engine.add_source(AudioSource("boom", position=Vector3(10, 0, 0)))
    mixes = {m.source_id: m for m in engine.update()}
    assert mixes[near.id].gain > mixes[far.id].gain


def test_source_directly_ahead_has_zero_pan():
    engine = SpatialAudioEngine()
    engine.set_listener_pose(Vector3.zero(), Quaternion.identity())
    source = engine.add_source(AudioSource("beep", position=Vector3(0, 0, -2)))
    mix = engine.update()[0]
    assert mix.pan == pytest.approx(0.0, abs=1e-6)


def test_source_to_the_right_pans_right():
    engine = SpatialAudioEngine()
    engine.set_listener_pose(Vector3.zero(), Quaternion.identity())
    source = engine.add_source(AudioSource("beep", position=Vector3(2, 0, 0)))
    mix = engine.update()[0]
    assert mix.pan > 0.0


def test_source_beyond_max_distance_is_silent():
    engine = SpatialAudioEngine()
    source = engine.add_source(AudioSource("beep", position=Vector3(100, 0, 0), max_distance=10))
    mix = engine.update()[0]
    assert mix.gain == pytest.approx(0.0)


def test_wall_between_listener_and_source_occludes(world_model):
    scene = XRSceneGraph(world_model)
    wall = WallNode("wall", bounding_radius=2.0)
    from xr_os.core.math3d import Transform

    wall.local_transform = Transform(Vector3(0, 0, -1))
    scene.add_virtual(wall)

    engine = SpatialAudioEngine(scene)
    engine.set_listener_pose(Vector3.zero(), Quaternion.identity())
    source = engine.add_source(AudioSource("beep", position=Vector3(0, 0, -3)))
    mix = engine.update()[0]
    assert mix.occluded is True


def test_stopped_source_is_excluded_from_mix():
    engine = SpatialAudioEngine()
    engine.add_source(AudioSource("beep", position=Vector3(1, 0, 0), playing=False))
    assert engine.update() == []


def test_attached_source_follows_scene_node(world_model):
    from xr_os.core.math3d import Transform
    from xr_os.scene.nodes import ModelNode

    scene = XRSceneGraph(world_model)
    node = ModelNode("speaker", local_transform=Transform(Vector3(3, 0, 0)))
    scene.add_virtual(node)

    engine = SpatialAudioEngine(scene)
    source = engine.add_source(AudioSource("hum", attached_node_id=node.id))
    engine.update()
    assert source.position.as_tuple() == pytest.approx((3.0, 0.0, 0.0))
