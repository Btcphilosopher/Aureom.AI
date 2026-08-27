"""Full manufacturing cost roll-up for one batch.

Combines ingredient, energy, labour, equipment, packaging, waste, and
transport/storage costs into a single :class:`ManufacturingCostResult`.
Every non-ingredient, non-energy cost is supplied as a simple rate
(currency/kg or currency/batch) rather than derived from the physical
engine -- these are commercial inputs, not simulation outputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from icecream_x.core.engine import PipelineResult
from icecream_x.economics.energy_cost import EnergyCostResult, flat_rate_cost
from icecream_x.economics.ingredient_cost import IngredientCostBreakdown, ingredient_cost_breakdown
from icecream_x.formulation.recipe import Recipe


@dataclass(frozen=True, slots=True)
class CostRates:
    labour_cost_per_batch: float = 25.0
    equipment_cost_per_batch: float = 15.0
    packaging_cost_per_kg: float = 0.35
    waste_fraction: float = 0.02
    transport_cost_per_kg: float = 0.08
    storage_cost_per_kg: float = 0.03
    electricity_price_per_kwh: float = 0.20


@dataclass(frozen=True, slots=True)
class ManufacturingCostResult:
    ingredient: IngredientCostBreakdown
    energy: EnergyCostResult
    labour_cost: float
    equipment_cost: float
    packaging_cost: float
    waste_cost: float
    transport_cost: float
    storage_cost: float
    total_cost: float
    batch_mass_kg: float
    cost_breakdown_pct: dict[str, float] = field(default_factory=dict)

    @property
    def cost_per_kg(self) -> float:
        return self.total_cost / self.batch_mass_kg if self.batch_mass_kg > 0 else 0.0


def manufacturing_cost(
    recipe: Recipe,
    pipeline_result: PipelineResult,
    rates: CostRates = CostRates(),
) -> ManufacturingCostResult:
    ingredient = ingredient_cost_breakdown(recipe)
    energy = flat_rate_cost(pipeline_result.final_state.cumulative_energy_j, rates.electricity_price_per_kwh)

    batch_mass = recipe.batch_mass_kg
    packaging = batch_mass * rates.packaging_cost_per_kg
    transport = batch_mass * rates.transport_cost_per_kg
    storage = batch_mass * rates.storage_cost_per_kg
    subtotal = (
        ingredient.total_cost
        + energy.total_cost
        + rates.labour_cost_per_batch
        + rates.equipment_cost_per_batch
        + packaging
        + transport
        + storage
    )
    waste = subtotal * rates.waste_fraction
    total = subtotal + waste

    breakdown = {
        "ingredients": 100 * ingredient.total_cost / total if total else 0.0,
        "energy": 100 * energy.total_cost / total if total else 0.0,
        "labour": 100 * rates.labour_cost_per_batch / total if total else 0.0,
        "equipment": 100 * rates.equipment_cost_per_batch / total if total else 0.0,
        "packaging": 100 * packaging / total if total else 0.0,
        "transport": 100 * transport / total if total else 0.0,
        "storage": 100 * storage / total if total else 0.0,
        "waste": 100 * waste / total if total else 0.0,
    }

    return ManufacturingCostResult(
        ingredient=ingredient,
        energy=energy,
        labour_cost=rates.labour_cost_per_batch,
        equipment_cost=rates.equipment_cost_per_batch,
        packaging_cost=packaging,
        waste_cost=waste,
        transport_cost=transport,
        storage_cost=storage,
        total_cost=total,
        batch_mass_kg=batch_mass,
        cost_breakdown_pct=breakdown,
    )
