"""XR modes: AR, VR and MR, and the manager that lets apps switch between them at runtime."""

from xr_os.modes.xr_mode import ModeChangeEvent, XRMode, XRModeManager

__all__ = ["XRMode", "XRModeManager", "ModeChangeEvent"]
