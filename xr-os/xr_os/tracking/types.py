"""Data types shared by the tracking engine and its sensor sources."""

from __future__ import annotations

import time
from enum import Enum

from pydantic import BaseModel, Field

from xr_os.core.math3d import Quaternion, Transform, Vector3


class TrackingQuality(str, Enum):
    """Coarse confidence bucket a dashboard or app can react to directly."""

    LOST = "lost"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @classmethod
    def from_confidence(cls, confidence: float) -> "TrackingQuality":
        if confidence <= 0.05:
            return cls.LOST
        if confidence < 0.4:
            return cls.LOW
        if confidence < 0.8:
            return cls.MEDIUM
        return cls.HIGH


class TrackingSource(str, Enum):
    """Which sensor modality produced a given sample, for fusion weighting."""

    IMU = "imu"
    VISUAL = "visual"
    DEPTH = "depth"
    CONTROLLER = "controller"
    HAND = "hand"
    EYE = "eye"
    BODY = "body"


class TrackedTarget(str, Enum):
    """What a unified pose refers to."""

    HEAD = "head"
    LEFT_HAND = "left_hand"
    RIGHT_HAND = "right_hand"
    LEFT_CONTROLLER = "left_controller"
    RIGHT_CONTROLLER = "right_controller"
    GAZE = "gaze"
    BODY_ROOT = "body_root"


class Pose(BaseModel):
    """A single fused 6DoF pose plus velocity, quality and provenance."""

    target: TrackedTarget
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    linear_velocity: tuple[float, float, float] = (0.0, 0.0, 0.0)
    angular_velocity: tuple[float, float, float] = (0.0, 0.0, 0.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    sources: list[TrackingSource] = Field(default_factory=list)
    timestamp: float = Field(default_factory=time.time)

    @property
    def quality(self) -> TrackingQuality:
        return TrackingQuality.from_confidence(self.confidence)

    @property
    def transform(self) -> Transform:
        return Transform(Vector3.from_tuple(self.position), Quaternion.from_tuple(self.rotation))


class ImuSample(BaseModel):
    """Raw or lightly-filtered inertial measurement."""

    orientation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    angular_velocity: tuple[float, float, float] = (0.0, 0.0, 0.0)
    linear_acceleration: tuple[float, float, float] = (0.0, 0.0, 0.0)
    timestamp: float = Field(default_factory=time.time)


class VisionSample(BaseModel):
    """A visual (SLAM/VIO front-end) pose estimate for a tracked target."""

    target: TrackedTarget
    position: tuple[float, float, float]
    rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    timestamp: float = Field(default_factory=time.time)


class DepthSample(BaseModel):
    """A depth-derived refinement, typically position-only, high confidence at short range."""

    target: TrackedTarget
    position: tuple[float, float, float]
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    timestamp: float = Field(default_factory=time.time)


class ControllerSample(BaseModel):
    """Pose + input state reported directly by a tracked controller."""

    target: TrackedTarget
    position: tuple[float, float, float]
    rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    is_tracking: bool = True
    battery: float | None = None
    timestamp: float = Field(default_factory=time.time)


class HandJoint(BaseModel):
    name: str
    position: tuple[float, float, float]
    rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)


class HandSample(BaseModel):
    """A hand-tracking frame: wrist pose plus per-joint skeleton."""

    target: TrackedTarget
    wrist_position: tuple[float, float, float]
    wrist_rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    joints: list[HandJoint] = Field(default_factory=list)
    pinch_strength: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    timestamp: float = Field(default_factory=time.time)
