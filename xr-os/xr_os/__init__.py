"""
XR-OS: a modular Python operating layer for spatial computing.

    Physical World
        -> Sensors / Cameras / IMU
        -> Spatial Perception
        -> Spatial World Model
        -> XR Runtime
        -> Applications / Experiences
        -> Display + Audio + Haptics

XR-OS is not an XR application. It is the software layer that sits between
raw sensors and XR applications: it understands the user's position, their
environment, the objects around them, how they interact with the world, and
how virtual content should be composed into it. Applications are written
against stable, hardware-independent APIs (see ``xr_os.runtime``); anything
latency-critical (rendering, tracking fusion, frame scheduling, device
drivers) is exposed here as a swappable interface intended to eventually be
backed by Rust/C++ (see ``xr_os.tracking``, ``xr_os.slam``).
"""

from importlib import metadata as _metadata

try:
    __version__ = _metadata.version("xr-os")
except _metadata.PackageNotFoundError:  # pragma: no cover - editable/dev checkout
    __version__ = "0.1.0-dev"

__all__ = ["__version__"]
