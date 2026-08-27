"""Blend modes and alpha compositing."""
from __future__ import annotations

from enum import Enum
from typing import Optional

import numpy as np


class BlendMode(str, Enum):
    NORMAL = "normal"
    ADD = "add"
    MULTIPLY = "multiply"
    SCREEN = "screen"
    OVERLAY = "overlay"
    DARKEN = "darken"
    LIGHTEN = "lighten"
    SUBTRACT = "subtract"
    DIFFERENCE = "difference"


def _blend(base: np.ndarray, blend: np.ndarray, mode: BlendMode) -> np.ndarray:
    b, l = base.astype(np.float64), blend.astype(np.float64)
    if mode == BlendMode.NORMAL:
        return l
    if mode == BlendMode.ADD:
        return b + l
    if mode == BlendMode.MULTIPLY:
        return b * l
    if mode == BlendMode.SCREEN:
        return 1 - (1 - b) * (1 - l)
    if mode == BlendMode.OVERLAY:
        return np.where(b <= 0.5, 2 * b * l, 1 - 2 * (1 - b) * (1 - l))
    if mode == BlendMode.DARKEN:
        return np.minimum(b, l)
    if mode == BlendMode.LIGHTEN:
        return np.maximum(b, l)
    if mode == BlendMode.SUBTRACT:
        return b - l
    if mode == BlendMode.DIFFERENCE:
        return np.abs(b - l)
    raise ValueError(f"unknown blend mode {mode}")


def composite(
    base: np.ndarray,
    overlay: np.ndarray,
    mode: BlendMode = BlendMode.NORMAL,
    opacity: float = 1.0,
    mask: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Composite ``overlay`` onto ``base``. Both are float images in [0, 1]."""
    blended = np.clip(_blend(base, overlay, mode), 0.0, 1.0)
    alpha = opacity
    if mask is not None:
        m = mask[..., np.newaxis] if mask.ndim == 2 else mask
        alpha = alpha * m
    return base * (1 - alpha) + blended * alpha


def apply_opacity(image: np.ndarray, background: np.ndarray, opacity: float) -> np.ndarray:
    return composite(background, image, BlendMode.NORMAL, opacity)
