"""AI-facing wrapper around ``colour.matching``: gates proposals by confidence
and frames them as reviewable :class:`~finalcut_engine.ai.Suggestion` objects.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from finalcut_engine.ai import Suggestion
from finalcut_engine.colour.matching import SmartColourMatching


@dataclass
class AIColourMatcher:
    min_confidence: float = 0.3

    def suggest(self, reference: np.ndarray, target: np.ndarray, target_clip_name: str = "clip") -> Suggestion | None:
        result = SmartColourMatching().analyze(reference, target)
        if result.confidence < self.min_confidence:
            return None
        return Suggestion(
            kind="colour_match",
            summary=f"Match {target_clip_name} to the reference shot's colour",
            reason="Proposed lift/gamma/gain derived from the reference clip's colour statistics",
            confidence=result.confidence,
            payload={"lift": result.wheel.lift, "gamma": result.wheel.gamma, "gain": result.wheel.gain},
        )
