"""The Colour Board: one bundle of primary-grade controls (spec section 10)."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from finalcut_engine.colour.colour_wheels import ColourWheel
from finalcut_engine.colour.curves import RGBCurves
from finalcut_engine.colour.exposure import ExposureParams


@dataclass
class ColourBoard:
    exposure: ExposureParams = field(default_factory=ExposureParams)
    wheels: ColourWheel = field(default_factory=ColourWheel)
    curves: RGBCurves = field(default_factory=RGBCurves)

    def apply(self, image: np.ndarray) -> np.ndarray:
        out = self.exposure.apply(image)
        out = self.wheels.apply(out)
        out = self.curves.apply(out)
        return np.clip(out, 0.0, 1.0)
