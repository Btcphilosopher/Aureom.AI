"""Production economics / unit-cost engine (spec items 39-40)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CostInputs:
    material_cost: float
    energy_cost: float
    labour_cost: float
    maintenance_cost: float
    depreciation_cost: float
    scrap_cost: float
    logistics_cost: float
    overhead_cost: float

    @property
    def total_cost(self) -> float:
        return (self.material_cost + self.energy_cost + self.labour_cost + self.maintenance_cost
                + self.depreciation_cost + self.scrap_cost + self.logistics_cost + self.overhead_cost)


@dataclass
class UnitCostResult:
    cost_per_cell: float
    cost_per_kwh: float
    cost_per_module: float
    cost_per_pack: float
    breakdown_pct: dict[str, float]


class CostEngine:
    def compute_unit_costs(
        self,
        inputs: CostInputs,
        cells_produced: int,
        kwh_produced: float,
        modules_produced: int,
        packs_produced: int,
    ) -> UnitCostResult:
        total = inputs.total_cost
        cells = max(cells_produced, 1)
        kwh = max(kwh_produced, 1e-6)
        modules = max(modules_produced, 1)
        packs = max(packs_produced, 1)

        breakdown_pct = {
            field: 100.0 * value / total if total > 0 else 0.0
            for field, value in [
                ("material", inputs.material_cost), ("energy", inputs.energy_cost),
                ("labour", inputs.labour_cost), ("maintenance", inputs.maintenance_cost),
                ("depreciation", inputs.depreciation_cost), ("scrap", inputs.scrap_cost),
                ("logistics", inputs.logistics_cost), ("overhead", inputs.overhead_cost),
            ]
        }

        return UnitCostResult(
            cost_per_cell=total / cells,
            cost_per_kwh=total / kwh,
            cost_per_module=total / modules,
            cost_per_pack=total / packs,
            breakdown_pct=breakdown_pct,
        )
