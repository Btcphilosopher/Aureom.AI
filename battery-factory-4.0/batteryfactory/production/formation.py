"""Formation & aging simulation (spec item 13), configurable recipes."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from batteryfactory.config.chemistry_profiles import ChemistryProfile
from batteryfactory.datamodel.models import Cell, next_serial


@dataclass
class FormationRecipe:
    num_cycles: int = 3
    charge_c_rate: float = 0.1
    discharge_c_rate: float = 0.2
    rest_time_min: float = 30.0
    target_temp_c: float = 25.0


@dataclass
class FormationResult:
    formation_batch_id: str
    formation_capacity_ah: float
    coulombic_efficiency_pct: float
    energy_charge_kwh: float
    energy_discharge_kwh: float
    duration_hr: float
    max_temp_c: float
    gas_generation_flag: bool
    passed: bool


class FormationLine:
    """Charges/discharges each cell through its formation recipe (SEI build)."""

    def __init__(self, rng: np.random.Generator | None = None) -> None:
        self.rng = rng or np.random.default_rng()

    def run(self, cell: Cell, profile: ChemistryProfile, recipe: FormationRecipe) -> FormationResult:
        batch_id = next_serial("FORM")
        vmin, vmax = profile.formation_voltage_window_v
        nominal_capacity = profile.capacity_ah_reference

        # Coulombic efficiency improves with more, gentler formation cycles.
        base_ce = 92.0 + min(recipe.num_cycles, 5) * 1.2 - recipe.charge_c_rate * 3.0
        coulombic_efficiency = float(np.clip(self.rng.normal(base_ce, 0.6), 80.0, 99.9))

        capacity_yield = coulombic_efficiency / 100.0
        formation_capacity = float(nominal_capacity * capacity_yield * self.rng.normal(1.0, 0.01))

        charge_time_hr = recipe.num_cycles * (1.0 / max(recipe.charge_c_rate, 1e-3))
        discharge_time_hr = recipe.num_cycles * (1.0 / max(recipe.discharge_c_rate, 1e-3))
        rest_time_hr = recipe.num_cycles * recipe.rest_time_min / 60.0
        duration_hr = charge_time_hr + discharge_time_hr + rest_time_hr

        energy_charge_kwh = nominal_capacity * (vmax + vmin) / 2.0 / 1000.0 * recipe.num_cycles
        energy_discharge_kwh = energy_charge_kwh * capacity_yield

        temp_rise = recipe.charge_c_rate * 8.0 + recipe.discharge_c_rate * 5.0
        max_temp_c = float(recipe.target_temp_c + temp_rise + self.rng.normal(0, 0.5))

        gas_generation_flag = bool(max_temp_c > profile.target_operating_temp_c[1] + 15.0
                                     or self.rng.random() < 0.003)
        passed = (not gas_generation_flag) and coulombic_efficiency >= 90.0

        return FormationResult(
            formation_batch_id=batch_id,
            formation_capacity_ah=formation_capacity,
            coulombic_efficiency_pct=coulombic_efficiency,
            energy_charge_kwh=float(energy_charge_kwh),
            energy_discharge_kwh=float(energy_discharge_kwh),
            duration_hr=float(duration_hr),
            max_temp_c=max_temp_c,
            gas_generation_flag=gas_generation_flag,
            passed=passed,
        )
