"""A parametric multi-band EQ built from RBJ-cookbook biquad filters.

No SciPy dependency: biquads are the same handful of multiply-adds a native
Accelerate/vDSP implementation would use, so swapping in a native filter
later changes nothing at the call site.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import List

import numpy as np


class FilterType(str, Enum):
    PEAK = "peak"
    LOW_SHELF = "low_shelf"
    HIGH_SHELF = "high_shelf"
    LOW_PASS = "low_pass"
    HIGH_PASS = "high_pass"


@dataclass
class Biquad:
    """Direct Form I biquad; coefficients from Robert Bristow-Johnson's cookbook."""

    b0: float
    b1: float
    b2: float
    a1: float
    a2: float

    @classmethod
    def design(cls, filter_type: FilterType, freq_hz: float, sample_rate: int, q: float = 0.707, gain_db: float = 0.0) -> "Biquad":
        w0 = 2 * math.pi * freq_hz / sample_rate
        cos_w0, sin_w0 = math.cos(w0), math.sin(w0)
        alpha = sin_w0 / (2 * q)
        A = 10 ** (gain_db / 40.0)

        if filter_type == FilterType.PEAK:
            b0 = 1 + alpha * A
            b1 = -2 * cos_w0
            b2 = 1 - alpha * A
            a0 = 1 + alpha / A
            a1 = -2 * cos_w0
            a2 = 1 - alpha / A
        elif filter_type == FilterType.LOW_SHELF:
            sq = 2 * math.sqrt(A) * alpha
            b0 = A * ((A + 1) - (A - 1) * cos_w0 + sq)
            b1 = 2 * A * ((A - 1) - (A + 1) * cos_w0)
            b2 = A * ((A + 1) - (A - 1) * cos_w0 - sq)
            a0 = (A + 1) + (A - 1) * cos_w0 + sq
            a1 = -2 * ((A - 1) + (A + 1) * cos_w0)
            a2 = (A + 1) + (A - 1) * cos_w0 - sq
        elif filter_type == FilterType.HIGH_SHELF:
            sq = 2 * math.sqrt(A) * alpha
            b0 = A * ((A + 1) + (A - 1) * cos_w0 + sq)
            b1 = -2 * A * ((A - 1) + (A + 1) * cos_w0)
            b2 = A * ((A + 1) + (A - 1) * cos_w0 - sq)
            a0 = (A + 1) - (A - 1) * cos_w0 + sq
            a1 = 2 * ((A - 1) - (A + 1) * cos_w0)
            a2 = (A + 1) - (A - 1) * cos_w0 - sq
        elif filter_type == FilterType.LOW_PASS:
            b0 = (1 - cos_w0) / 2
            b1 = 1 - cos_w0
            b2 = (1 - cos_w0) / 2
            a0 = 1 + alpha
            a1 = -2 * cos_w0
            a2 = 1 - alpha
        else:  # HIGH_PASS
            b0 = (1 + cos_w0) / 2
            b1 = -(1 + cos_w0)
            b2 = (1 + cos_w0) / 2
            a0 = 1 + alpha
            a1 = -2 * cos_w0
            a2 = 1 - alpha

        return cls(b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0)

    def process(self, samples: np.ndarray) -> np.ndarray:
        out = np.empty_like(samples, dtype=np.float64)
        x1 = x2 = y1 = y2 = 0.0
        b0, b1, b2, a1, a2 = self.b0, self.b1, self.b2, self.a1, self.a2
        src = samples.astype(np.float64)
        for i in range(len(src)):
            x0 = src[i]
            y0 = b0 * x0 + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
            out[i] = y0
            x2, x1 = x1, x0
            y2, y1 = y1, y0
        return out.astype(samples.dtype)


@dataclass
class EQBand:
    filter_type: FilterType
    freq_hz: float
    q: float = 0.707
    gain_db: float = 0.0


@dataclass
class Equalizer:
    """A chain of EQ bands applied in series (SOURCE -> ... -> EQ in the audio graph)."""

    bands: List[EQBand] = field(default_factory=list)

    def add_band(self, band: EQBand) -> "Equalizer":
        self.bands.append(band)
        return self

    def process(self, samples: np.ndarray, sample_rate: int) -> np.ndarray:
        out = samples
        for band in self.bands:
            biquad = Biquad.design(band.filter_type, band.freq_hz, sample_rate, band.q, band.gain_db)
            out = biquad.process(out)
        return out
