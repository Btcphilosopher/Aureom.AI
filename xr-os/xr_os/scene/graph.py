"""XRSceneGraph: the root scene graph, splitting physical (ROOM) from authored (VIRTUAL_WORLD) content."""

from __future__ import annotations

from dataclasses import dataclass

from xr_os.core.math3d import Vector3
from xr_os.core.spatial_object import SpatialObject
from xr_os.core.world_model import SpatialWorldModel
from xr_os.scene.node import SceneNode
from xr_os.scene.nodes import (
    ChairNode,
    DoorNode,
    FloorNode,
    PersonNode,
    PhysicalObjectNode,
    RoomNode,
    TableNode,
    VirtualWorldNode,
    WallNode,
    WindowNode,
)

from xr_os.core.spatial_object import SpatialObjectType

_PHYSICAL_NODE_CLASSES: dict[SpatialObjectType, type[SceneNode]] = {
    SpatialObjectType.WALL: WallNode,
    SpatialObjectType.FLOOR: FloorNode,
    SpatialObjectType.DOOR: DoorNode,
    SpatialObjectType.WINDOW: WindowNode,
    SpatialObjectType.TABLE: TableNode,
    SpatialObjectType.CHAIR: ChairNode,
    SpatialObjectType.OBJECT: PhysicalObjectNode,
    SpatialObjectType.PERSON: PersonNode,
}


@dataclass
class RaycastHit:
    node: SceneNode
    distance: float
    point: Vector3


class XRSceneGraph:
    """
    XR WORLD
      +-- ROOM (physical geometry, mirrored from the SpatialWorldModel)
      +-- VIRTUAL WORLD (application-authored content)
    """

    def __init__(self, world_model: SpatialWorldModel | None = None) -> None:
        self.root = SceneNode("xr_world")
        self.room = RoomNode("room")
        self.virtual_world = VirtualWorldNode("virtual_world")
        self.root.add_child(self.room)
        self.root.add_child(self.virtual_world)
        self.world_model = world_model
        self._mirrored: dict[str, SceneNode] = {}  # spatial_object_id -> node in .room

    # -- physical mirroring ------------------------------------------------

    def sync_from_world_model(self) -> None:
        """Mirror WALL/FLOOR/TABLE/... SpatialObjects from the world model into ``room``."""
        if self.world_model is None:
            return
        live_ids: set[str] = set()
        for obj in self.world_model.all():
            node_cls = _PHYSICAL_NODE_CLASSES.get(obj.type)
            if node_cls is None:
                continue
            live_ids.add(obj.id)
            self._sync_object(obj, node_cls)
        # drop nodes for objects that vanished from the world model
        for stale_id in set(self._mirrored) - live_ids:
            node = self._mirrored.pop(stale_id)
            if node.parent is not None:
                node.parent.remove_child(node)

    def _sync_object(self, obj: SpatialObject, node_cls: type[SceneNode]) -> SceneNode:
        node = self._mirrored.get(obj.id)
        if node is None:
            node = node_cls(obj.label or obj.type.value, node_id=obj.id, spatial_object_id=obj.id)
            self._mirrored[obj.id] = node
            self.room.add_child(node)
        node.local_transform = obj.transform
        return node

    # -- virtual content -----------------------------------------------------

    def add_virtual(self, node: SceneNode, parent: SceneNode | None = None) -> SceneNode:
        (parent or self.virtual_world).add_child(node)
        return node

    # -- queries -------------------------------------------------------------

    def find(self, node_id: str) -> SceneNode | None:
        return self.root.find(node_id)

    def all_nodes(self) -> list[SceneNode]:
        return list(self.root.traverse())

    def interactable_nodes(self) -> list[SceneNode]:
        return [n for n in self.root.traverse() if n.interactable and n.is_effectively_visible()]

    def raycast(self, origin: Vector3, direction: Vector3, max_distance: float = 10.0) -> RaycastHit | None:
        """Sphere-based hit test: nearest interactable/collidable node whose
        bounding sphere the ray intersects. Sufficient for pointing/gaze
        interaction and simulation; a renderer-backed implementation would
        replace this with true mesh raycasting."""
        direction = direction.normalized()
        best: RaycastHit | None = None
        for node in self.root.traverse():
            if not (node.interactable or node.collidable) or not node.is_effectively_visible():
                continue
            center = node.world_position
            to_center = center - origin
            t = to_center.dot(direction)
            if t < 0 or t > max_distance:
                continue
            closest_point = origin + direction * t
            if closest_point.distance_to(center) <= node.bounding_radius:
                if best is None or t < best.distance:
                    best = RaycastHit(node=node, distance=t, point=closest_point)
        return best
