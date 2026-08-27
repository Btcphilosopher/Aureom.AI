"""Smart colour matching: propose grade parameters that match one clip to another.

Uses per-channel statistical (Reinhard-style) colour transfer to derive a
:class:`~finalcut_engine.colour.colour_wheels.ColourWheel` — parameters, not a
baked pixel remap, so the result is a *proposal* the editor can review,
tweak, or reject (spec sections 10 and 15 both require this to stay
non-destructive).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from finalcut_engine.colour.colour_wheels import ColourWheel


@dataclass
class MatchResult:
    wheel: ColourWheel
    confidence: float  # in [0, 1]; how well the proposed linear grade explains the difference


class SmartColourMatching:
    def analyze(self, reference: np.ndarray, target: np.ndarray) -> MatchResult:
        """``reference``/``target``: float images in [0, 1], shape (H, W, 3)."""
        ref = reference.astype(np.float64).reshape(-1, 3)
        tgt = target.astype(np.float64).reshape(-1, 3)

        ref_mean, ref_std = ref.mean(axis=0), ref.std(axis=0) + 1e-6
        tgt_mean, tgt_std = tgt.mean(axis=0), tgt.std(axis=0) + 1e-6

        gain = ref_std / tgt_std
        lift = ref_mean - tgt_mean * gain

        wheel = ColourWheel(lift=tuple(lift), gamma=(1.0, 1.0, 1.0), gain=tuple(gain))

        # A linear grade always reproduces the reference's mean/std exactly by
        # construction, so that can't measure quality. Instead, confidence
        # reflects how drastic the proposed correction is: a small nudge is
        # trustworthy; a huge gain/lift swing likely means the two shots are
        # too different in content for a simple global match to be reliable.
        correction_magnitude = float(np.mean(np.abs(gain - 1.0)) + np.mean(np.abs(lift)))
        confidence = float(np.clip(1.0 - correction_magnitude, 0.0, 1.0))

        return MatchResult(wheel=wheel, confidence=confidence)
