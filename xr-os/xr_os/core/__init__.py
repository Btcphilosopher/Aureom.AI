"""Core spatial primitives shared across every XR-OS subsystem."""

from xr_os.core.math3d import Quaternion, Transform, Vector3
from xr_os.core.spatial_object import SpatialObject, SpatialObjectType
from xr_os.core.world_model import SpatialWorldModel, Zone

__all__ = [
    "Vector3",
    "Quaternion",
    "Transform",
    "SpatialObject",
    "SpatialObjectType",
    "SpatialWorldModel",
    "Zone",
]
