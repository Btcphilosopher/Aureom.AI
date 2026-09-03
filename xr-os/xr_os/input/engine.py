"""InputEngine: polls every registered device, resolves a target scene node, and dispatches."""

from __future__ import annotations

from dataclasses import dataclass

from xr_os.core.events import EventBus
from xr_os.core.math3d import Vector3
from xr_os.input.devices import InputDevice
from xr_os.input.events import InputEvent, InputEventType

TOPIC_INPUT_EVENT = "input.event"

# Event types that carry a ray (position + direction) and should be resolved via raycast.
_RAY_EVENTS = {InputEventType.POINT, InputEventType.LOOK}
# Event types that carry just a position and should be resolved via proximity.
_PROXIMITY_EVENTS = {InputEventType.GRAB, InputEventType.PINCH, InputEventType.CLICK, InputEventType.TOUCH}


@dataclass
class InputRouteResult:
    event: InputEvent
    target_node_id: str | None


class InputEngine:
    """Device-agnostic input hub: applications subscribe to ``TOPIC_INPUT_EVENT`` or read node interactions."""

    def __init__(self, scene_graph=None, event_bus: EventBus | None = None) -> None:
        self.scene_graph = scene_graph
        self.events = event_bus or EventBus()
        self._devices: dict[str, InputDevice] = {}
        self.total_events = 0

    def register(self, device: InputDevice) -> InputDevice:
        self._devices[device.name] = device
        return device

    def unregister(self, name: str) -> None:
        self._devices.pop(name, None)

    def devices(self) -> list[InputDevice]:
        return list(self._devices.values())

    def update(self) -> list[InputRouteResult]:
        """Poll every device once, resolve targets, dispatch, and return the routed events."""
        results: list[InputRouteResult] = []
        for device in self._devices.values():
            for event in device.poll():
                target_id = self._resolve_target(event)
                event.target_node_id = target_id
                if target_id and self.scene_graph is not None:
                    node = self.scene_graph.find(target_id)
                    if node is not None:
                        node.interact(event.type.value, event.model_dump())
                self.events.publish(TOPIC_INPUT_EVENT, event)
                results.append(InputRouteResult(event=event, target_node_id=target_id))
                self.total_events += 1
        return results

    def _resolve_target(self, event: InputEvent) -> str | None:
        if self.scene_graph is None:
            return None
        if event.type in _RAY_EVENTS and event.position is not None and event.direction is not None:
            hit = self.scene_graph.raycast(Vector3.from_tuple(event.position), Vector3.from_tuple(event.direction))
            return hit.node.id if hit else None
        if event.type in _PROXIMITY_EVENTS and event.position is not None:
            point = Vector3.from_tuple(event.position)
            best_id, best_dist = None, float("inf")
            for node in self.scene_graph.interactable_nodes():
                dist = node.world_position.distance_to(point)
                if dist <= node.bounding_radius and dist < best_dist:
                    best_id, best_dist = node.id, dist
            return best_id
        return None
