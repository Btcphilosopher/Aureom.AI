"""General-purpose filters (vignette, noise, distortion, crop) and the ordered
filter stack that applies a clip's whole effects list in sequence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import numpy as np

from finalcut_engine.core.timebase import Time
from finalcut_engine.effects.effect import Effect


def _normalized_grid(shape: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    h, w = shape
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float64)
    return (ys / h - 0.5) * 2, (xs / w - 0.5) * 2  # both in roughly [-1, 1]


@dataclass(kw_only=True)
class VignetteEffect(Effect):
    name: str = "Vignette"
    strength: float = 0.5  # 0 = none, 1 = strong
    radius: float = 0.75  # where the falloff begins, in normalised radius

    def render(self, image: np.ndarray, t: Time) -> np.ndarray:
        ny, nx = _normalized_grid(image.shape[:2])
        r = np.sqrt(nx**2 + ny**2)
        falloff = np.clip((r - self.radius) / max(1e-6, (1.5 - self.radius)), 0.0, 1.0)
        mask = 1.0 - falloff * self.strength
        max_val = 255.0 if image.dtype == np.uint8 else 1.0
        return np.clip(image.astype(np.float64) * mask[..., np.newaxis], 0.0, max_val)


@dataclass(kw_only=True)
class NoiseEffect(Effect):
    name: str = "Noise"
    amount: float = 0.05  # standard deviation, in the image's own units (e.g. 0-1 float)
    seed: int = 0

    def render(self, image: np.ndarray, t: Time) -> np.ndarray:
        rng = np.random.default_rng(self.seed)
        max_val = 255.0 if image.dtype == np.uint8 else 1.0
        noise = rng.normal(0.0, self.amount * max_val, size=image.shape)
        return np.clip(image.astype(np.float64) + noise, 0.0, max_val)


@dataclass(kw_only=True)
class DistortionEffect(Effect):
    """Simple radial (barrel/pincushion) lens distortion via coordinate remap."""

    name: str = "Distortion"
    amount: float = 0.1  # positive = barrel, negative = pincushion

    def render(self, image: np.ndarray, t: Time) -> np.ndarray:
        h, w = image.shape[:2]
        ny, nx = _normalized_grid((h, w))
        r2 = nx**2 + ny**2
        factor = 1.0 + self.amount * r2
        src_x = ((nx * factor) / 2 + 0.5) * w
        src_y = ((ny * factor) / 2 + 0.5) * h
        src_x = np.clip(src_x, 0, w - 1).astype(np.int64)
        src_y = np.clip(src_y, 0, h - 1).astype(np.int64)
        return image[src_y, src_x]


@dataclass(kw_only=True)
class CropEffect(Effect):
    """Zeroes out image content outside ``[left, right] x [top, bottom]`` (normalised 0..1).

    Repositioning/scaling the remaining region is a job for
    ``motion.transforms``; this filter only masks geometry.
    """

    name: str = "Crop"
    left: float = 0.0
    right: float = 1.0
    top: float = 0.0
    bottom: float = 1.0

    def render(self, image: np.ndarray, t: Time) -> np.ndarray:
        h, w = image.shape[:2]
        out = np.zeros_like(image)
        y0, y1 = int(self.top * h), int(self.bottom * h)
        x0, x1 = int(self.left * w), int(self.right * w)
        out[y0:y1, x0:x1] = image[y0:y1, x0:x1]
        return out


@dataclass
class FilterStack:
    """An ordered, stackable list of effects applied to one clip."""

    effects: List[Effect] = field(default_factory=list)

    def add(self, effect: Effect, index: int | None = None) -> Effect:
        if index is None:
            self.effects.append(effect)
        else:
            self.effects.insert(index, effect)
        return effect

    def remove(self, effect: Effect) -> None:
        self.effects.remove(effect)

    def reorder(self, from_index: int, to_index: int) -> None:
        effect = self.effects.pop(from_index)
        self.effects.insert(to_index, effect)

    def apply(self, image: np.ndarray, t: Time) -> np.ndarray:
        out = image
        for effect in self.effects:
            out = effect.apply(out, t)
        return out

    def cache_key(self, t: Time) -> tuple:
        return tuple(e.cache_key(t) for e in self.effects if e.enabled)
