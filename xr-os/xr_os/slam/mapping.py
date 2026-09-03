"""
Spatial mapping primitives: point clouds, meshes, planes, and the
continuously-updated ``SpatialMap`` that accumulates them.

Heavy geometry processing (Poisson reconstruction, ICP, voxel hashing) is
delegated to Open3D when installed (``pip install xr-os[geometry]``); when
it isn't, ``SpatialMap`` still works with dependency-free numpy fallbacks so
the rest of XR-OS never has a hard dependency on it.
"""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from xr_os.core.math3d import Vector3
from xr_os.tracking.types import Pose


def _try_import_open3d():
    try:
        import open3d as o3d  # type: ignore

        return o3d
    except ImportError:
        return None


@dataclass
class PointCloud:
    """A set of 3D points, optionally with per-point color and normal."""

    points: np.ndarray = field(default_factory=lambda: np.zeros((0, 3), dtype=np.float64))
    colors: np.ndarray | None = None
    normals: np.ndarray | None = None

    def __len__(self) -> int:
        return int(self.points.shape[0])

    def merge(self, other: "PointCloud", voxel_size: float | None = None) -> "PointCloud":
        merged_points = np.vstack([self.points, other.points]) if len(self) or len(other) else self.points
        merged = PointCloud(points=merged_points)
        if voxel_size:
            merged = merged.voxel_downsample(voxel_size)
        return merged

    def voxel_downsample(self, voxel_size: float) -> "PointCloud":
        """Deduplicate points by snapping to a voxel grid (dependency-free fallback)."""
        if len(self) == 0 or voxel_size <= 0:
            return PointCloud(points=self.points.copy())
        o3d = _try_import_open3d()
        if o3d is not None:
            cloud = o3d.geometry.PointCloud()
            cloud.points = o3d.utility.Vector3dVector(self.points)
            down = cloud.voxel_down_sample(voxel_size)
            return PointCloud(points=np.asarray(down.points))
        keys = np.floor(self.points / voxel_size).astype(np.int64)
        _, unique_idx = np.unique(keys, axis=0, return_index=True)
        return PointCloud(points=self.points[np.sort(unique_idx)])

    def bounds(self) -> tuple[Vector3, Vector3]:
        if len(self) == 0:
            return Vector3.zero(), Vector3.zero()
        return Vector3.from_array(self.points.min(axis=0)), Vector3.from_array(self.points.max(axis=0))


@dataclass
class Mesh:
    """A reconstructed triangle mesh."""

    vertices: np.ndarray = field(default_factory=lambda: np.zeros((0, 3), dtype=np.float64))
    triangles: np.ndarray = field(default_factory=lambda: np.zeros((0, 3), dtype=np.int64))

    @property
    def vertex_count(self) -> int:
        return int(self.vertices.shape[0])

    @property
    def triangle_count(self) -> int:
        return int(self.triangles.shape[0])

    @classmethod
    def from_point_cloud(cls, cloud: PointCloud) -> "Mesh":
        """Best-effort reconstruction: Poisson surface via Open3D if available,
        otherwise a convex hull (dependency-free, good enough for coarse
        collision/visualization placeholders in simulation)."""
        if len(cloud) < 4:
            return cls()
        o3d = _try_import_open3d()
        if o3d is not None:
            pc = o3d.geometry.PointCloud()
            pc.points = o3d.utility.Vector3dVector(cloud.points)
            pc.estimate_normals()
            mesh, _ = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(pc, depth=8)
            return cls(vertices=np.asarray(mesh.vertices), triangles=np.asarray(mesh.triangles))
        try:
            from scipy.spatial import ConvexHull

            hull = ConvexHull(cloud.points)
            return cls(vertices=cloud.points[hull.vertices], triangles=np.array(hull.simplices))
        except Exception:
            return cls()


class PlaneType(str, Enum):
    FLOOR = "floor"
    CEILING = "ceiling"
    WALL = "wall"
    TABLE = "table"
    UNKNOWN = "unknown"


