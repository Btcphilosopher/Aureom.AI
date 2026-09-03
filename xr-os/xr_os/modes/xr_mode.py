"""AR / VR / MR mode management."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel

from xr_os.core.events import EventBus

TOPIC_MODE_CHANGED = "modes.changed"


class XRMode(str, Enum):
    AR = "ar"  # virtual content overlaid onto the physical world
    VR = "vr"  # fully virtual environment
    MR = "mr"  # virtual content interacts with reconstructed physical geometry


@dataclass(frozen=True)
class ModeCapabilities:
    """What a mode implies for rendering and physics, independent of any one app."""

    passthrough_enabled: bool
    physical_geometry_visible: bool
    physical_geometry_collidable: bool
    virtual_world_visible: bool


_CAPABILITIES: dict[XRMode, ModeCapabilities] = {
    XRMode.AR: ModeCapabilities(
        passthrough_enabled=True, physical_geometry_visible=True, physical_geometry_collidable=False, virtual_world_visible=True
    ),
    XRMode.VR: ModeCapabilities(
        passthrough_enabled=False, physical_geometry_visible=False, physical_geometry_collidable=False, virtual_world_visible=True
    ),
    XRMode.MR: ModeCapabilities(
        passthrough_enabled=True, physical_geometry_visible=True, physical_geometry_collidable=True, virtual_world_visible=True
    ),
}


class ModeChangeEvent(BaseModel):
    previous: XRMode
    current: XRMode


class XRModeManager:
    """Tracks the active XR mode and lets applications switch it at runtime."""

    def __init__(self, initial_mode: XRMode = XRMode.MR, event_bus: EventBus | None = None) -> None:
        self._mode = initial_mode
        self.events = event_bus or EventBus()

    @property
    def mode(self) -> XRMode:
        return self._mode

    @property
    def capabilities(self) -> ModeCapabilities:
        return _CAPABILITIES[self._mode]

    def set_mode(self, mode: XRMode) -> ModeChangeEvent:
        previous = self._mode
        self._mode = mode
        event = ModeChangeEvent(previous=previous, current=mode)
        if previous != mode:
            self.events.publish(TOPIC_MODE_CHANGED, event)
        return event

    @staticmethod
    def capabilities_for(mode: XRMode) -> ModeCapabilities:
        return _CAPABILITIES[mode]
