"""
The universal spatial object: every entity XR-OS knows about -- physical or
virtual, tracked or reconstructed -- is represented the same way. Higher
layers (scene graph, spatial memory, multi-user sync) all build on this one
shape instead of inventing their own per-subsystem record types.
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from xr_os.core.math3d import Quaternion, Transform, Vector3


class SpatialObjectType(str, Enum):
    """Every kind of thing the spatial world model can hold."""

    # Hardware / self
    HEADSET = "headset"
    USER = "user"
    HAND = "hand"
    CONTROLLER = "controller"
    CAMERA = "camera"

    # Physical environment (from SLAM / scene understanding)
    WALL = "wall"
    FLOOR = "floor"
    CEILING = "ceiling"
    DOOR = "door"
    WINDOW = "window"
    TABLE = "table"
    CHAIR = "chair"
    OBJECT = "object"
    PERSON = "person"

    # Virtual content
    VIRTUAL_OBJECT = "virtual_object"
    PANEL = "panel"
    MODEL = "model"
    AVATAR = "avatar"
    UI = "ui"

    # Organizational
    ZONE = "zone"
    ANCHOR = "anchor"
    ROOM = "room"


def _now() -> float:
    return time.time()


def _new_id() -> str:
    return uuid.uuid4().hex


class SpatialObject(BaseModel):
    """
    A single tracked or reconstructed entity in the spatial world model.

    ``confidence`` is in [0, 1] and represents how much the producing
    subsystem (SLAM, hand tracking, CV detector, ...) trusts this pose right
    now; consumers should degrade gracefully as confidence drops rather than
    assume every object is ground truth.
    """

    id: str = Field(default_factory=_new_id)
    type: SpatialObjectType
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)  # quaternion xyzw
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    timestamp: float = Field(default_factory=_now)
    label: str | None = None
    parent_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": False}

    # -- convenience accessors bridging to xr_os.core.math3d -------------

    @property
    def transform(self) -> Transform:
        return Transform(
            position=Vector3.from_tuple(self.position),
            rotation=Quaternion.from_tuple(self.rotation),
            scale=Vector3.from_tuple(self.scale),
        )

    def set_transform(self, transform: Transform) -> None:
        self.position = transform.position.as_tuple()
        self.rotation = transform.rotation.as_tuple()
        self.scale = transform.scale.as_tuple()
        self.touch()

    def touch(self, confidence: float | None = None) -> None:
        """Mark this object as freshly observed/updated."""
        self.timestamp = _now()
        if confidence is not None:
            self.confidence = max(0.0, min(1.0, confidence))

    def age_seconds(self) -> float:
        return max(0.0, _now() - self.timestamp)

    def distance_to(self, other: "SpatialObject") -> float:
        return self.transform.position.distance_to(other.transform.position)

    def is_stale(self, max_age_seconds: float) -> bool:
        return self.age_seconds() > max_age_seconds
