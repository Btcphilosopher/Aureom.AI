"""
Per-die and per-good-die cost modelling: combines the wafer cost, the
area/transistor model and the yield model into a single "silicon cost
index" the optimisation layer can trade off against performance.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..utils.config import GPUConfig
from .area_model import AreaBreakdown, AreaModel
from .yield_model import YieldModel


@dataclass
class CostBreakdown:
    area: AreaBreakdown
    dies_per_wafer: int
    good_dies_per_wafer: int
    murphy_yield_fraction: float
    raw_cost_per_die_usd: float
    cost_per_good_die_usd: float
    cost_per_mm2_usd: float


class TransistorCostModel:
    def __init__(self, config: GPUConfig):
        self.config = config
        self.area_model = AreaModel(config)
        self.yield_model = YieldModel(config.silicon)

    def evaluate(self) -> CostBreakdown:
        area = self.area_model.estimate()
        yield_result = self.yield_model.evaluate(area.total_die_mm2)

        wafer_cost = self.config.silicon.wafer_cost_usd
        raw_cost_per_die = wafer_cost / yield_result.dies_per_wafer if yield_result.dies_per_wafer > 0 else float("inf")
        cost_per_good_die = (
            wafer_cost / yield_result.good_dies_per_wafer if yield_result.good_dies_per_wafer > 0 else float("inf")
        )
        cost_per_mm2 = raw_cost_per_die / area.total_die_mm2 if area.total_die_mm2 > 0 else float("inf")

        return CostBreakdown(
            area=area, dies_per_wafer=yield_result.dies_per_wafer,
            good_dies_per_wafer=yield_result.good_dies_per_wafer,
            murphy_yield_fraction=yield_result.murphy_yield_fraction,
            raw_cost_per_die_usd=raw_cost_per_die, cost_per_good_die_usd=cost_per_good_die,
            cost_per_mm2_usd=cost_per_mm2,
        )

    def silicon_cost_index(self) -> float:
        """A single scalar (arbitrary units, lower is better) the optimiser
        can weigh against a performance objective: good-die cost scaled by
        die area, so both "expensive because low yield" and "expensive
        because huge" dies score worse."""
        breakdown = self.evaluate()
        if breakdown.cost_per_good_die_usd == float("inf"):
            return float("inf")
        return breakdown.cost_per_good_die_usd * (breakdown.area.total_die_mm2 / 100.0)
