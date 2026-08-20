"""
Power-efficiency (performance-per-watt) tracking over the course of a run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class EfficiencySample:
    timestep: int
    tflops: float
    watts: float
    gflops_per_watt: float


class EfficiencyTracker:
    def __init__(self) -> None:
        self.samples: List[EfficiencySample] = []

    def record(self, timestep: int, tflops: float, watts: float) -> EfficiencySample:
        gflops_per_watt = (tflops * 1000.0) / watts if watts > 0 else 0.0
        sample = EfficiencySample(timestep=timestep, tflops=tflops, watts=watts,
                                   gflops_per_watt=gflops_per_watt)
        self.samples.append(sample)
        return sample

    def average_gflops_per_watt(self) -> float:
        if not self.samples:
            return 0.0
        return sum(s.gflops_per_watt for s in self.samples) / len(self.samples)

    def best_sample(self) -> EfficiencySample | None:
        if not self.samples:
            return None
        return max(self.samples, key=lambda s: s.gflops_per_watt)
