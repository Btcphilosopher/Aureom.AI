"""The AI Auto-Edit assistant (spec section 14).

Given scored shot candidates and a target duration, proposes a timeline —
never writes to the user's project directly. Every non-trivial decision
(dropping a shot, preferring one take over another) is surfaced as an
:class:`~finalcut_engine.ai.Suggestion`:

```
AI SUGGESTION

Replace Clip 14
Reason:
Clip 18 has stronger visual quality.

[ACCEPT] [REJECT]
```
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from finalcut_engine.ai import Suggestion
from finalcut_engine.ai.highlight_detection import HighlightDetector, ShotFeatures


@dataclass
class ProposedTimeline:
    shot_ids: List[str]
    total_duration_seconds: float
    suggestions: List[Suggestion] = field(default_factory=list)


@dataclass
class AutoEditAssistant:
    detector: HighlightDetector = field(default_factory=HighlightDetector)

    def propose_edit(self, shots: List[ShotFeatures], target_duration_seconds: float) -> ProposedTimeline:
        if not shots:
            return ProposedTimeline(shot_ids=[], total_duration_seconds=0.0)

        scores = {s.shot_id: self.detector.score(s) for s in shots}
        suggestions: List[Suggestion] = []

        # 1. Within each group of "the same content" (duplicate takes), keep only
        #    the strongest shot and propose replacing the rest with it.
        groups: dict[str, List[ShotFeatures]] = {}
        for s in shots:
            groups.setdefault(s.content_group or s.shot_id, []).append(s)

        kept: List[ShotFeatures] = []
        for group_shots in groups.values():
            ranked = sorted(group_shots, key=lambda s: scores[s.shot_id], reverse=True)
            best = ranked[0]
            kept.append(best)
            for weaker in ranked[1:]:
                suggestions.append(
                    Suggestion(
                        kind="replace_clip",
                        summary=f"Replace {weaker.shot_id}",
                        reason=f"{best.shot_id} has stronger visual quality.",
                        confidence=float(min(1.0, max(0.0, scores[best.shot_id] - scores[weaker.shot_id]) + 0.5)),
                        payload={"remove_shot_id": weaker.shot_id, "keep_shot_id": best.shot_id},
                    )
                )

        # 2. Fit the remaining candidates to the target duration, favouring the
        #    highest-scoring shots (at least one shot is always kept).
        by_score = sorted(kept, key=lambda s: scores[s.shot_id], reverse=True)
        selected_ids: set[str] = set()
        total = 0.0
        for s in by_score:
            if not selected_ids or total + s.duration_seconds <= target_duration_seconds:
                selected_ids.add(s.shot_id)
                total += s.duration_seconds

        # 3. Preserve original shot order in the final sequence, for pacing/continuity.
        timeline_order = [s.shot_id for s in shots if s.shot_id in selected_ids]

        dropped = [s.shot_id for s in kept if s.shot_id not in selected_ids]
        if dropped:
            suggestions.append(
                Suggestion(
                    kind="trim_to_duration",
                    summary=f"Drop {len(dropped)} lower-scoring shot(s)",
                    reason=f"Fits the edit to the {target_duration_seconds:.0f}s target duration.",
                    confidence=0.6,
                    payload={"dropped_shot_ids": dropped},
                )
            )

        return ProposedTimeline(shot_ids=timeline_order, total_duration_seconds=total, suggestions=suggestions)
