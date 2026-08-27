"""Highlight detection: rank shots by a weighted mix of motion, audio, speech,
duration and composition signals (spec section 13).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

import numpy as np

from finalcut_engine.ai import Suggestion
from finalcut_engine.media.analyzer import measure_audio_levels


@dataclass
class ShotFeatures:
    shot_id: str
    motion_score: float  # 0..1, mean inter-frame difference
    audio_intensity: float  # 0..1, normalised RMS
    speech_present: bool
    duration_seconds: float
    composition_score: float = 0.5  # 0..1; e.g. rule-of-thirds framing score
    content_group: str | None = None  # shots of "the same thing" (e.g. multiple takes), for de-duplication


def compute_motion_score(frames: Sequence[np.ndarray]) -> float:
    if len(frames) < 2:
        return 0.0
    diffs = [np.mean(np.abs(frames[i].astype(np.float64) - frames[i - 1].astype(np.float64))) for i in range(1, len(frames))]
    max_val = 255.0 if frames[0].dtype == np.uint8 else 1.0
    return float(np.clip(np.mean(diffs) / max_val, 0.0, 1.0))


def compute_audio_intensity(samples: np.ndarray) -> float:
    levels = measure_audio_levels(samples)
    # Map roughly [-60dB, 0dB] to [0, 1].
    return float(np.clip((levels.rms_dbfs + 60.0) / 60.0, 0.0, 1.0))


@dataclass
class HighlightDetector:
    motion_weight: float = 0.3
    audio_weight: float = 0.25
    speech_weight: float = 0.2
    duration_weight: float = 0.1
    composition_weight: float = 0.15
    ideal_duration_seconds: float = 4.0

    def _duration_score(self, duration: float) -> float:
        # Peaks at ideal_duration_seconds, falls off for very short or very long shots.
        ratio = duration / self.ideal_duration_seconds
        return float(np.clip(1.0 - abs(np.log(max(ratio, 1e-6))), 0.0, 1.0))

    def score(self, shot: ShotFeatures) -> float:
        return (
            self.motion_weight * shot.motion_score
            + self.audio_weight * shot.audio_intensity
            + self.speech_weight * (1.0 if shot.speech_present else 0.0)
            + self.duration_weight * self._duration_score(shot.duration_seconds)
            + self.composition_weight * shot.composition_score
        )

    def rank(self, shots: List[ShotFeatures]) -> List[Suggestion]:
        scored = sorted(((self.score(s), s) for s in shots), key=lambda pair: pair[0], reverse=True)
        return [
            Suggestion(
                kind="highlight",
                summary=f"Shot {s.shot_id} looks like a strong highlight",
                reason=(
                    f"motion={s.motion_score:.2f}, audio={s.audio_intensity:.2f}, "
                    f"speech={s.speech_present}, duration={s.duration_seconds:.1f}s"
                ),
                confidence=float(np.clip(score, 0.0, 1.0)),
                payload={"shot_id": s.shot_id, "score": score},
            )
            for score, s in scored
        ]
