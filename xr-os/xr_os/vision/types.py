"""Result types shared by every vision component."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Detection(BaseModel):
    """A 2D detection in image space, optionally lifted to 3D once depth is known."""

    label: str
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: tuple[int, int, int, int]  # x, y, width, height, in pixels
    position_3d: tuple[float, float, float] | None = None


class HandLandmarks(BaseModel):
    """Per-joint 2D (or, once lifted, 3D) hand keypoints, MediaPipe-style 21-point layout."""

    handedness: str  # "left" | "right"
    points: list[tuple[float, float]]  # normalized image coordinates
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class PoseLandmarks(BaseModel):
    """Per-joint body keypoints."""

    joint_names: list[str]
    points: list[tuple[float, float]]
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
