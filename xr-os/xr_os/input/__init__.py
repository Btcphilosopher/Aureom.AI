"""
The Input Engine: unifies controllers, hand gestures, eye gaze, voice,
keyboard, mouse, touch and haptic devices behind one device-agnostic event
system (POINT, GRAB, PINCH, CLICK, LOOK, MOVE, ROTATE, SPEAK, TOUCH).
Applications consume ``InputEvent``s and never need to know which physical
device produced them.
"""

from xr_os.input.devices import (
    ControllerDevice,
    GazeDevice,
    HandDevice,
    InputDevice,
    KeyboardDevice,
    MouseDevice,
    TouchDevice,
    VoiceDevice,
)
from xr_os.input.engine import InputEngine, InputRouteResult
from xr_os.input.events import InputEvent, InputEventType

__all__ = [
    "InputEventType",
    "InputEvent",
    "InputEngine",
    "InputRouteResult",
    "InputDevice",
    "ControllerDevice",
    "HandDevice",
    "GazeDevice",
    "VoiceDevice",
    "KeyboardDevice",
    "MouseDevice",
    "TouchDevice",
]
