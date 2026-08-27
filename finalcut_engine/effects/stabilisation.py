"""Frame-to-frame stabilisation via FFT phase correlation.

Estimates camera motion as a pure translation between consecutive frames
(the classic, dependency-free stabilisation technique); a native build would
add rotation/scale (similarity transform) via a log-polar phase correlation
pass, and feed the result through a real optical-flow tracker for
sub-pixel accuracy.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Tuple

import numpy as np


def phase_correlation_shift(a: np.ndarray, b: np.ndarray) -> Tuple[float, float]:
    """Returns (dy, dx): how far ``b`` is shifted relative to ``a``."""
    fa = np.fft.fft2(a)
    fb = np.fft.fft2(b)
    cross_power = fa * np.conj(fb)
    cross_power /= np.abs(cross_power) + 1e-12
    correlation = np.abs(np.fft.ifft2(cross_power))
    peak = np.unravel_index(np.argmax(correlation), correlation.shape)
    h, w = a.shape
    dy = peak[0] if peak[0] < h / 2 else peak[0] - h
    dx = peak[1] if peak[1] < w / 2 else peak[1] - w
    # Empirically (verified against a known synthetic translation), the peak
    # of ifft(Fa * conj(Fb)) sits at -shift for b(x) = a(x - shift); negate to
    # report the shift itself, matching this function's documented contract.
    return float(-dy), float(-dx)


def _to_gray(frame: np.ndarray) -> np.ndarray:
    return frame.mean(axis=2) if frame.ndim == 3 else frame


@dataclass
class Stabiliser:
    smoothing_window: int = 5

    def estimate_camera_motion(self, frames: Sequence[np.ndarray]) -> List[Tuple[float, float]]:
        """Cumulative (dy, dx) camera displacement at each frame, frame 0 = (0, 0)."""
        if not frames:
            return []
        grays = [_to_gray(f).astype(np.float64) for f in frames]
        cumulative = [(0.0, 0.0)]
        cy, cx = 0.0, 0.0
        for i in range(1, len(grays)):
            dy, dx = phase_correlation_shift(grays[i - 1], grays[i])
            cy, cx = cy + dy, cx + dx
            cumulative.append((cy, cx))
        return cumulative

    def _smooth(self, path: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        if self.smoothing_window <= 1 or len(path) < 2:
            return path
        ys = np.array([p[0] for p in path])
        xs = np.array([p[1] for p in path])
        kernel = np.ones(self.smoothing_window) / self.smoothing_window
        pad = self.smoothing_window // 2
        ys_smooth = np.convolve(np.pad(ys, pad, mode="edge"), kernel, mode="valid")[: len(ys)]
        xs_smooth = np.convolve(np.pad(xs, pad, mode="edge"), kernel, mode="valid")[: len(xs)]
        return list(zip(ys_smooth.tolist(), xs_smooth.tolist()))

    def stabilising_corrections(self, frames: Sequence[np.ndarray]) -> List[Tuple[float, float]]:
        """Per-frame (dy, dx) to apply so the smoothed camera path becomes the new path."""
        raw_path = self.estimate_camera_motion(frames)
        smoothed_path = self._smooth(raw_path)
        return [(sy - ry, sx - rx) for (ry, rx), (sy, sx) in zip(raw_path, smoothed_path)]

    def apply(self, frames: Sequence[np.ndarray], corrections: Sequence[Tuple[float, float]]) -> List[np.ndarray]:
        """Integer-pixel correction via ``np.roll`` (a native build would use a
        sub-pixel warp on the GPU); edges wrap rather than crop for simplicity.
        """
        out = []
        for frame, (dy, dx) in zip(frames, corrections):
            shifted = np.roll(frame, int(round(dy)), axis=0)
            shifted = np.roll(shifted, int(round(dx)), axis=1)
            out.append(shifted)
        return out
