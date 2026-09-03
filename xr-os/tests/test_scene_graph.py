"""Scene-graph tests: hierarchy, transform inheritance, visibility, permissions, raycast."""

import pytest

from xr_os.core.math3d import Quaternion, Transform, Vector3
from xr_os.core.spatial_object import SpatialObject, SpatialObjectType
from xr_os.scene.graph import XRSceneGraph
from xr_os.scene.node import SceneNode
from xr_os.scene.nodes import ModelNode, TableNode


def test_add_child_sets_parent():
    root = SceneNode("root")
    child = SceneNode("child")
    root.add_child(child)
    assert child.parent is root
    assert child in root.children


def test_reparent_moves_child():
    a = SceneNode("a")
    b = SceneNode("b")
    child = SceneNode("child")
    a.add_child(child)
    b.add_child(child)
    assert child.parent is b
    assert child not in a.children


def test_world_transform_inherits_from_parent():
    parent = SceneNode("parent", local_transform=Transform(Vector3(1, 0, 0)))
    child = SceneNode("child", local_transform=Transform(Vector3(0, 1, 0)))
    parent.add_child(child)
    assert child.world_transform.position.as_tuple() == pytest.approx((1.0, 1.0, 0.0))


def test_set_world_position_solves_local_transform():
    parent = SceneNode("parent", local_transform=Transform(Vector3(5, 0, 0), Quaternion.from_axis_angle(Vector3(0, 1, 0), 1.5)))
    child = SceneNode("child")
    parent.add_child(child)
    child.set_world_position(Vector3(5, 2, 0))
    assert child.world_position.as_tuple() == pytest.approx((5.0, 2.0, 0.0), abs=1e-6)


def test_visibility_is_inherited():
    parent = SceneNode("parent", visible=False)
    child = SceneNode("child", visible=True)
    parent.add_child(child)
    assert not child.is_effectively_visible()
    parent.visible = True
    assert child.is_effectively_visible()


def test_interaction_dispatch_requires_interactable():
    node = SceneNode("n", interactable=False)
    calls = []
    node.on_interact(lambda n, e, p: calls.append(e))
    assert node.interact("click") is False
    assert calls == []

    node.interactable = True
    assert node.interact("click") is True
    assert calls == ["click"]


def test_permissions_default_visible_to_everyone():
    node = SceneNode("n")
    assert node.is_visible_to("any_app")
    node.grant("app_a")
    assert node.is_visible_to("app_a")
    assert not node.is_visible_to("app_b")


def test_traverse_and_find():
    root = SceneNode("root")
    a = root.add_child(SceneNode("a"))
    b = a.add_child(SceneNode("b"))
    ids = {n.id for n in root.traverse()}
    assert ids == {root.id, a.id, b.id}
    assert root.find(b.id) is b


def test_scene_graph_room_and_virtual_world_split(scene_graph: XRSceneGraph):
    table = TableNode("table")
    model = ModelNode("cube")
    scene_graph.room.add_child(table)
    scene_graph.add_virtual(model)
    assert table.parent is scene_graph.room
    assert model.parent is scene_graph.virtual_world


def test_scene_graph_syncs_physical_objects_from_world_model(world_model, scene_graph: XRSceneGraph):
    obj = world_model.add(SpatialObject(type=SpatialObjectType.TABLE, position=(1, 0, 0)))
    scene_graph.sync_from_world_model()
    node = scene_graph.find(obj.id)
    assert node is not None
    assert node.parent is scene_graph.room
    assert node.world_position.as_tuple() == pytest.approx((1.0, 0.0, 0.0))

    world_model.remove(obj.id)
    scene_graph.sync_from_world_model()
    assert scene_graph.find(obj.id) is None


def test_raycast_hits_nearest_interactable_node(scene_graph: XRSceneGraph):
    near = ModelNode("near", local_transform=Transform(Vector3(0, 0, -1)))
    far = ModelNode("far", local_transform=Transform(Vector3(0, 0, -5)))
    scene_graph.add_virtual(near)
    scene_graph.add_virtual(far)

    hit = scene_graph.raycast(Vector3.zero(), Vector3(0, 0, -1))
    assert hit is not None
    assert hit.node.id == near.id


def test_raycast_misses_when_nothing_in_path(scene_graph: XRSceneGraph):
    scene_graph.add_virtual(ModelNode("off_axis", local_transform=Transform(Vector3(5, 5, 5))))
    assert scene_graph.raycast(Vector3.zero(), Vector3(0, 0, -1)) is None
