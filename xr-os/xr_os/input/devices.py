"""
Device adapters. Each wraps whatever hardware/SDK produces raw samples and
exposes the same ``poll() -> list[InputEvent]`` contract to the
``InputEngine``, so applications never see device-specific data.

Every adapter here is a queue-based ``InputDevice`` that real hardware
bindings (OpenXR, ARKit, a custom controller SDK, an OS speech-recognition
API, ...) push recognized events into; convenience ``emit_*`` helpers are
provided so the simulator (and tests) can drive them without hardware.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque

from xr_os.input.events import InputEvent, InputEventType


class InputDevice(ABC):
    """Base contract for anything that can produce ``InputEvent``s."""

    device_kind: str = "generic"

    def __init__(self, name: str | None = None) -> None:
        self.name = name or self.device_kind

    @abstractmethod
    def poll(self) -> list[InputEvent]:
        """Drain and return all events produced since the last poll."""


class QueuedInputDevice(InputDevice):
    """A device whose events are pushed into a FIFO queue and drained on poll."""

    def __init__(self, name: str | None = None) -> None:
        super().__init__(name)
        self._queue: deque[InputEvent] = deque()

    def push(self, event: InputEvent) -> None:
        self._queue.append(event)

    def poll(self) -> list[InputEvent]:
        events = list(self._queue)
        self._queue.clear()
        return events


class ControllerDevice(QueuedInputDevice):
    device_kind = "controller"

    def emit_grab(self, position: tuple[float, float, float], value: float = 1.0) -> None:
        self.push(InputEvent(type=InputEventType.GRAB, device=self.name, position=position, value=value))

    def emit_point(self, position: tuple[float, float, float], direction: tuple[float, float, float]) -> None:
        self.push(InputEvent(type=InputEventType.POINT, device=self.name, position=position, direction=direction))

    def emit_click(self, position: tuple[float, float, float]) -> None:
        self.push(InputEvent(type=InputEventType.CLICK, device=self.name, position=position))

    def emit_move(self, position: tuple[float, float, float]) -> None:
        self.push(InputEvent(type=InputEventType.MOVE, device=self.name, position=position))

    def emit_rotate(self, rotation_delta: tuple[float, float, float, float]) -> None:
        self.push(InputEvent(type=InputEventType.ROTATE, device=self.name, rotation_delta=rotation_delta))


class HandDevice(QueuedInputDevice):
    device_kind = "hand"

    def emit_pinch(self, position: tuple[float, float, float], strength: float) -> None:
        self.push(InputEvent(type=InputEventType.PINCH, device=self.name, position=position, value=strength))

    def emit_grab(self, position: tuple[float, float, float]) -> None:
        self.push(InputEvent(type=InputEventType.GRAB, device=self.name, position=position))

    def emit_point(self, position: tuple[float, float, float], direction: tuple[float, float, float]) -> None:
        self.push(InputEvent(type=InputEventType.POINT, device=self.name, position=position, direction=direction))

    def emit_touch(self, position: tuple[float, float, float]) -> None:
        self.push(InputEvent(type=InputEventType.TOUCH, device=self.name, position=position))


class GazeDevice(QueuedInputDevice):
    device_kind = "gaze"

    def emit_look(self, origin: tuple[float, float, float], direction: tuple[float, float, float]) -> None:
        self.push(InputEvent(type=InputEventType.LOOK, device=self.name, position=origin, direction=direction))


class VoiceDevice(QueuedInputDevice):
    device_kind = "voice"

    def emit_speak(self, transcript: str, confidence: float = 1.0) -> None:
        self.push(InputEvent(type=InputEventType.SPEAK, device=self.name, text=transcript, value=confidence))


class KeyboardDevice(QueuedInputDevice):
    device_kind = "keyboard"

    def emit_key(self, key: str) -> None:
        self.push(InputEvent(type=InputEventType.CLICK, device=self.name, text=key))


class MouseDevice(QueuedInputDevice):
    device_kind = "mouse"

    def emit_click(self, position: tuple[float, float, float]) -> None:
        self.push(InputEvent(type=InputEventType.CLICK, device=self.name, position=position))

    def emit_move(self, position: tuple[float, float, float]) -> None:
        self.push(InputEvent(type=InputEventType.MOVE, device=self.name, position=position))


class TouchDevice(QueuedInputDevice):
    device_kind = "touch"

    def emit_touch(self, position: tuple[float, float, float], pressure: float = 1.0) -> None:
        self.push(InputEvent(type=InputEventType.TOUCH, device=self.name, position=position, value=pressure))
