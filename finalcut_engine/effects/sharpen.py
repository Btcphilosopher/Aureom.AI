"""Unsharp-mask sharpening, built on the same Gaussian kernel as blur.py."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from finalcut_engine.core.timebase import Time
from finalcut_engine.effects.blur import gaussian_kernel1d, separable_convolve
from finalcut_engine.effects.effect import Effect


@dataclass(kw_only=True)
class SharpenEffect(Effect):
    name: str = "Sharpen"
    radius: float = 2.0
    amount: float = 0.6  # 0 = no effect, 1 = full-strength unsharp mask

    def render(self, image: np.ndarray, t: Time) -> np.ndarray:
        kernel = gaussian_kernel1d(self.radius)
        blurred = separable_convolve(image, kernel)
        high_freq = image.astype(np.float64) - blurred
        sharpened = image.astype(np.float64) + self.amount * high_freq
        max_val = 255.0 if image.dtype == np.uint8 else 1.0
        return np.clip(sharpened, 0.0, max_val)
