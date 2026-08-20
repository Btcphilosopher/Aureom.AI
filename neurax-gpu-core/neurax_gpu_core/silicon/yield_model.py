"""
Die yield model.

Implements the standard Murphy / negative-binomial defect model used in
semiconductor cost analysis: yield falls off as the die gets bigger,
because a bigger die is statistically more likely to overlap a random
process defect. Bigger, denser dies (more SMs, more cache) always cost
more *and* yield worse -- exactly the trade-off an architecture optimiser
needs to see.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..utils.config import SiliconConfig


@dataclass
class YieldResult:
    die_area_mm2: float
    defect_density_per_cm2: float
    raw_yield_fraction: float          # Poisson model, worst case
    murphy_yield_fraction: float       # Murphy model, more realistic clustering
    dies_per_wafer: int
    good_dies_per_wafer: int


class YieldModel:
    def __init__(self, config: SiliconConfig):
        self.config = config

    def dies_per_wafer(self, die_area_mm2: float) -> int:
        """Classic wafer-packing approximation accounting for edge losses."""
        if die_area_mm2 <= 0:
            return 0
        r = self.config.wafer_diameter_mm / 2.0
        wafer_area = math.pi * r * r
        edge_loss = math.pi * self.config.wafer_diameter_mm / math.sqrt(2.0 * die_area_mm2)
        n = (wafer_area / die_area_mm2) - edge_loss
        return max(0, int(n))

    def poisson_yield(self, die_area_mm2: float) -> float:
        d0 = self.config.defect_density_per_cm2 / 100.0  # defects per mm^2
        return math.exp(-d0 * die_area_mm2)

    def murphy_yield(self, die_area_mm2: float) -> float:
        """Murphy's model: Y = ((1 - exp(-2*AD)) / (2*AD))^2, a smoother,
        more realistic falloff than the pure Poisson bound above."""
        d0 = self.config.defect_density_per_cm2 / 100.0
        ad = d0 * die_area_mm2
        if ad <= 1e-9:
            return 1.0
        return ((1 - math.exp(-2 * ad)) / (2 * ad)) ** 2

    def evaluate(self, die_area_mm2: float) -> YieldResult:
        dpw = self.dies_per_wafer(die_area_mm2)
        raw = self.poisson_yield(die_area_mm2)
        murphy = self.murphy_yield(die_area_mm2)
        good = int(dpw * murphy)
        return YieldResult(
            die_area_mm2=die_area_mm2, defect_density_per_cm2=self.config.defect_density_per_cm2,
            raw_yield_fraction=raw, murphy_yield_fraction=murphy, dies_per_wafer=dpw,
            good_dies_per_wafer=good,
        )
