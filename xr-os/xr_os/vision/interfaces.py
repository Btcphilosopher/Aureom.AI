"""Replaceable perception interfaces: swap in a real model without touching the rest of XR-OS."""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from xr_os.vision.types import Detection, HandLandmarks, PoseLandmarks


class ObjectDetector(ABC):
    @abstractmethod
    def detect(self, image: np.ndarray) -> list[Detection]: ...


class ImageSegmenter(ABC):
    @abstractmethod
    def segment(self, image: np.ndarray) -> np.ndarray:
        """Return a same-height/width integer label mask."""


class HandDetector(ABC):
    @abstractmethod
    def detect(self, image: np.ndarray) -> list[HandLandmarks]: ...


class PoseEstimator(ABC):
    @abstractmethod
    def estimate(self, image: np.ndarray) -> PoseLandmarks | None: ...


class DepthEstimator(ABC):
    @abstractmethod
    def estimate(self, image: np.ndarray, image_right: np.ndarray | None = None) -> np.ndarray:
        """Return a same-height/width float32 depth (or disparity) map."""
