"""Exposure, contrast, highlights/shadows, saturation, and white balance.

These are the "BALANCE" and "EXPOSURE" stages of the colour pipeline (spec
section 10). Temperature/tint here is a simplified linear RGB-gain
approximation of a Kelvin shift — a native build would convert Kelvin to a
CIE xy chromaticity and apply a proper von Kries chromatic-adaptation matrix;
that is intentionally out of scope for this prototype.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

REC709_LUMA_WEIGHTS = np.array([0.2126, 0.7152, 0.0722])


def luma(image: np.ndarray) -> np.ndarray:
    return image.astype(np.float64) @ REC709_LUMA_WEIGHTS


def apply_exposure(image: np.ndarray, stops: float) -> np.ndarray:
    return np.clip(image.astype(np.float64) * (2.0**stops), 0.0, None)


def apply_contrast(image: np.ndarray, contrast: float, pivot: float = 0.5) -> np.ndarray:
    return (image.astype(np.float64) - pivot) * contrast + pivot


def apply_saturation(image: np.ndarray, saturation: float) -> np.ndarray:
    y = luma(image)[..., np.newaxis]
    return y + (image.astype(np.float64) - y) * saturation


def _smoothstep(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def apply_highlights_shadows(image: np.ndarray, highlights: float, shadows: float) -> np.ndarray:
    """``highlights``/``shadows`` in roughly [-1, 1]; positive brightens, negative recovers/darkens."""
    y = luma(image)
    shadow_mask = 1.0 - _smoothstep(0.0, 0.5, y)
    highlight_mask = _smoothstep(0.5, 1.0, y)
    out = image.astype(np.float64)
    out = out + shadows * shadow_mask[..., np.newaxis] * 0.5
    out = out + highlights * highlight_mask[..., np.newaxis] * 0.5
    return out


def apply_temperature_tint(image: np.ndarray, temperature: float, tint: float) -> np.ndarray:
    """``temperature``/``tint`` in [-1, 1]: +temperature warms (more red/less blue)."""
    r_gain = 1.0 + temperature * 0.3
    b_gain = 1.0 - temperature * 0.3
    g_gain = 1.0 - tint * 0.2
    r_gain -= tint * 0.1
    b_gain -= tint * 0.1
    gains = np.array([r_gain, g_gain, b_gain])
    return image.astype(np.float64) * gains


@dataclass
class ExposureParams:
    exposure_stops: float = 0.0
    contrast: float = 1.0
    highlights: float = 0.0
    shadows: float = 0.0
    saturation: float = 1.0
    temperature: float = 0.0
    tint: float = 0.0

    def apply(self, image: np.ndarray) -> np.ndarray:
        out = apply_temperature_tint(image, self.temperature, self.tint)
        out = apply_exposure(out, self.exposure_stops)
        out = apply_contrast(out, self.contrast)
        out = apply_highlights_shadows(out, self.highlights, self.shadows)
        out = apply_saturation(out, self.saturation)
        return np.clip(out, 0.0, 1.0)
