"""
Classical-OpenCV perception backends: genuinely functional, dependency-light
implementations of the ``xr_os.vision`` interfaces, good enough to drive the
simulator and CI without pulling in a pretrained model. A production
deployment swaps these for YOLO/MediaPipe/a depth-sensor SDK behind the same
interfaces.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from xr_os.vision.interfaces import DepthEstimator, ImageSegmenter, ObjectDetector
from xr_os.vision.types import Detection


@dataclass
class ColorRange:
    label: str
    lower_hsv: tuple[int, int, int]
    upper_hsv: tuple[int, int, int]


class ColorBlobDetector(ObjectDetector):
    """Detects connected blobs of configured HSV color ranges as labeled objects.

    A real deployment would swap this for a learned detector; this is a
    genuinely-working baseline useful for markers, calibration targets, and
    the simulator's synthetic camera frames.
    """

    def __init__(self, color_ranges: list[ColorRange] | None = None, min_area: int = 200) -> None:
        self.color_ranges = color_ranges or [
            ColorRange("red", (0, 120, 70), (10, 255, 255)),
            ColorRange("green", (36, 60, 60), (86, 255, 255)),
            ColorRange("blue", (94, 80, 40), (126, 255, 255)),
        ]
        self.min_area = min_area

    def detect(self, image: np.ndarray) -> list[Detection]:
        hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV) if image.ndim == 3 else None
        detections: list[Detection] = []
        if hsv is None:
            return detections
        for color in self.color_ranges:
            mask = cv2.inRange(hsv, np.array(color.lower_hsv), np.array(color.upper_hsv))
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for contour in contours:
                area = cv2.contourArea(contour)
                if area < self.min_area:
                    continue
                x, y, w, h = cv2.boundingRect(contour)
                confidence = min(1.0, area / (image.shape[0] * image.shape[1]))
                detections.append(Detection(label=color.label, confidence=max(0.3, confidence), bbox=(x, y, w, h)))
        return detections


class OtsuSegmenter(ImageSegmenter):
    """Binary foreground/background segmentation via Otsu thresholding."""

    def segment(self, image: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY) if image.ndim == 3 else image
        _, mask = cv2.threshold(gray, 0, 1, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return mask.astype(np.int32)


class StereoDepthEstimator(DepthEstimator):
    """Block-matching stereo depth from a left/right image pair."""

    def __init__(self, num_disparities: int = 64, block_size: int = 15) -> None:
        num_disparities = max(16, (num_disparities // 16) * 16)
        self._matcher = cv2.StereoBM_create(numDisparities=num_disparities, blockSize=block_size)

    def estimate(self, image: np.ndarray, image_right: np.ndarray | None = None) -> np.ndarray:
        if image_right is None:
            raise ValueError("StereoDepthEstimator requires a right image (pass as image_right=...)")
        left_gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY) if image.ndim == 3 else image
        right_gray = cv2.cvtColor(image_right, cv2.COLOR_RGB2GRAY) if image_right.ndim == 3 else image_right
        disparity = self._matcher.compute(left_gray, right_gray).astype(np.float32) / 16.0
        return disparity
