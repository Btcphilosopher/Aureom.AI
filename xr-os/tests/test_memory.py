"""Persistent spatial memory tests: hierarchy and room recognition."""

import pytest

from xr_os.memory.spatial_memory import PlaceKind, RoomFingerprint, SpatialMemory


@pytest.fixture
def memory() -> SpatialMemory:
    mem = SpatialMemory(":memory:")
    yield mem
    mem.close()


def test_create_and_get_place(memory: SpatialMemory):
    place = memory.create_place("Home", PlaceKind.HOME)
    fetched = memory.get(place.id)
    assert fetched is not None
    assert fetched.name == "Home"
    assert fetched.kind == PlaceKind.HOME


def test_hierarchy_children(memory: SpatialMemory):
    home = memory.create_place("Home", PlaceKind.HOME)
    living_room = memory.create_place("Living Room", PlaceKind.ROOM, parent_id=home.id)
    memory.create_place("TV", PlaceKind.OBJECT, parent_id=living_room.id)
    memory.create_place("Sofa", PlaceKind.OBJECT, parent_id=living_room.id)

    children_of_home = memory.children(home.id)
    assert [c.name for c in children_of_home] == ["Living Room"]

    children_of_room = memory.children(living_room.id)
    assert {c.name for c in children_of_room} == {"TV", "Sofa"}


def test_tree_builds_nested_structure(memory: SpatialMemory):
    home = memory.create_place("Home", PlaceKind.HOME)
    memory.create_place("Office", PlaceKind.ROOM, parent_id=home.id)
    tree = memory.tree()
    assert tree["children"][0]["name"] == "Home"
    assert tree["children"][0]["children"][0]["name"] == "Office"


def test_delete_cascades_to_children(memory: SpatialMemory):
    home = memory.create_place("Home", PlaceKind.HOME)
    room = memory.create_place("Room", PlaceKind.ROOM, parent_id=home.id)
    obj = memory.create_place("Desk", PlaceKind.OBJECT, parent_id=room.id)

    memory.delete(room.id)
    assert memory.get(room.id) is None
    assert memory.get(obj.id) is None
    assert memory.get(home.id) is not None


def test_recognize_room_matches_similar_fingerprint(memory: SpatialMemory):
    fingerprint = RoomFingerprint(floor_area=20.0, wall_count=4, avg_wall_length=4.0, ceiling_height=2.4)
    room = memory.create_place("Living Room", PlaceKind.ROOM, fingerprint=fingerprint)

    observed = RoomFingerprint(floor_area=19.5, wall_count=4, avg_wall_length=3.9, ceiling_height=2.4)
    match = memory.recognize_room(observed)
    assert match is not None
    matched_room, score = match
    assert matched_room.id == room.id
    assert score > 0.9


def test_recognize_room_rejects_dissimilar_fingerprint(memory: SpatialMemory):
    fingerprint = RoomFingerprint(floor_area=20.0, wall_count=4, avg_wall_length=4.0, ceiling_height=2.4)
    memory.create_place("Living Room", PlaceKind.ROOM, fingerprint=fingerprint)

    observed = RoomFingerprint(floor_area=2.0, wall_count=4, avg_wall_length=1.0, ceiling_height=2.4)
    assert memory.recognize_room(observed, min_similarity=0.9) is None


def test_persistence_across_reopen(tmp_path):
    db_path = tmp_path / "spatial_memory.db"
    mem = SpatialMemory(db_path)
    place = mem.create_place("Home", PlaceKind.HOME)
    mem.close()

    reopened = SpatialMemory(db_path)
    fetched = reopened.get(place.id)
    assert fetched is not None
    assert fetched.name == "Home"
    reopened.close()
