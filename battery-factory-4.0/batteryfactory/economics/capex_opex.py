"""CAPEX and OPEX models (spec items 41-42)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CapexInputs:
    land: float
    buildings: float
    machinery: float
    automation: float
    utilities: float
    dry_rooms: float
    formation_equipment: float
    warehouses: float
    laboratories: float
    useful_life_years: float = 15.0

    @property
    def total_capex(self) -> float:
        return (self.land + self.buildings + self.machinery + self.automation + self.utilities
                + self.dry_rooms + self.formation_equipment + self.warehouses + self.laboratories)

    @property
    def annual_depreciation(self) -> float:
        # Land is not depreciated.
        depreciable = self.total_capex - self.land
        return depreciable / max(self.useful_life_years, 1e-6)

    def capital_intensity(self, annual_capacity_units: float) -> float:
        return self.total_capex / annual_capacity_units if annual_capacity_units > 0 else float("inf")

    def capacity_per_currency_invested(self, annual_capacity_units: float) -> float:
        return annual_capacity_units / self.total_capex if self.total_capex > 0 else 0.0


@dataclass
class OpexInputs:
    materials: float
    electricity: float
    labour: float
    maintenance: float
    logistics: float
    consumables: float
    waste: float

    @property
    def annual_opex(self) -> float:
        return self.materials + self.electricity + self.labour + self.maintenance + self.logistics + self.consumables + self.waste

    def cost_per_unit(self, annual_units: float) -> float:
        return self.annual_opex / annual_units if annual_units > 0 else float("inf")

    def cost_per_kwh(self, annual_kwh: float) -> float:
        return self.annual_opex / annual_kwh if annual_kwh > 0 else float("inf")
