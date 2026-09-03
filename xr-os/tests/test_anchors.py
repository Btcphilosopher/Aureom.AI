"""Spatial anchor engine tests."""

import pytest

from xr_os.anchors.anchor_engine import AnchorType, SpatialAnchorEngine
from xr_os.core.math3d import Quaternion, Transform, Vector3
from xr_os.core.spatial_object import SpatialObject, SpatialObjectType


def test_local_anchor_resolves_to_its_own_transform(world_model):
    engine = SpatialAnchorEngine(world_model)
    anchor = engine.create_local_anchor(Vector3(1, 2, 3))
    transform = engine.resolve(anchor.id)
    assert transform.position.as_tuple() == pytest.approx((1.0, 2.0, 3.0))
    assert anchor.type == AnchorType.LOCAL


def test_object_anchor_tracks_moving_target(world_model):
    table = world_model.add(SpatialObject(type=SpatialObjectType.TABLE, position=(0, 0, 0)))
    engine = SpatialAnchorEngine(world_model)
    anchor = engine.create_object_anchor(table.id, offset=Transform(Vector3(0, 0.8, 0)))

    transform = engine.resolve(anchor.id)
    assert transform.position.as_tuple() == pytest.approx((0.0, 0.8, 0.0))

    world_model.update(table.id, position=(2, 0, 0))
    transform_after_move = engine.resolve(anchor.id)
    assert transform_after_move.position.as_tuple() == pytest.approx((2.0, 0.8, 0.0))


def test_object_anchor_resolves_none_when_target_missing(world_model):
    engine = SpatialAnchorEngine(world_model)
    anchor = engine.create_object_anchor("does-not-exist")
    assert engine.resolve(anchor.id) is None


def test_attach_and_resolve_for_object(world_model):
    engine = SpatialAnchorEngine(world_model)
    anchor = engine.create_persistent_anchor(Vector3(5, 0, 0))
    engine.attach("virtual_screen_1", anchor)
    resolved = engine.resolve_for_object("virtual_screen_1")
    assert resolved.position.as_tuple() == pytest.approx((5.0, 0.0, 0.0))

    engine.detach("virtual_screen_1")
    assert engine.resolve_for_object("virtual_screen_1") is None


def test_room_and_geographic_anchor_creation(world_model):
    engine = SpatialAnchorEngine(world_model)
    room_anchor = engine.create_room_anchor("room-1", Vector3(0, 0, 0))
    geo_anchor = engine.create_geographic_anchor(latitude=51.5, longitude=-0.1, altitude=10.0)

    assert room_anchor.type == AnchorType.ROOM
    assert geo_anchor.type == AnchorType.GEOGRAPHIC
    assert engine.by_type(AnchorType.ROOM) == [room_anchor]
    assert engine.by_type(AnchorType.GEOGRAPHIC) == [geo_anchor]


def test_remove_anchor_clears_attachments(world_model):
    engine = SpatialAnchorEngine(world_model)
    anchor = engine.create_local_anchor(Vector3.zero())
    engine.attach("obj1", anchor)
    engine.remove(anchor.id)
    assert engine.get(anchor.id) is None
    assert engine.resolve_for_object("obj1") is None


class _InMemoryAnchorStore:
    def __init__(self) -> None:
        self.saved = []

    def save_anchors(self, anchors):
        self.saved = list(anchors)

    def load_anchors(self):
        return list(self.saved)


def test_anchor_store_persists_and_reloads(world_model):
    store = _InMemoryAnchorStore()
    engine = SpatialAnchorEngine(world_model, store=store)
    engine.create_persistent_anchor(Vector3(1, 1, 1), label="desk-screen")

    reloaded = SpatialAnchorEngine(world_model, store=store)
    assert len(reloaded.all()) == 1
    assert reloaded.all()[0].label == "desk-screen"
