"""Lift / Gamma / Gain colour wheels, expressed as an ASC CDL transform.

``ColourWheel`` mirrors Final Cut Pro's colour board: three RGB triples for
shadows (lift), midtones (gamma) and highlights (gain). Internally this is
exactly the ASC Color Decision List primary grade — the same math a
professional grading tool (and a native Metal shader) would apply — so the
parameters translate directly to an interchange format later.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

RGB = tuple[float, float, float]


@dataclass
class ColourWheel:
    lift: RGB = (0.0, 0.0, 0.0)  # ASC CDL "offset"; shifts shadows
    gamma: RGB = (1.0, 1.0, 1.0)  # ASC CDL "power" is 1/gamma; shifts midtones
    gain: RGB = (1.0, 1.0, 1.0)  # ASC CDL "slope"; shifts highlights

    def apply(self, image: np.ndarray) -> np.ndarray:
        """``image``: float array in [0, 1], shape (..., 3)."""
        slope = np.array(self.gain, dtype=np.float64)
        offset = np.array(self.lift, dtype=np.float64)
        power = 1.0 / np.array(self.gamma, dtype=np.float64)

        out = image.astype(np.float64) * slope + offset
        out = np.clip(out, 0.0, None)
        out = np.power(out, power)
        return np.clip(out, 0.0, 1.0)

    def is_identity(self) -> bool:
        return self.lift == (0.0, 0.0, 0.0) and self.gamma == (1.0, 1.0, 1.0) and self.gain == (1.0, 1.0, 1.0)
