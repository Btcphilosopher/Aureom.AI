"""2D spatial transforms: position, scale, rotation, anchor point, and crop.

Implemented as a plain affine warp with inverse mapping + bilinear sampling
in NumPy — the same math a Core Animation / Metal transform pipeline
performs, just on the CPU. A native build replaces :meth:`Transform.apply`
with a GPU shader; nothing else in the motion or timeline layers changes.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass
class Transform:
    position: tuple[float, float] = (0.0, 0.0)  # translation, in pixels
    scale: tuple[float, float] = (1.0, 1.0)
    rotation_degrees: float = 0.0
    anchor: tuple[float, float] = (0.5, 0.5)  # normalised pivot, (0.5, 0.5) = centre
    crop: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)  # left, top, right, bottom, normalised

    def is_identity(self) -> bool:
        return (
            self.position == (0.0, 0.0)
            and self.scale == (1.0, 1.0)
            and self.rotation_degrees == 0.0
            and self.crop == (0.0, 0.0, 1.0, 1.0)
        )

    def _matrix(self, width: int, height: int) -> np.ndarray:
        """The 3x3 forward matrix mapping source pixel coords -> destination pixel coords."""
        ax, ay = self.anchor[0] * width, self.anchor[1] * height
        theta = math.radians(self.rotation_degrees)
        cos_t, sin_t = math.cos(theta), math.sin(theta)

        to_origin = np.array([[1, 0, -ax], [0, 1, -ay], [0, 0, 1]])
        scale_m = np.array([[self.scale[0], 0, 0], [0, self.scale[1], 0], [0, 0, 1]])
        rotate_m = np.array([[cos_t, -sin_t, 0], [sin_t, cos_t, 0], [0, 0, 1]])
        back_and_translate = np.array([[1, 0, ax + self.position[0]], [0, 1, ay + self.position[1]], [0, 0, 1]])

        return back_and_translate @ rotate_m @ scale_m @ to_origin

    def apply(self, image: np.ndarray) -> np.ndarray:
        h, w = image.shape[:2]
        forward = self._matrix(w, h)
        inverse = np.linalg.inv(forward)

        dst_y, dst_x = np.mgrid[0:h, 0:w].astype(np.float64)
        ones = np.ones_like(dst_x)
        dst_coords = np.stack([dst_x.ravel(), dst_y.ravel(), ones.ravel()])
        src_coords = inverse @ dst_coords
        src_x = src_coords[0].reshape(h, w)
        src_y = src_coords[1].reshape(h, w)

        warped = _bilinear_sample(image, src_x, src_y)
        return self._apply_crop(warped)

    def _apply_crop(self, image: np.ndarray) -> np.ndarray:
        left, top, right, bottom = self.crop
        if (left, top, right, bottom) == (0.0, 0.0, 1.0, 1.0):
            return image
        h, w = image.shape[:2]
        out = np.zeros_like(image)
        y0, y1 = int(top * h), int(bottom * h)
        x0, x1 = int(left * w), int(right * w)
        out[y0:y1, x0:x1] = image[y0:y1, x0:x1]
        return out


def _bilinear_sample(image: np.ndarray, src_x: np.ndarray, src_y: np.ndarray) -> np.ndarray:
    h, w = image.shape[:2]
    x0 = np.floor(src_x).astype(np.int64)
    y0 = np.floor(src_y).astype(np.int64)
    x1, y1 = x0 + 1, y0 + 1
    fx, fy = src_x - x0, src_y - y0

    valid = (x0 >= 0) & (x1 < w) & (y0 >= 0) & (y1 < h)
    x0c, x1c = np.clip(x0, 0, w - 1), np.clip(x1, 0, w - 1)
    y0c, y1c = np.clip(y0, 0, h - 1), np.clip(y1, 0, h - 1)

    def gather(yi, xi):
        return image[yi, xi]

    top = gather(y0c, x0c) * (1 - fx)[..., None] + gather(y0c, x1c) * fx[..., None]
    bottom = gather(y1c, x0c) * (1 - fx)[..., None] + gather(y1c, x1c) * fx[..., None]
    result = top * (1 - fy)[..., None] + bottom * fy[..., None]
    result[~valid] = 0
    return result
