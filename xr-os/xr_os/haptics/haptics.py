"""HapticEngine: turns physics collisions (and direct app calls) into actuator commands."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from enum import Enum

from pydantic import BaseModel, Field

from xr_os.core.events import EventBus
from xr_os.physics.engine import CollisionContact

TOPIC_HAPTIC_EVENT = "haptics.event"

# Collision impulse magnitude -> perceived intensity is nonlinear; this caps
# how hard an impulse can hit before it's clipped to "as strong as it gets".
_MAX_IMPULSE_FOR_FULL_INTENSITY = 4.0


class ActuatorTarget(str, Enum):
    LEFT_CONTROLLER = "left_controller"
    RIGHT_CONTROLLER = "right_controller"
    LEFT_HAND_GLOVE = "left_hand_glove"
    RIGHT_HAND_GLOVE = "right_hand_glove"
    WRISTBAND = "wristband"
    ULTRASOUND_ARRAY = "ultrasound_array"


class HapticEvent(BaseModel):
    """A concrete tactile-feedback instruction, the output of COLLISION -> PHYSICS."""

    target: ActuatorTarget
    intensity: float = Field(ge=0.0, le=1.0)
    frequency_hz: float = 180.0
    duration_ms: float = 60.0
    position: tuple[float, float, float] | None = None
    timestamp: float = Field(default_factory=time.time)


class Actuator(ABC):
    """A haptic output device contract: turns a ``HapticEvent`` into a physical pulse."""

    target: ActuatorTarget

    @abstractmethod
    def send(self, event: HapticEvent) -> None: ...


class LoggingActuator(Actuator):
    """A simulated actuator that just records the events it was sent (dev/testing)."""

    def __init__(self, target: ActuatorTarget) -> None:
        self.target = target
        self.history: list[HapticEvent] = []

    def send(self, event: HapticEvent) -> None:
        self.history.append(event)

    def last(self) -> HapticEvent | None:
        return self.history[-1] if self.history else None


class HapticEngine:
    """Routes haptic events -- from physics collisions or direct app triggers -- to actuators."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self.events = event_bus or EventBus()
        self._actuators: dict[ActuatorTarget, Actuator] = {}
        # which physics body id maps to which actuator target (e.g. "right_hand_body" -> RIGHT_CONTROLLER)
        self._body_targets: dict[str, ActuatorTarget] = {}

    def register_actuator(self, actuator: Actuator) -> None:
        self._actuators[actuator.target] = actuator

    def bind_body(self, body_id: str, target: ActuatorTarget) -> None:
        """Associate a physics-engine body (e.g. the hand/controller collider) with an actuator."""
        self._body_targets[body_id] = target

    def bound_body_count(self) -> int:
        return len(self._body_targets)

    def trigger(
        self, target: ActuatorTarget, intensity: float, duration_ms: float = 60.0, frequency_hz: float = 180.0
    ) -> HapticEvent:
        """Directly fire haptic feedback (e.g. a UI button press acknowledgement)."""
        event = HapticEvent(
            target=target, intensity=max(0.0, min(1.0, intensity)), duration_ms=duration_ms, frequency_hz=frequency_hz
        )
        self._dispatch(event)
        return event

    def handle_collisions(self, contacts: list[CollisionContact]) -> list[HapticEvent]:
        """COLLISION -> PHYSICS -> HAPTIC EVENT: convert physics contacts touching a bound body into feedback."""
        events: list[HapticEvent] = []
        for contact in contacts:
            for body_id in (contact.body_id, contact.other_id):
                target = self._body_targets.get(body_id)
                if target is None:
                    continue
                intensity = min(1.0, contact.impulse / _MAX_IMPULSE_FOR_FULL_INTENSITY)
                event = HapticEvent(target=target, intensity=intensity, position=contact.point.as_tuple())
                self._dispatch(event)
                events.append(event)
        return events

    def _dispatch(self, event: HapticEvent) -> None:
        actuator = self._actuators.get(event.target)
        if actuator is not None:
            actuator.send(event)
        self.events.publish(TOPIC_HAPTIC_EVENT, event)
