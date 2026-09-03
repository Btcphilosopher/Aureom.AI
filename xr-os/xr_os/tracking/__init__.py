"""
The Tracking Engine: fuses camera, IMU, depth and controller data into one
unified spatial state (head, hands, controllers, eyes, body) and writes it
back into the ``SpatialWorldModel``.
"""

from xr_os.tracking.engine import TrackingEngine
from xr_os.tracking.types import (
    ControllerSample,
    DepthSample,
    HandSample,
    ImuSample,
    Pose,
    TrackedTarget,
    TrackingQuality,
    TrackingSource,
    VisionSample,
)

__all__ = [
    "TrackingEngine",
    "Pose",
    "TrackingQuality",
    "TrackingSource",
    "TrackedTarget",
    "ImuSample",
    "VisionSample",
    "DepthSample",
    "ControllerSample",
    "HandSample",
]
