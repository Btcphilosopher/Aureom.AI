"""
Runtime warp-scheduling optimiser.

Watches aggregate stall/divergence telemetry and, periodically, decides
whether a different warp-scheduling policy would likely reduce stalls --
optionally applying that decision live across every SM's schedulers. This
is the "AI optimises ... warp scheduling strategies" piece of the spec,
kept intentionally simple (a rule-based heuristic) rather than a black box,
so its recommendations stay auditable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from ..compute.sm_units import StreamingMultiprocessor
from ..compute.warp_scheduler import SchedulingPolicy


@dataclass
class SchedulingRecommendation:
    timestep: int
    previous_policy: SchedulingPolicy
    new_policy: SchedulingPolicy
    reason: str
    applied: bool


class SchedulingOptimizer:
    def __init__(self, evaluation_interval: int = 25, min_samples: int = 5):
        self.evaluation_interval = evaluation_interval
        self.min_samples = min_samples
        self._divergence_history: List[float] = []
        self._occupancy_history: List[float] = []
        self.recommendations: List[SchedulingRecommendation] = []

    def observe(self, divergence_rate: float, occupancy: float) -> None:
        self._divergence_history.append(divergence_rate)
        self._occupancy_history.append(occupancy)

    def _current_policy(self, sms: List[StreamingMultiprocessor]) -> SchedulingPolicy:
        if not sms or not sms[0].schedulers:
            return SchedulingPolicy.GREEDY_THEN_OLDEST
        return sms[0].schedulers[0].policy

    def maybe_retune(self, timestep: int, sms: List[StreamingMultiprocessor],
                      apply: bool = True) -> Optional[SchedulingRecommendation]:
        if timestep % self.evaluation_interval != 0 or len(self._divergence_history) < self.min_samples:
            return None

        recent_div = sum(self._divergence_history[-self.min_samples:]) / self.min_samples
        recent_occ = sum(self._occupancy_history[-self.min_samples:]) / self.min_samples
        current = self._current_policy(sms)

        new_policy = current
        reason = "no change: metrics within nominal range"
        if recent_div > 0.20 and current != SchedulingPolicy.GREEDY_THEN_OLDEST:
            new_policy = SchedulingPolicy.GREEDY_THEN_OLDEST
            reason = f"high divergence rate ({recent_div:.2f}) favours prioritising the oldest warp to reconverge sooner"
        elif recent_div <= 0.20 and recent_occ < 0.5 and current != SchedulingPolicy.ROUND_ROBIN:
            new_policy = SchedulingPolicy.ROUND_ROBIN
            reason = f"low occupancy ({recent_occ:.2f}) favours fairness across resident warps to hide latency better"

        applied_now = apply and new_policy != current
        if applied_now:
            for sm in sms:
                for scheduler in sm.schedulers:
                    scheduler.policy = new_policy

        rec = SchedulingRecommendation(
            timestep=timestep, previous_policy=current, new_policy=new_policy,
            reason=reason, applied=applied_now,
        )
        self.recommendations.append(rec)
        return rec
