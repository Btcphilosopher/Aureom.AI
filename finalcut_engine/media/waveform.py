"""Peak/RMS waveform envelope extraction for timeline UI rendering.

This is the core numeric algorithm; :mod:`finalcut_engine.audio.waveform`
wraps it with track/clip-aware caching.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class WaveformData:
    """Per-pixel-column min/max envelope, ready to draw as a filled polygon."""

    minimums: np.ndarray
    maximums: np.ndarray
    rms: np.ndarray
    samples_per_pixel: int
    sample_rate: int

    def duration_seconds(self) -> float:
        return len(self.minimums) * self.samples_per_pixel / self.sample_rate


class WaveformGenerator:
    def generate(self, samples: np.ndarray, sample_rate: int, pixels_per_second: int = 50) -> WaveformData:
        """``samples``: float32 in [-1, 1], shape (n,) mono or (n, channels)."""
        if samples.ndim > 1:
            samples = samples.mean(axis=1)
        samples_per_pixel = max(1, int(sample_rate / pixels_per_second))
        n_pixels = max(1, len(samples) // samples_per_pixel)
        trimmed = samples[: n_pixels * samples_per_pixel]
        chunks = trimmed.reshape(n_pixels, samples_per_pixel)
        mins = chunks.min(axis=1)
        maxs = chunks.max(axis=1)
        rms = np.sqrt(np.mean(np.square(chunks), axis=1))
        return WaveformData(
            minimums=mins, maximums=maxs, rms=rms, samples_per_pixel=samples_per_pixel, sample_rate=sample_rate
        )
