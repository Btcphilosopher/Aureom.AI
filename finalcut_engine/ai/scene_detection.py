"""Scene/shot/cut detection, surfaced as review-able suggestions."""
from __future__ import annotations

from typing import List, Sequence

import numpy as np

from finalcut_engine.ai import Suggestion
from finalcut_engine.media.analyzer import detect_shot_boundaries


class SceneDetector:
    def __init__(self, threshold: float = 0.35) -> None:
        self.threshold = threshold

    def suggest_cuts(self, frames: Sequence[np.ndarray]) -> List[Suggestion]:
        boundaries = detect_shot_boundaries(frames, threshold=self.threshold)
        return [
            Suggestion(
                kind="scene_cut",
                summary=f"Likely shot change at frame {b.frame_index}",
                reason=f"Colour histogram changed by {b.score:.2f} between consecutive frames",
                confidence=b.score,
                payload={"frame_index": b.frame_index},
            )
            for b in boundaries
        ]
