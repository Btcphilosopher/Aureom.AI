"""Electrode slurry mixing process model (spec item 8)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class MixingRecipe:
    active_material_pct: float
    binder_pct: float
    conductive_additive_pct: float
    solvent_pct: float
    mixing_time_min: float
    temperature_c: float
    target_viscosity_cp: float

    def validate(self) -> bool:
        total_solids = self.active_material_pct + self.binder_pct + self.conductive_additive_pct
        return abs(total_solids + self.solvent_pct - 100.0) < 1.0


@dataclass
class MixingBatchResult:
    batch_size_kg: float
    actual_viscosity_cp: float
    quality_score: float          # 0..1, distance from target viscosity + mix time adequacy
    energy_kwh: float
    cycle_time_min: float
    yield_pct: float


class MixingProcess:
    """A planetary/high-shear mixer digital twin."""

    def __init__(self, rated_power_kw: float = 45.0, rng: np.random.Generator | None = None) -> None:
        self.rated_power_kw = rated_power_kw
        self.rng = rng or np.random.default_rng()

    def run(self, recipe: MixingRecipe, batch_size_kg: float) -> MixingBatchResult:
        # Viscosity responds to mix time/temperature around the target with process
        # noise. 90 minutes is the neutral (time_factor=1.0) point: a typical
        # planetary-mixer dwell time for a gigafactory-scale slurry batch.
        time_factor = np.clip(recipe.mixing_time_min / 90.0, 0.4, 1.6)
        temp_factor = 1.0 + (recipe.temperature_c - 25.0) * -0.004
        noise = self.rng.normal(1.0, 0.04)
        actual_viscosity = recipe.target_viscosity_cp * time_factor * temp_factor * noise

        viscosity_error = abs(actual_viscosity - recipe.target_viscosity_cp) / recipe.target_viscosity_cp
        quality_score = float(np.clip(1.0 - viscosity_error * 2.0, 0.0, 1.0))

        cycle_time = recipe.mixing_time_min * self.rng.normal(1.0, 0.03)
        energy_kwh = self.rated_power_kw * (cycle_time / 60.0)
        # Under-mixed or over-thin batches lose yield to rework/scrap downstream.
        yield_pct = float(np.clip(96.0 - viscosity_error * 40.0 + self.rng.normal(0, 0.5), 70.0, 99.5))

        return MixingBatchResult(
            batch_size_kg=batch_size_kg,
            actual_viscosity_cp=float(actual_viscosity),
            quality_score=quality_score,
            energy_kwh=float(energy_kwh),
            cycle_time_min=float(cycle_time),
            yield_pct=yield_pct,
        )
