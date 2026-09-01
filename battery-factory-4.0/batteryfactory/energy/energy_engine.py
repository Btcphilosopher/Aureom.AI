"""Energy digital twin (spec item 24): per-category metering and KPIs."""
from __future__ import annotations

from dataclasses import dataclass, field

from batteryfactory.config.chemistry_profiles import ChemistryProfile
from batteryfactory.simulation.des_engine import FactorySimulationResult


@dataclass
class EnergyBreakdown:
    electricity_kwh: float = 0.0
    hvac_dry_room_kwh: float = 0.0
    formation_kwh: float = 0.0
    compressed_air_kwh: float = 0.0
    other_machine_kwh: float = 0.0

    @property
    def total_kwh(self) -> float:
        return (self.electricity_kwh + self.hvac_dry_room_kwh + self.formation_kwh
                + self.compressed_air_kwh + self.other_machine_kwh)


@dataclass
class EnergyKPIs:
    kwh_per_cell: float
    kwh_per_kwh_produced: float
    kwh_per_pack: float
    total_factory_kwh: float
    breakdown: EnergyBreakdown


class EnergyDigitalTwin:
    def compute_breakdown(self, result: FactorySimulationResult, dry_room_kwh: float = 0.0, compressed_air_kwh: float = 0.0) -> EnergyBreakdown:
        formation_kwh = result.stage_stats["formation"].energy_kwh
        other = sum(s.energy_kwh for name, s in result.stage_stats.items() if name != "formation")
        return EnergyBreakdown(
            electricity_kwh=other + formation_kwh,
            hvac_dry_room_kwh=dry_room_kwh,
            formation_kwh=formation_kwh,
            compressed_air_kwh=compressed_air_kwh,
            other_machine_kwh=other,
        )

    def compute_kpis(self, result: FactorySimulationResult, profile: ChemistryProfile, breakdown: EnergyBreakdown | None = None) -> EnergyKPIs:
        breakdown = breakdown or self.compute_breakdown(result)
        total = breakdown.total_kwh
        cells = max(result.cells_completed, 1)
        packs = max(result.packs_completed, 1) if result.packs_completed else 0

        kwh_per_cell = total / cells
        cell_energy_kwh = profile.capacity_ah_reference * profile.nominal_voltage_v / 1000.0
        kwh_per_kwh_produced = total / (cells * cell_energy_kwh) if cell_energy_kwh > 0 else 0.0
        kwh_per_pack = total / packs if packs > 0 else 0.0

        return EnergyKPIs(
            kwh_per_cell=kwh_per_cell,
            kwh_per_kwh_produced=kwh_per_kwh_produced,
            kwh_per_pack=kwh_per_pack,
            total_factory_kwh=total,
            breakdown=breakdown,
        )
