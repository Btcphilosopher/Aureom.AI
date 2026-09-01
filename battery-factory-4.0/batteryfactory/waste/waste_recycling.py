"""Waste & scrap engine and recycling model (spec items 37-38)."""
from __future__ import annotations

from dataclasses import dataclass

from batteryfactory.simulation.des_engine import FactorySimulationResult


@dataclass
class WasteSummary:
    total_scrap_units: int
    scrap_rate_pct: float
    material_cost_lost: float
    recoverable_material_value: float


class WasteTracker:
    def summarise(self, result: FactorySimulationResult, avg_material_cost_per_cell: float) -> WasteSummary:
        completed = sum(s.completed_units for s in result.stage_stats.values() if s is not result.stage_stats.get("shipping"))
        scrap = sum(s.scrapped_units for s in result.stage_stats.values())
        throughput = completed + scrap
        scrap_rate_pct = 100.0 * scrap / throughput if throughput else 0.0
        material_cost_lost = scrap * avg_material_cost_per_cell
        return WasteSummary(
            total_scrap_units=scrap,
            scrap_rate_pct=scrap_rate_pct,
            material_cost_lost=material_cost_lost,
            recoverable_material_value=material_cost_lost * RecyclingModel.DEFAULT_RECOVERY_RATE,
        )


@dataclass
class RecyclingFlow:
    input_failed_cells: int
    recovered_material_kg: dict[str, float]
    recovered_value: float
    virgin_material_offset_pct: float


class RecyclingModel:
    """FAILED CELLS -> DISASSEMBLY -> MATERIAL RECOVERY -> RECOVERED MATERIAL -> FACTORY INPUT."""

    DEFAULT_RECOVERY_RATE = 0.85  # blended value-recovery rate across materials

    RECOVERY_RATE_BY_MATERIAL = {
        "copper_foil": 0.95,
        "aluminium_foil": 0.90,
        "lithium_iron_phosphate": 0.80,
        "graphite": 0.60,
        "electrolyte": 0.20,
        "casing": 0.90,
    }

    def process(self, failed_cells: int, material_kg_per_cell: dict[str, float], material_unit_cost: dict[str, float]) -> RecyclingFlow:
        recovered_kg: dict[str, float] = {}
        recovered_value = 0.0
        for material, kg_per_cell in material_kg_per_cell.items():
            rate = self.RECOVERY_RATE_BY_MATERIAL.get(material, 0.5)
            recovered = failed_cells * kg_per_cell * rate
            recovered_kg[material] = recovered
            recovered_value += recovered * material_unit_cost.get(material, 0.0)

        total_input_material_kg = failed_cells * sum(material_kg_per_cell.values())
        total_recovered_kg = sum(recovered_kg.values())
        virgin_offset_pct = 100.0 * total_recovered_kg / total_input_material_kg if total_input_material_kg else 0.0

        return RecyclingFlow(
            input_failed_cells=failed_cells,
            recovered_material_kg=recovered_kg,
            recovered_value=recovered_value,
            virgin_material_offset_pct=virgin_offset_pct,
        )
