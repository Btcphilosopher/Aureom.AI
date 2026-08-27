"""Separable Gaussian blur."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from finalcut_engine.core.timebase import Time
from finalcut_engine.effects.effect import Effect


def gaussian_kernel1d(sigma: float, radius: int | None = None) -> np.ndarray:
    if sigma <= 0:
        return np.array([1.0])
    if radius is None:
        radius = max(1, int(3 * sigma))
    x = np.arange(-radius, radius + 1, dtype=np.float64)
    kernel = np.exp(-(x**2) / (2 * sigma**2))
    return kernel / kernel.sum()


def separable_convolve(image: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """Apply a 1D kernel along both spatial axes of an HxWx(C) image."""
    out = image.astype(np.float64)
    channels = [out[..., c] for c in range(out.shape[2])] if out.ndim == 3 else [out]
    result_channels = []
    for ch in channels:
        rows = np.apply_along_axis(lambda m: np.convolve(m, kernel, mode="same"), axis=1, arr=ch)
        cols = np.apply_along_axis(lambda m: np.convolve(m, kernel, mode="same"), axis=0, arr=rows)
        result_channels.append(cols)
    return np.stack(result_channels, axis=-1) if image.ndim == 3 else result_channels[0]


@dataclass(kw_only=True)
class GaussianBlurEffect(Effect):
    name: str = "Gaussian Blur"
    radius: float = 3.0

    def render(self, image: np.ndarray, t: Time) -> np.ndarray:
        kernel = gaussian_kernel1d(self.radius)
        return np.clip(separable_convolve(image, kernel), 0.0, 1.0 if image.dtype != np.uint8 else 255.0)
