"""
Haptic integration: the HapticOS-style pipeline wired into XR-OS.

    COLLISION -> PHYSICS -> HAPTIC EVENT -> ACTUATOR
"""

from xr_os.haptics.haptics import ActuatorTarget, Actuator, HapticEngine, HapticEvent, LoggingActuator

__all__ = ["HapticEvent", "ActuatorTarget", "Actuator", "LoggingActuator", "HapticEngine"]
