"""
Per-discipline reputation. This is the single source of truth
``world.event_generation`` and ``progression.unlock_tree`` both read to
gate content -- nothing else in the engine is allowed to duplicate a rep
number, so there is exactly one place progression state can drift.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

DISCIPLINES = ("street", "circuit", "drift", "offroad", "endurance")
REP_PER_TIER = 8.0
MAX_TIER = 10


@dataclass
class ReputationBook:
    scores: Dict[str, float] = field(default_factory=lambda: {d: 0.0 for d in DISCIPLINES})

    def gain(self, discipline: str, amount: float) -> None:
        if discipline not in self.scores:
            self.scores[discipline] = 0.0
        self.scores[discipline] = max(0.0, self.scores[discipline] + amount)

    def tier(self, discipline: str) -> int:
        return min(MAX_TIER, 1 + int(self.scores.get(discipline, 0.0) // REP_PER_TIER))

    def overall_tier(self) -> int:
        if not self.scores:
            return 1
        return min(MAX_TIER, 1 + int((sum(self.scores.values()) / len(self.scores)) // REP_PER_TIER))

    def total(self) -> float:
        return sum(self.scores.values())

    def as_dict(self) -> Dict[str, float]:
        return dict(self.scores)

    def progress_to_next_tier(self, discipline: str) -> float:
        """0..1 fraction of the way to the discipline's next tier."""
        score = self.scores.get(discipline, 0.0)
        return (score % REP_PER_TIER) / REP_PER_TIER
