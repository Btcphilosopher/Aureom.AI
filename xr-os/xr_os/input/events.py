"""The unified input event vocabulary every XR-OS input device maps onto."""

from __future__ import annotations

import time
from enum import Enum

from pydantic import BaseModel, Field


class InputEventType(str, Enum):
    POINT = "point"
    GRAB = "grab"
    PINCH = "pinch"
    CLICK = "click"
    LOOK = "look"
    MOVE = "move"
    ROTATE = "rotate"
    SPEAK = "speak"
    TOUCH = "touch"


class InputEvent(BaseModel):
    """One device-agnostic input occurrence."""

    type: InputEventType
    device: str  # e.g. "right_controller", "left_hand", "gaze", "voice", "keyboard"
    position: tuple[float, float, float] | None = None
    direction: tuple[float, float, float] | None = None
    rotation_delta: tuple[float, float, float, float] | None = None
    value: float | None = None  # e.g. pinch strength, trigger pull, touch pressure
    text: str | None = None  # e.g. recognized speech, key pressed
    target_node_id: str | None = None  # resolved by the engine once raycast against the scene graph
    timestamp: float = Field(default_factory=time.time)
