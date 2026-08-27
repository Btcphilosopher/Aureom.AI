"""A feed-forward dynamic range compressor with an attack/release envelope follower."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass
class Compressor:
    threshold_db: float = -18.0
    ratio: float = 4.0  # e.g. 4:1
    attack_ms: float = 10.0
    release_ms: float = 100.0
    knee_db: float = 6.0
    makeup_gain_db: float = 0.0

    def _gain_reduction_db(self, level_db: np.ndarray) -> np.ndarray:
        """Soft-knee static compression curve, in dB."""
        over = level_db - self.threshold_db
        half_knee = self.knee_db / 2
        reduction = np.zeros_like(level_db)

        # Below the knee: no reduction.
        below = over <= -half_knee
        # Above the knee: full ratio.
        above = over >= half_knee
        # Inside the knee: smooth quadratic transition (standard soft-knee formula).
        inside = ~below & ~above

        reduction[above] = over[above] - over[above] / self.ratio
        knee_over = over[inside] + half_knee
        reduction[inside] = (1 / self.ratio - 1) * (knee_over**2) / (2 * self.knee_db)
        return reduction

    def process(self, samples: np.ndarray, sample_rate: int) -> np.ndarray:
        x = samples.astype(np.float64)
        eps = 1e-9
        level_db = 20 * np.log10(np.maximum(np.abs(x), eps))
        target_reduction = self._gain_reduction_db(level_db)

        attack_coef = math.exp(-1.0 / (sample_rate * (self.attack_ms / 1000.0))) if self.attack_ms > 0 else 0.0
        release_coef = math.exp(-1.0 / (sample_rate * (self.release_ms / 1000.0))) if self.release_ms > 0 else 0.0

        envelope = np.zeros_like(target_reduction)  # positive dB amount to subtract
        current = 0.0
        for i in range(len(target_reduction)):
            desired = target_reduction[i]
            coef = attack_coef if desired > current else release_coef  # reduction increasing = attack
            current = coef * current + (1 - coef) * desired
            envelope[i] = current

        makeup = 10 ** (self.makeup_gain_db / 20.0)
        out = x * (10 ** (-envelope / 20.0)) * makeup
        return out.astype(samples.dtype)
