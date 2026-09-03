"""Spatial anchors: local, persistent, object-, room-, and geo-anchored content."""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Protocol

from pydantic import BaseModel, Field

from xr_os.core.math3d import Quaternion, Transform, Vector3
from xr_os.core.world_model import SpatialWorldModel


class AnchorType(str, Enum):
    LOCAL = "local"  # valid only for the current tracking session
    PERSISTENT = "persistent"  # survives across sessions, relocalized by SLAM
    OBJECT = "object"  # relative to a tracked real-world object's pose
    ROOM = "room"  # relative to a recognized room's origin
    GEOGRAPHIC = "geographic"  # world-scale, lat/lon/altitude + heading


class Anchor(BaseModel):
    """A stable reference frame that virtual content can be parented to."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    type: AnchorType = AnchorType.LOCAL
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    target_object_id: str | None = None  # for OBJECT anchors
    room_id: str | None = None  # for ROOM anchors
    latitude: float | None = None  # for GEOGRAPHIC anchors
    longitude: float | None = None
    altitude: float | None = None
    heading_degrees: float | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    created_at: float = Field(default_factory=time.time)
    label: str | None = None

    @property
    def transform(self) -> Transform:
        return Transform(Vector3.from_tuple(self.position), Quaternion.from_tuple(self.rotation))


class AnchorStore(Protocol):
    """Persistence contract for PERSISTENT/ROOM/GEOGRAPHIC anchors."""

    def save_anchors(self, anchors: list[Anchor]) -> None: ...

    def load_anchors(self) -> list[Anchor]: ...


class SpatialAnchorEngine:
    """
    Creates and resolves spatial anchors, and lets virtual objects "attach"
    to them so their world transform is always derived from the anchor's
    current (possibly relocalized) pose rather than a fixed coordinate.
    """

    def __init__(self, world_model: SpatialWorldModel | None = None, store: AnchorStore | None = None) -> None:
        self.world_model = world_model
        self.store = store
        self._anchors: dict[str, Anchor] = {}
        self._attachments: dict[str, str] = {}  # object_id -> anchor_id
        if store is not None:
            for anchor in store.load_anchors():
                self._anchors[anchor.id] = anchor

    # -- creation --------------------------------------------------------

    def create_local_anchor(self, position: Vector3, rotation: Quaternion | None = None, label: str | None = None) -> Anchor:
        return self._register(
            Anchor(type=AnchorType.LOCAL, position=position.as_tuple(), rotation=(rotation or Quaternion.identity()).as_tuple(), label=label)
        )

    def create_persistent_anchor(self, position: Vector3, rotation: Quaternion | None = None, label: str | None = None) -> Anchor:
        anchor = self._register(
            Anchor(
                type=AnchorType.PERSISTENT,
                position=position.as_tuple(),
                rotation=(rotation or Quaternion.identity()).as_tuple(),
                label=label,
            )
        )
        self._persist()
        return anchor

    def create_object_anchor(self, target_object_id: str, offset: Transform | None = None, label: str | None = None) -> Anchor:
        offset = offset or Transform.identity()
        anchor = self._register(
            Anchor(
                type=AnchorType.OBJECT,
                target_object_id=target_object_id,
                position=offset.position.as_tuple(),
                rotation=offset.rotation.as_tuple(),
                label=label,
            )
        )
        self._persist()
        return anchor

    def create_room_anchor(self, room_id: str, position: Vector3, rotation: Quaternion | None = None, label: str | None = None) -> Anchor:
        anchor = self._register(
            Anchor(
                type=AnchorType.ROOM,
                room_id=room_id,
                position=position.as_tuple(),
                rotation=(rotation or Quaternion.identity()).as_tuple(),
                label=label,
            )
        )
        self._persist()
        return anchor

    def create_geographic_anchor(
        self, latitude: float, longitude: float, altitude: float = 0.0, heading_degrees: float = 0.0, label: str | None = None
    ) -> Anchor:
        anchor = self._register(
            Anchor(
                type=AnchorType.GEOGRAPHIC,
                latitude=latitude,
                longitude=longitude,
                altitude=altitude,
                heading_degrees=heading_degrees,
                label=label,
            )
        )
        self._persist()
        return anchor

    def _register(self, anchor: Anchor) -> Anchor:
        self._anchors[anchor.id] = anchor
        return anchor

    def _persist(self) -> None:
        if self.store is not None:
            self.store.save_anchors(list(self._anchors.values()))

    # -- attachment / resolution -----------------------------------------

    def attach(self, object_id: str, anchor: Anchor | str) -> None:
        anchor_id = anchor.id if isinstance(anchor, Anchor) else anchor
        if anchor_id not in self._anchors:
            raise KeyError(f"unknown anchor: {anchor_id}")
        self._attachments[object_id] = anchor_id

    def detach(self, object_id: str) -> None:
        self._attachments.pop(object_id, None)

    def resolve(self, anchor_id: str) -> Transform | None:
        """Compute the anchor's current world transform.

        OBJECT anchors are resolved relative to their live target object's
        pose in the world model, so they track a moving real-world object;
        every other anchor type resolves to its stored/relocalized pose.
        """
        anchor = self._anchors.get(anchor_id)
        if anchor is None:
            return None
        if anchor.type == AnchorType.OBJECT and self.world_model is not None and anchor.target_object_id:
            target = self.world_model.get(anchor.target_object_id)
            if target is None:
                return None
            return target.transform.combine(anchor.transform)
        return anchor.transform

    def resolve_for_object(self, object_id: str) -> Transform | None:
        anchor_id = self._attachments.get(object_id)
        if anchor_id is None:
            return None
        return self.resolve(anchor_id)

    def get(self, anchor_id: str) -> Anchor | None:
        return self._anchors.get(anchor_id)

    def all(self) -> list[Anchor]:
        return list(self._anchors.values())

    def by_type(self, anchor_type: AnchorType) -> list[Anchor]:
        return [a for a in self._anchors.values() if a.type == anchor_type]

    def remove(self, anchor_id: str) -> None:
        self._anchors.pop(anchor_id, None)
        for object_id in [oid for oid, aid in self._attachments.items() if aid == anchor_id]:
            self._attachments.pop(object_id, None)
        self._persist()
