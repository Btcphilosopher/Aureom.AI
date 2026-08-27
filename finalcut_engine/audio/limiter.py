"""A brickwall peak limiter: guarantees output never exceeds ``ceiling_db``."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass
class Limiter:
    ceiling_db: float = -0.3
    release_ms: float = 50.0

    def process(self, samples: np.ndarray, sample_rate: int) -> np.ndarray:
        x = samples.astype(np.float64)
        ceiling = 10 ** (self.ceiling_db / 20.0)
        eps = 1e-9
        required_gain = np.minimum(1.0, ceiling / np.maximum(np.abs(x), eps))

        release_coef = math.exp(-1.0 / (sample_rate * (self.release_ms / 1000.0))) if self.release_ms > 0 else 0.0
        gain = np.empty_like(required_gain)
        current = 1.0
        for i in range(len(required_gain)):
            need = required_gain[i]
            # Instant attack (never allow an overshoot to slip through), smoothed release.
            current = need if need < current else release_coef * current + (1 - release_coef) * need
            gain[i] = current

        out = x * gain
        # Hard safety clip in case of numerical edge cases.
        out = np.clip(out, -ceiling, ceiling)
        return out.astype(samples.dtype)
