"""
Computer-vision perception: object detection, segmentation, plane detection,
hand detection, pose estimation, depth estimation and scene understanding.

Every capability is a small, swappable interface (``xr_os.vision.interfaces``)
so a production deployment can drop in whatever model/SDK it needs (YOLO,
MediaPipe, a proprietary depth sensor SDK, ...) without touching the rest of
XR-OS. The bundled implementations (``xr_os.vision.cv_backends``) use
classical OpenCV -- genuinely functional, dependency-light, and good enough
for the simulator and CI -- rather than shipping a heavyweight pretrained
model nobody asked for.
"""

from xr_os.vision.cv_backends import ColorBlobDetector, OtsuSegmenter, StereoDepthEstimator
from xr_os.vision.interfaces import DepthEstimator, HandDetector, ImageSegmenter, ObjectDetector, PoseEstimator
from xr_os.vision.scene_understanding import ScenePerceptionPipeline
from xr_os.vision.types import Detection, HandLandmarks, PoseLandmarks

__all__ = [
    "Detection",
    "HandLandmarks",
    "PoseLandmarks",
    "ObjectDetector",
    "ImageSegmenter",
    "HandDetector",
    "PoseEstimator",
    "DepthEstimator",
    "ColorBlobDetector",
    "OtsuSegmenter",
    "StereoDepthEstimator",
    "ScenePerceptionPipeline",
]
