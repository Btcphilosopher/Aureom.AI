"""
Scene understanding: lifts 2D detections into 3D and writes them into the
``SpatialWorldModel`` as OBJECT/PERSON spatial objects, merging repeat
observations of the same real-world thing instead of spawning duplicates
every frame.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from xr_os.core.math3d import Transform, Vector3
from xr_os.core.spatial_object import SpatialObject, SpatialObjectType
from xr_os.core.world_model import SpatialWorldModel
from xr_os.vision.interfaces import DepthEstimator, ObjectDetector
from xr_os.vision.types import Detection

_PERSON_LABELS = {"person", "people", "human"}


@dataclass
class CameraIntrinsics:
    """Pinhole camera intrinsics used to unproject a pixel + depth into camera space."""

    fx: float
    fy: float
    cx: float
    cy: float

    def unproject(self, px: float, py: float, depth: float) -> Vector3:
        x = (px - self.cx) * depth / self.fx
        y = (py - self.cy) * depth / self.fy
        return Vector3(x, y, -depth)  # camera looks down -Z


class ScenePerceptionPipeline:
    """CAMERA FRAME -> DETECTIONS -> 3D POSITIONS -> SPATIAL WORLD MODEL."""

    def __init__(
        self,
        detector: ObjectDetector,
        intrinsics: CameraIntrinsics,
        world_model: SpatialWorldModel | None = None,
        depth_estimator: DepthEstimator | None = None,
        merge_radius: float = 0.3,
    ) -> None:
        self.detector = detector
        self.intrinsics = intrinsics
        self.world_model = world_model
        self.depth_estimator = depth_estimator
        self.merge_radius = merge_radius

    def process(
        self,
        image: np.ndarray,
        depth_map: np.ndarray | None = None,
        camera_transform: Transform = Transform.identity(),
    ) -> list[SpatialObject]:
        detections = self.detector.detect(image)
        if depth_map is None and self.depth_estimator is not None:
            depth_map = self.depth_estimator.estimate(image)

        objects: list[SpatialObject] = []
        for detection in detections:
            depth = self._sample_depth(detection, depth_map)
            if depth is None:
                continue
            x, y, w, h = detection.bbox
            center_px, center_py = x + w / 2.0, y + h / 2.0
            camera_space = self.intrinsics.unproject(center_px, center_py, depth)
            world_position = camera_transform.transform_point(camera_space)
            objects.append(self._upsert(detection, world_position))
        return objects

    def _sample_depth(self, detection: Detection, depth_map: np.ndarray | None) -> float | None:
        if depth_map is None:
            return None
        x, y, w, h = detection.bbox
        cx, cy = int(x + w / 2), int(y + h / 2)
        cy = max(0, min(depth_map.shape[0] - 1, cy))
        cx = max(0, min(depth_map.shape[1] - 1, cx))
        depth = float(depth_map[cy, cx])
        return depth if depth > 1e-6 else None

    def _upsert(self, detection: Detection, position: Vector3) -> SpatialObject:
        obj_type = SpatialObjectType.PERSON if detection.label.lower() in _PERSON_LABELS else SpatialObjectType.OBJECT
        if self.world_model is not None:
            existing = self._find_match(detection.label, position)
            if existing is not None:
                existing.position = position.as_tuple()
                existing.touch(confidence=detection.confidence)
                return existing
        obj = SpatialObject(type=obj_type, label=detection.label, position=position.as_tuple(), confidence=detection.confidence)
        if self.world_model is not None:
            self.world_model.add(obj)
        return obj

    def _find_match(self, label: str, position: Vector3) -> SpatialObject | None:
        candidates = self.world_model.query(lambda o: o.label == label and o.type in (SpatialObjectType.OBJECT, SpatialObjectType.PERSON))
        for obj in candidates:
            if obj.transform.position.distance_to(position) <= self.merge_radius:
                return obj
        return None
