"""Fast, decode-once technical media analysis.

This is the low-level numeric toolkit (frame-difference shot detection, audio
level metering, black-frame detection) shared by the AI subsystem's
higher-level, user-facing analyzers (see ``ai.scene_detection``,
``ai.highlight_detection``) and by import-time indexing. Keeping the numeric
core here means the AI layer stays about *interpretation and suggestions*,
not signal processing.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Sequence

import numpy as np


def frame_histogram(frame: np.ndarray, bins: int = 32) -> np.ndarray:
    """A normalised per-channel colour histogram used as a cheap frame fingerprint.

    Accepts either uint8 frames (range 0-255) or float frames (range 0-1) —
    both are common across this codebase (decoded frames vs. the colour/effects
    pipelines' float working space) — and bins each to its own native range.
    """
    value_range = (0, 255) if np.issubdtype(frame.dtype, np.integer) else (0.0, 1.0)
    hist = []
    channels = frame.shape[2] if frame.ndim == 3 else 1
    flat = frame.reshape(-1, channels) if frame.ndim == 3 else frame.reshape(-1, 1)
    for c in range(channels):
        h, _ = np.histogram(flat[:, c], bins=bins, range=value_range)
        hist.append(h.astype(np.float64) / max(1, flat.shape[0]))
    return np.concatenate(hist)


def histogram_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Bhattacharyya-style distance in [0, 1]; 0 = identical, 1 = disjoint."""
    bc = np.sum(np.sqrt(np.clip(a, 0, None) * np.clip(b, 0, None)))
    return float(np.clip(1.0 - bc, 0.0, 1.0))


@dataclass
class ShotBoundary:
    frame_index: int
    score: float  # how large the visual discontinuity was, in [0, 1]


def detect_shot_boundaries(frames: Sequence[np.ndarray], threshold: float = 0.35) -> List[ShotBoundary]:
    """Detect hard cuts between shots using per-frame colour histogram deltas.

    A production build would run this on the GPU against decoded frames from
    AVFoundation; the algorithm (histogram-delta thresholding) is the same
    one professional NLEs have used for scene detection for two decades.
    """
    if len(frames) < 2:
        return []
    boundaries: List[ShotBoundary] = []
    prev_hist = frame_histogram(frames[0])
    for i in range(1, len(frames)):
        hist = frame_histogram(frames[i])
        dist = histogram_distance(prev_hist, hist)
        if dist >= threshold:
            boundaries.append(ShotBoundary(frame_index=i, score=dist))
        prev_hist = hist
    return boundaries


def is_black_frame(frame: np.ndarray, luma_threshold: float = 8.0) -> bool:
    """``luma_threshold`` is on a 0-255 scale regardless of the frame's own dtype."""
    luma = frame.mean() if frame.ndim == 2 else frame.mean(axis=2).mean()
    if not np.issubdtype(frame.dtype, np.integer):
        luma = luma * 255.0
    return bool(luma < luma_threshold)


@dataclass
class AudioLevels:
    peak_dbfs: float
    rms_dbfs: float
    clipping: bool


def measure_audio_levels(samples: np.ndarray) -> AudioLevels:
    """``samples`` are float32 in [-1, 1], mono or interleaved multichannel."""
    if samples.size == 0:
        return AudioLevels(peak_dbfs=-math.inf, rms_dbfs=-math.inf, clipping=False)
    peak = float(np.max(np.abs(samples)))
    rms = float(np.sqrt(np.mean(np.square(samples))))
    to_db = lambda v: 20.0 * math.log10(v) if v > 1e-9 else -120.0
    return AudioLevels(peak_dbfs=to_db(peak), rms_dbfs=to_db(rms), clipping=peak >= 0.999)


class MediaAnalyzer:
    """Facade used by the import pipeline to run a quick technical pass on new media."""

    def analyze_video(self, frames: Sequence[np.ndarray]) -> dict:
        boundaries = detect_shot_boundaries(frames)
        black_frames = [i for i, f in enumerate(frames) if is_black_frame(f)]
        return {
            "shot_boundaries": [b.frame_index for b in boundaries],
            "shot_boundary_scores": [b.score for b in boundaries],
            "black_frames": black_frames,
            "frame_count": len(frames),
        }

    def analyze_audio(self, samples: np.ndarray) -> dict:
        levels = measure_audio_levels(samples)
        return {"peak_dbfs": levels.peak_dbfs, "rms_dbfs": levels.rms_dbfs, "clipping": levels.clipping}