@dataclass
class Plane:
    """A detected planar surface: point-on-plane, unit normal, and rough bounds."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    point: Vector3 = field(default_factory=Vector3.zero)
    normal: Vector3 = field(default_factory=lambda: Vector3(0, 1, 0))
    extents: tuple[float, float] = (1.0, 1.0)
    plane_type: PlaneType = PlaneType.UNKNOWN
    confidence: float = 0.5

    def classify(self) -> PlaneType:
        """Classify by normal direction: near-vertical up/down -> floor/ceiling, else wall."""
        n = self.normal.normalized()
        if n.y > 0.85:
            self.plane_type = PlaneType.FLOOR
        elif n.y < -0.85:
            self.plane_type = PlaneType.CEILING
        else:
            self.plane_type = PlaneType.WALL
        return self.plane_type

    def distance_to_point(self, p: Vector3) -> float:
        n = self.normal.normalized()
        return abs((p - self.point).dot(n))


@dataclass
class SlamFrame:
    """The result of feeding one sensor frame through a SLAM backend."""

    pose: Pose
    new_points: PointCloud = field(default_factory=PointCloud)
    is_tracking: bool = True
    timestamp: float = field(default_factory=time.time)


class VisualSlamBackend(ABC):
    """
    Visual / visual-inertial SLAM front-end contract.

    A concrete backend (ARKit, ARCore, OpenXR, ORB-SLAM3, a proprietary VIO
    stack, or the bundled deterministic simulator in ``xr_os.simulation``)
    implements this and is otherwise invisible to the rest of XR-OS.
    """

    @abstractmethod
    def process_frame(
        self,
        image: np.ndarray | None = None,
        depth: np.ndarray | None = None,
        imu: dict | None = None,
    ) -> SlamFrame:
        """Consume one sensor frame and return the updated pose + any new geometry."""

    @abstractmethod
    def reset(self) -> None:
        """Reset tracking state (e.g. after a tracking loss / relocalization failure)."""

    @property
    @abstractmethod
    def is_tracking(self) -> bool:
        ...


class PlaneDetector(ABC):
    """Plane-detection contract, run against the accumulated point cloud."""

    @abstractmethod
    def detect(self, cloud: PointCloud) -> list[Plane]:
        ...


class NaivePlaneDetector(PlaneDetector):
    """A simple, dependency-free RANSAC plane detector for point clouds.

    Good enough for simulation and small/simple scans; a production
    deployment would swap this for a proper segmentation/RANSAC pipeline
    (Open3D's ``segment_plane`` or a learned plane detector).
    """

    def __init__(self, iterations: int = 200, distance_threshold: float = 0.02, min_inliers: int = 30) -> None:
        self.iterations = iterations
        self.distance_threshold = distance_threshold
        self.min_inliers = min_inliers

    def detect(self, cloud: PointCloud, max_planes: int = 4) -> list[Plane]:
        points = cloud.points.copy()
        planes: list[Plane] = []
        rng = np.random.default_rng(seed=0)
        # A bare plane fit can't tell floor from ceiling -- both are flat and
        # horizontal. Use the room's overall height range as the "up" prior:
        # a horizontal plane near the bottom is the floor (normal points up,
        # into the room); one near the top is the ceiling (normal points
        # down, into the room). Computed once, over the un-eroded cloud, so
        # later iterations (which delete inliers as they go) keep judging
        # against the whole room's extent.
        y_min = float(points[:, 1].min()) if len(points) else 0.0
        y_max = float(points[:, 1].max()) if len(points) else 0.0
        for _ in range(max_planes):
            if len(points) < self.min_inliers:
                break
            best_inliers: np.ndarray | None = None
            best_params = None
            for _ in range(self.iterations):
                if len(points) < 3:
                    break
                idx = rng.choice(len(points), size=3, replace=False)
                p0, p1, p2 = points[idx]
                normal = np.cross(p1 - p0, p2 - p0)
                norm = np.linalg.norm(normal)
                if norm < 1e-9:
                    continue
                normal = normal / norm
                if abs(normal[1]) > 0.7:  # near-horizontal: orient by height, not an arbitrary cross-product sign
                    near_floor = abs(p0[1] - y_min) <= abs(p0[1] - y_max)
                    desired_sign = 1.0 if near_floor else -1.0
                    if np.sign(normal[1] or 1.0) != desired_sign:
                        normal = -normal
                d = -np.dot(normal, p0)
                dist = np.abs(points @ normal + d)
                inliers = np.where(dist < self.distance_threshold)[0]
                if best_inliers is None or len(inliers) > len(best_inliers):
                    best_inliers, best_params = inliers, (p0, normal)
            if best_inliers is None or len(best_inliers) < self.min_inliers:
                break
            p0, normal = best_params
            inlier_points = points[best_inliers]
            extents = (
                float(inlier_points[:, 0].max() - inlier_points[:, 0].min()) or 0.1,
                float(inlier_points[:, 2].max() - inlier_points[:, 2].min()) or 0.1,
            )
            plane = Plane(
                point=Vector3.from_array(p0),
                normal=Vector3.from_array(normal),
                extents=extents,
                confidence=min(1.0, len(best_inliers) / max(1, len(points))),
            )
            plane.classify()
            planes.append(plane)
            points = np.delete(points, best_inliers, axis=0)
        return planes


class SpatialMap:
    """
    The continuously-updated map: accumulated point cloud, derived mesh, and
    detected planes. Fed by a ``VisualSlamBackend`` frame-by-frame.
    """

    def __init__(self, plane_detector: PlaneDetector | None = None, voxel_size: float = 0.03) -> None:
        self.cloud = PointCloud()
        self.mesh: Mesh | None = None
        self.planes: list[Plane] = []
        self.plane_detector = plane_detector or NaivePlaneDetector()
        self.voxel_size = voxel_size
        self.last_pose: Pose | None = None
        self.frame_count = 0

    def integrate_frame(self, frame: SlamFrame) -> None:
        self.last_pose = frame.pose
        self.frame_count += 1
        if len(frame.new_points):
            self.cloud = self.cloud.merge(frame.new_points, voxel_size=self.voxel_size)

    def rebuild_planes(self, max_planes: int = 4) -> list[Plane]:
        self.planes = self.plane_detector.detect(self.cloud, max_planes=max_planes)
        return self.planes

    def rebuild_mesh(self) -> Mesh:
        self.mesh = Mesh.from_point_cloud(self.cloud)
        return self.mesh

    def floor(self) -> Plane | None:
        return next((p for p in self.planes if p.plane_type == PlaneType.FLOOR), None)

    def walls(self) -> list[Plane]:
        return [p for p in self.planes if p.plane_type == PlaneType.WALL]

    def summary(self) -> dict:
        return {
            "points": len(self.cloud),
            "planes": len(self.planes),
            "frames": self.frame_count,
            "mesh_vertices": self.mesh.vertex_count if self.mesh else 0,
        }
