"""
SceneNode: the base building block of the XR scene graph.

    XR WORLD
    |
    +-- ROOM
    |    +-- WALL / FLOOR / TABLE / OBJECT
    |
    +-- VIRTUAL WORLD
         +-- PANEL / MODEL / AVATAR / UI

Supports parent/child relationships with transform inheritance, visibility,
collision, interaction, and per-node permissions (which apps may see or act
on a node).
"""

from __future__ import annotations

import uuid
from typing import Callable, Iterator

from xr_os.core.math3d import Transform, Vector3
from xr_os.core.spatial_object import SpatialObjectType

InteractionHandler = Callable[["SceneNode", str, dict], None]


class SceneNode:
    """
    A node in the XR scene graph.

    ``local_transform`` is relative to ``parent``; ``world_transform`` folds
    the full ancestor chain. A node may optionally mirror a live
    ``SpatialObject`` (via ``spatial_object_id``) for physical geometry
    reconstructed by SLAM/CV, or be pure virtual content authored by an app.
    """

    def __init__(
        self,
        name: str,
        node_type: SpatialObjectType = SpatialObjectType.OBJECT,
        local_transform: Transform | None = None,
        node_id: str | None = None,
        *,
        visible: bool = True,
        collidable: bool = False,
        interactable: bool = False,
        bounding_radius: float = 0.25,
        spatial_object_id: str | None = None,
    ) -> None:
        self.id = node_id or uuid.uuid4().hex
        self.name = name
        self.node_type = node_type
        self.local_transform = local_transform or Transform.identity()
        self.visible = visible
        self.collidable = collidable
        self.interactable = interactable
        self.bounding_radius = bounding_radius
        self.spatial_object_id = spatial_object_id
        self.permissions: set[str] = set()
        self.metadata: dict = {}

        self.parent: "SceneNode | None" = None
        self.children: list["SceneNode"] = []
        self._interaction_handlers: list[InteractionHandler] = []

    # -- hierarchy ---------------------------------------------------

    def add_child(self, child: "SceneNode") -> "SceneNode":
        if child.parent is not None:
            child.parent.remove_child(child)
        child.parent = self
        self.children.append(child)
        return child

    def remove_child(self, child: "SceneNode") -> None:
        if child in self.children:
            self.children.remove(child)
            child.parent = None

    def reparent_to(self, new_parent: "SceneNode") -> None:
        new_parent.add_child(self)

    def traverse(self) -> Iterator["SceneNode"]:
        yield self
        for child in self.children:
            yield from child.traverse()

    def find(self, node_id: str) -> "SceneNode | None":
        for node in self.traverse():
            if node.id == node_id:
                return node
        return None

    def find_by_name(self, name: str) -> list["SceneNode"]:
        return [n for n in self.traverse() if n.name == name]

    def depth(self) -> int:
        d, node = 0, self
        while node.parent is not None:
            d += 1
            node = node.parent
        return d

    # -- transforms ------------------------------------------------------

    @property
    def world_transform(self) -> Transform:
        if self.parent is None:
            return self.local_transform
        return self.parent.world_transform.combine(self.local_transform)

    @property
    def world_position(self) -> Vector3:
        return self.world_transform.position

    def set_world_position(self, position: Vector3) -> None:
        """Reposition this node so its world position equals ``position``,
        keeping its local rotation/scale, by solving for the required local
        translation under the current parent transform."""
        if self.parent is None:
            self.local_transform = Transform(position, self.local_transform.rotation, self.local_transform.scale)
            return
        parent_inv = self.parent.world_transform.inverse()
        local_pos = parent_inv.transform_point(position)
        self.local_transform = Transform(local_pos, self.local_transform.rotation, self.local_transform.scale)

    # -- visibility / collision inheritance -------------------------------

    def is_effectively_visible(self) -> bool:
        node = self
        while node is not None:
            if not node.visible:
                return False
            node = node.parent
        return True

    # -- interaction -------------------------------------------------------

    def on_interact(self, handler: InteractionHandler) -> None:
        self._interaction_handlers.append(handler)

    def interact(self, event_type: str, payload: dict | None = None) -> bool:
        """Dispatch an interaction (e.g. a resolved input event) to this node.

        Returns True if the node accepted the interaction (is interactable
        and had at least one handler invoked).
        """
        if not self.interactable:
            return False
        for handler in self._interaction_handlers:
            handler(self, event_type, payload or {})
        return True

    # -- permissions -------------------------------------------------------

    def grant(self, app_id: str) -> None:
        self.permissions.add(app_id)

    def revoke(self, app_id: str) -> None:
        self.permissions.discard(app_id)

    def is_visible_to(self, app_id: str) -> bool:
        """Nodes with no explicit permission set are visible to everyone."""
        return not self.permissions or app_id in self.permissions

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"SceneNode(id={self.id[:8]}, name={self.name!r}, type={self.node_type.value})"
