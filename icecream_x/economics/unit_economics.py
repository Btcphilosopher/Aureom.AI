"""Unit economics: cost/margin per litre, per kg, and per retail unit."""

from __future__ import annotations

from dataclasses import dataclass

from icecream_x.economics.manufacturing_cost import ManufacturingCostResult


@dataclass(frozen=True, slots=True)
class UnitEconomicsResult:
    cost_per_kg: float
    cost_per_litre: float
    cost_per_unit: float
    selling_price_per_unit: float
    gross_margin_per_unit: float
    gross_margin_pct: float


def unit_economics(
    cost: ManufacturingCostResult,
    product_density_kg_m3: float,
    unit_volume_litres: float,
    selling_price_per_unit: float,
) -> UnitEconomicsResult:
    cost_per_kg = cost.cost_per_kg
    cost_per_litre = cost_per_kg * (product_density_kg_m3 / 1000.0)
    cost_per_unit = cost_per_litre * unit_volume_litres
    margin = selling_price_per_unit - cost_per_unit
    margin_pct = 100.0 * margin / selling_price_per_unit if selling_price_per_unit > 0 else 0.0
    return UnitEconomicsResult(
        cost_per_kg=cost_per_kg,
        cost_per_litre=cost_per_litre,
        cost_per_unit=cost_per_unit,
        selling_price_per_unit=selling_price_per_unit,
        gross_margin_per_unit=margin,
        gross_margin_pct=margin_pct,
    )
