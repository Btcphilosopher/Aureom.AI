"""SpatialObject + SpatialWorldModel tests."""

import time

import pytest

from xr_os.core.math3d import Vector3
from xr_os.core.spatial_object import SpatialObject, SpatialObjectType
from xr_os.core.world_model import SpatialWorldModel, Zone


def test_spatial_object_defaults_and_transform():
    obj = SpatialObject(type=SpatialObjectType.TABLE, position=(1, 0, 2))
    assert obj.confidence == 1.0
    assert obj.transform.position.as_tuple() == (1.0, 0.0, 2.0)


def test_spatial_object_touch_updates_timestamp_and_confidence():
    obj = SpatialObject(type=SpatialObjectType.OBJECT, timestamp=0.0)
    obj.touch(confidence=0.42)
    assert obj.confidence == 0.42
    assert obj.timestamp > 0.0


def test_spatial_object_stale_detection():
    obj = SpatialObject(type=SpatialObjectType.OBJECT, timestamp=time.time() - 100)
    assert obj.is_stale(max_age_seconds=1.0)
    assert not obj.is_stale(max_age_seconds=1000.0)


def test_world_model_add_get_remove(world_model: SpatialWorldModel):
    obj = SpatialObject(type=SpatialObjectType.CHAIR)
    world_model.add(obj)
    assert world_model.get(obj.id) is obj
    assert len(world_model) == 1
    removed = world_model.remove(obj.id)
    assert removed is obj
    assert world_model.get(obj.id) is None


def test_world_model_publishes_events(world_model: SpatialWorldModel):
    events: list[str] = []
    world_model.events.subscribe("world.object.added", lambda o: events.append("added"))
    world_model.events.subscribe("world.object.updated", lambda o: events.append("updated"))
    world_model.events.subscribe("world.object.removed", lambda o: events.append("removed"))

    obj = SpatialObject(type=SpatialObjectType.TABLE)
    world_model.add(obj)
    world_model.update(obj.id, label="kitchen table")
    world_model.remove(obj.id)

    assert events == ["added", "updated", "removed"]


def test_world_model_by_type_and_children(world_model: SpatialWorldModel):
    parent = world_model.add(SpatialObject(type=SpatialObjectType.ROOM))
    child = world_model.add(SpatialObject(type=SpatialObjectType.TABLE, parent_id=parent.id))
    world_model.add(SpatialObject(type=SpatialObjectType.CHAIR, parent_id=parent.id))

    assert world_model.by_type(SpatialObjectType.TABLE) == [child]
    assert len(world_model.children_of(parent.id)) == 2


def test_world_model_nearest_and_within_radius(world_model: SpatialWorldModel):
    near = world_model.add(SpatialObject(type=SpatialObjectType.OBJECT, position=(0.1, 0, 0)))
    far = world_model.add(SpatialObject(type=SpatialObjectType.OBJECT, position=(5, 0, 0)))

    nearest = world_model.nearest(Vector3.zero(), obj_type=SpatialObjectType.OBJECT)
    assert nearest.id == near.id

    within = world_model.within_radius(Vector3.zero(), radius=1.0, obj_type=SpatialObjectType.OBJECT)
    assert near in within and far not in within


def test_world_model_prune_stale(world_model: SpatialWorldModel):
    stale = world_model.add(SpatialObject(type=SpatialObjectType.OBJECT, timestamp=time.time() - 1000))
    fresh = world_model.add(SpatialObject(type=SpatialObjectType.OBJECT))
    removed = world_model.prune_stale(max_age_seconds=1.0)
    assert stale.id in removed
    assert world_model.get(fresh.id) is not None


def test_zone_contains_point(world_model: SpatialWorldModel):
    zone = Zone(id="z1", label="kitchen", center=(0, 0, 0), half_extents=(2, 2, 2))
    world_model.add_zone(zone)
    assert zone.contains((1, 1, 1))
    assert not zone.contains((3, 0, 0))
    assert world_model.zones_containing((0, 0, 0)) == [zone]
