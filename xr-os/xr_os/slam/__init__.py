"""
SLAM / spatial mapping interfaces: visual SLAM, visual-inertial tracking,
depth mapping, point clouds, mesh reconstruction and plane detection, all
feeding one continuously-updated ``SpatialMap``.

These are hardware/algorithm-independent interfaces on purpose -- a real
deployment plugs in ARKit/ARCore/OpenXR-provided SLAM, ORB-SLAM3, or a
proprietary VIO stack behind the same ``VisualSlamBackend`` contract.
"""

from xr_os.slam.mapping import (
    Mesh,
    Plane,
    PointCloud,
    PlaneDetector,
    SlamFrame,
    SpatialMap,
    VisualSlamBackend,
)

__all__ = [
    "PointCloud",
    "Mesh",
    "Plane",
    "SlamFrame",
    "VisualSlamBackend",
    "PlaneDetector",
    "SpatialMap",
]
