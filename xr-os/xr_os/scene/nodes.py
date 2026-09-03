"""Concrete scene-node kinds with sensible defaults for visibility/collision/interaction."""

from __future__ import annotations

from xr_os.core.math3d import Transform
from xr_os.core.spatial_object import SpatialObjectType
from xr_os.scene.node import SceneNode


class RoomNode(SceneNode):
    """Container for a physically reconstructed room."""

    def __init__(self, name: str = "room", **kwargs) -> None:
        super().__init__(name, SpatialObjectType.ROOM, collidable=False, interactable=False, **kwargs)


class WallNode(SceneNode):
    def __init__(self, name: str = "wall", **kwargs) -> None:
        kwargs.setdefault("collidable", True)
        super().__init__(name, SpatialObjectType.WALL, **kwargs)


class FloorNode(SceneNode):
    def __init__(self, name: str = "floor", **kwargs) -> None:
        kwargs.setdefault("collidable", True)
        super().__init__(name, SpatialObjectType.FLOOR, **kwargs)


class DoorNode(SceneNode):
    def __init__(self, name: str = "door", **kwargs) -> None:
        kwargs.setdefault("collidable", True)
        kwargs.setdefault("interactable", True)
        super().__init__(name, SpatialObjectType.DOOR, **kwargs)


class WindowNode(SceneNode):
    def __init__(self, name: str = "window", **kwargs) -> None:
        kwargs.setdefault("collidable", True)
        super().__init__(name, SpatialObjectType.WINDOW, **kwargs)


class TableNode(SceneNode):
    def __init__(self, name: str = "table", **kwargs) -> None:
        kwargs.setdefault("collidable", True)
        super().__init__(name, SpatialObjectType.TABLE, **kwargs)


class ChairNode(SceneNode):
    def __init__(self, name: str = "chair", **kwargs) -> None:
        kwargs.setdefault("collidable", True)
        super().__init__(name, SpatialObjectType.CHAIR, **kwargs)


class PhysicalObjectNode(SceneNode):
    """A generic reconstructed real-world object (from CV object detection)."""

    def __init__(self, name: str = "object", **kwargs) -> None:
        kwargs.setdefault("collidable", True)
        super().__init__(name, SpatialObjectType.OBJECT, **kwargs)


class PersonNode(SceneNode):
    def __init__(self, name: str = "person", **kwargs) -> None:
        super().__init__(name, SpatialObjectType.PERSON, **kwargs)


class VirtualWorldNode(SceneNode):
    """Container for all authored/virtual content."""

    def __init__(self, name: str = "virtual_world", **kwargs) -> None:
        super().__init__(name, SpatialObjectType.VIRTUAL_OBJECT, collidable=False, interactable=False, **kwargs)


class PanelNode(SceneNode):
    """A flat spatial surface -- the backing node for ``SpatialPanel`` UI."""

    def __init__(self, name: str = "panel", size: tuple[float, float] = (1.0, 1.0), **kwargs) -> None:
        kwargs.setdefault("interactable", True)
        super().__init__(name, SpatialObjectType.PANEL, **kwargs)
        self.size = size


class ModelNode(SceneNode):
    """A 3D virtual model/asset that can be grabbed, thrown, physically simulated."""

    def __init__(self, name: str = "model", **kwargs) -> None:
        kwargs.setdefault("collidable", True)
        kwargs.setdefault("interactable", True)
        super().__init__(name, SpatialObjectType.MODEL, **kwargs)


class AvatarNode(SceneNode):
    """A representation of a local or remote user in a multi-user session."""

    def __init__(self, name: str = "avatar", user_id: str | None = None, **kwargs) -> None:
        super().__init__(name, SpatialObjectType.AVATAR, **kwargs)
        self.user_id = user_id


class UINode(SceneNode):
    """A generic spatial UI element (button, menu, toolbar, notification, keyboard)."""

    def __init__(self, name: str = "ui", **kwargs) -> None:
        kwargs.setdefault("interactable", True)
        super().__init__(name, SpatialObjectType.UI, **kwargs)


def make_room(name: str = "room", transform: Transform | None = None) -> RoomNode:
    return RoomNode(name, local_transform=transform or Transform.identity())
