"""Placement of spatial UI relative to head, hands, room, an object, or world coordinates."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from xr_os.core.math3d import Transform
from xr_os.core.world_model import SpatialWorldModel
from xr_os.tracking.engine import TrackingEngine
from xr_os.tracking.types import TrackedTarget


class RelativeTo(str, Enum):
    WORLD = "world"
    HEAD = "head"
    LEFT_HAND = "left_hand"
    RIGHT_HAND = "right_hand"
    ROOM = "room"
    OBJECT = "object"


_TARGET_BY_RELATIVE_TO = {
    RelativeTo.HEAD: TrackedTarget.HEAD,
    RelativeTo.LEFT_HAND: TrackedTarget.LEFT_HAND,
    RelativeTo.RIGHT_HAND: TrackedTarget.RIGHT_HAND,
}


@dataclass
class PlacementRef:
    """Where a UI element should be anchored, and its offset within that frame."""

    relative_to: RelativeTo = RelativeTo.WORLD
    offset: Transform = Transform.identity()
    object_id: str | None = None  # required when relative_to == OBJECT/ROOM


def resolve_placement(
    ref: PlacementRef,
    tracking_engine: TrackingEngine | None = None,
    world_model: SpatialWorldModel | None = None,
) -> Transform:
    """Resolve a ``PlacementRef`` to a concrete world-space ``Transform``."""
    if ref.relative_to == RelativeTo.WORLD:
        return ref.offset

    if ref.relative_to in _TARGET_BY_RELATIVE_TO:
        if tracking_engine is None:
            return ref.offset
        pose = tracking_engine.get_pose(_TARGET_BY_RELATIVE_TO[ref.relative_to])
        if pose is None:
            return ref.offset
        return pose.transform.combine(ref.offset)

    if ref.relative_to in (RelativeTo.ROOM, RelativeTo.OBJECT):
        if world_model is None or ref.object_id is None:
            return ref.offset
        obj = world_model.get(ref.object_id)
        if obj is None:
            return ref.offset
        return obj.transform.combine(ref.offset)

    return ref.offset
