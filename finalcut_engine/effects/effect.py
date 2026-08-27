"""The base Effect interface: parameters, masking, ordering, and cache keys.

Every concrete effect is a small ``kw_only`` dataclass so its parameters are
both keyframeable field values and automatically hashable for
:mod:`finalcut_engine.render.cache` — the render cache never needs to know
what a specific effect does, only whether its parameters changed.
"""
from __future__ import annotations

import dataclasses
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

import numpy as np

from finalcut_engine.core.timebase import Time

#: Given an (height, width) shape, returns an HxW mask in [0, 1].
MaskFn = Callable[[Tuple[int, int]], np.ndarray]


@dataclass(kw_only=True)
class Effect(ABC):
    name: str = "Effect"
    enabled: bool = True
    opacity: float = 1.0
    mask: Optional[MaskFn] = None

    @abstractmethod
    def render(self, image: np.ndarray, t: Time) -> np.ndarray:
        """Produce the fully-processed image; masking/opacity are applied by :meth:`apply`."""

    def apply(self, image: np.ndarray, t: Time) -> np.ndarray:
        if not self.enabled:
            return image
        result = self.render(image, t)
        blend = result * self.opacity + image * (1 - self.opacity)
        if self.mask is not None:
            m = self.mask(image.shape[:2])
            if m.ndim == 2:
                m = m[..., np.newaxis]
            blend = image * (1 - m) + blend * m
        return blend

    def cache_key(self, t: Time) -> tuple:
        """A hashable fingerprint of this effect's parameters at time ``t``.

        Excludes ``mask`` (an arbitrary callable) from the key; callers that
        use per-pixel masks should key on the mask separately if needed.
        """
        values = []
        for f in dataclasses.fields(self):
            if f.name == "mask":
                continue
            values.append((f.name, getattr(self, f.name)))
        return (type(self).__name__, tuple(values))
