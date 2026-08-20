"""
Occupancy analysis: theoretical (resource-limited) vs achieved warp
occupancy, plus SIMT lane efficiency (how much of a warp's 32 lanes are
actually active on average, i.e. the cost of branch divergence).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from ..compute.sm_units import StreamingMultiprocessor


@dataclass
class OccupancySnapshot:
    theoretical_occupancy: float   # register/shared-mem/block limited ceiling
    achieved_occupancy: float      # currently resident warps / that ceiling
    mean_active_warps_fraction: float  # active_warps this cycle / resident warps
    sm_occupancies: List[float]


class OccupancyAnalyzer:
    def __init__(self, sms: List[StreamingMultiprocessor], config_max_warps_per_sm: int):
        self.sms = sms
        self.config_max_warps_per_sm = config_max_warps_per_sm

    def theoretical_occupancy(self) -> float:
        if not self.sms:
            return 0.0
        ratios = [sm.max_resident_warps / self.config_max_warps_per_sm for sm in self.sms]
        return sum(ratios) / len(ratios)

    def snapshot(self, active_warps_total: int, resident_warps_total: int) -> OccupancySnapshot:
        sm_occ = [sm.occupancy() for sm in self.sms]
        achieved = sum(sm_occ) / len(sm_occ) if sm_occ else 0.0
        active_frac = (active_warps_total / resident_warps_total) if resident_warps_total > 0 else 0.0
        return OccupancySnapshot(
            theoretical_occupancy=self.theoretical_occupancy(),
            achieved_occupancy=achieved,
            mean_active_warps_fraction=active_frac,
            sm_occupancies=sm_occ,
        )

    @staticmethod
    def simt_efficiency(divergence_events: int, issued_instructions: int) -> float:
        """Rough proxy for average active-lane fraction: every divergence
        event costs (heuristically) half a warp's worth of wasted lanes."""
        if issued_instructions == 0:
            return 1.0
        penalty = min(1.0, (divergence_events * 0.5) / issued_instructions)
        return 1.0 - penalty
