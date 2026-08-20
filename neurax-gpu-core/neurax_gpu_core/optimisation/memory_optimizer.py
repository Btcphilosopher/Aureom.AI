"""
Memory-hierarchy advisory optimiser.

Analyses observed cache hit rates and bandwidth utilisation and produces
human-readable recommendations (cache resizing, bandwidth allocation) for
the next architecture revision. Cache/bandwidth capacity cannot realistically
be changed mid-run on real silicon, so this module is advisory (surfaced on
the dashboard / fed to :mod:`ai.gpu_tuner` for the next design iteration)
rather than mutating a live run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class MemoryRecommendation:
    timestep: int
    message: str
    severity: str  # 'info' | 'warning' | 'critical'


class MemoryOptimizer:
    def __init__(self, evaluation_interval: int = 25):
        self.evaluation_interval = evaluation_interval
        self.recommendations: List[MemoryRecommendation] = []

    def evaluate(self, timestep: int, l1_hit_rate: float, l2_hit_rate: float,
                 bandwidth_utilisation: float, mem_access_fraction: float) -> List[MemoryRecommendation]:
        if timestep % self.evaluation_interval != 0:
            return []

        new_recs: List[MemoryRecommendation] = []
        if l1_hit_rate < 0.55:
            new_recs.append(MemoryRecommendation(
                timestep=timestep,
                message=f"L1 hit rate is low ({l1_hit_rate:.1%}); consider a larger L1 or better data locality "
                        f"in the current kernel's access pattern.",
                severity="warning",
            ))
        if l2_hit_rate < 0.40 and mem_access_fraction > 0.25:
            new_recs.append(MemoryRecommendation(
                timestep=timestep,
                message=f"L2 hit rate is low ({l2_hit_rate:.1%}) with {mem_access_fraction:.1%} of accesses "
                        f"reaching DRAM; the working set likely exceeds L2 capacity -- consider growing L2 or "
                        f"tiling the kernel.",
                severity="warning",
            ))
        if bandwidth_utilisation > 0.92:
            new_recs.append(MemoryRecommendation(
                timestep=timestep,
                message=f"Memory bandwidth utilisation is {bandwidth_utilisation:.1%} -- the workload is "
                        f"bandwidth-bound; more SMs will not help without also growing VRAM/HBM bandwidth.",
                severity="critical",
            ))
        elif bandwidth_utilisation < 0.15 and mem_access_fraction > 0.1:
            new_recs.append(MemoryRecommendation(
                timestep=timestep,
                message=f"Memory bandwidth utilisation is low ({bandwidth_utilisation:.1%}); bandwidth "
                        f"allocation could safely be redirected toward a narrower, cheaper memory subsystem.",
                severity="info",
            ))

        self.recommendations.extend(new_recs)
        return new_recs
