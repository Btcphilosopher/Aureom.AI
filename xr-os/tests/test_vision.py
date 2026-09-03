"""Computer-vision perception tests: detection, segmentation, and scene understanding."""

import numpy as np
import pytest

from xr_os.core.spatial_object import SpatialObjectType
from xr_os.vision.cv_backends import ColorBlobDetector, OtsuSegmenter
from xr_os.vision.scene_understanding import CameraIntrinsics, ScenePerceptionPipeline


def _synthetic_frame() -> np.ndarray:
    image = np.zeros((200, 200, 3), dtype=np.uint8)
    image[50:100, 50:100] = (255, 0, 0)  # red block, RGB order
    return image


def test_color_blob_detector_finds_red_block():
    detections = ColorBlobDetector().detect(_synthetic_frame())
    assert any(d.label == "red" for d in detections)
    red = next(d for d in detections if d.label == "red")
    x, y, w, h = red.bbox
    assert 45 <= x <= 55
    assert 45 <= w <= 55


def test_color_blob_detector_finds_nothing_on_blank_image():
    blank = np.zeros((100, 100, 3), dtype=np.uint8)
    assert ColorBlobDetector().detect(blank) == []


def test_otsu_segmenter_separates_bright_region():
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    image[:, 50:] = 255
    mask = OtsuSegmenter().segment(image)
    assert mask.shape == (100, 100)
    assert set(np.unique(mask)).issubset({0, 1})


def test_scene_perception_pipeline_lifts_detection_into_world_model(world_model):
    detector = ColorBlobDetector()
    intrinsics = CameraIntrinsics(fx=100, fy=100, cx=100, cy=100)
    pipeline = ScenePerceptionPipeline(detector, intrinsics, world_model=world_model)

    depth = np.ones((200, 200), dtype=np.float32) * 2.0
    objects = pipeline.process(_synthetic_frame(), depth_map=depth)

    assert len(objects) >= 1
    assert all(o.type == SpatialObjectType.OBJECT for o in objects)
    assert len(world_model.by_type(SpatialObjectType.OBJECT)) == len(objects)


def test_scene_perception_pipeline_merges_repeat_observations(world_model):
    detector = ColorBlobDetector()
    intrinsics = CameraIntrinsics(fx=100, fy=100, cx=100, cy=100)
    pipeline = ScenePerceptionPipeline(detector, intrinsics, world_model=world_model, merge_radius=1.0)

    depth = np.ones((200, 200), dtype=np.float32) * 2.0
    frame = _synthetic_frame()
    pipeline.process(frame, depth_map=depth)
    pipeline.process(frame, depth_map=depth)  # same scene again

    assert len(world_model.by_type(SpatialObjectType.OBJECT)) == 1
