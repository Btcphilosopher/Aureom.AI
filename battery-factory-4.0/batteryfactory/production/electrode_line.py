"""
Electrode manufacturing line (spec item 7): chains material preparation,
mixing, coating, drying, calendering, slitting, vacuum drying and electrode
storage into one throughput/yield/scrap-tracking pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from batteryfactory.datamodel.models import ElectrodeBatch, next_serial
from batteryfactory.production.calendering import CalenderingModel, CalenderingParameters
from batteryfactory.production.coating import CoatingMachine, CoatingParameters
from batteryfactory.production.mixing import MixingProcess, MixingRecipe


@dataclass
class ElectrodeLineConfig:
    electrode_type: str  # "anode" | "cathode"
    mixing_recipe: MixingRecipe
    coating_params: CoatingParameters
    calendering_params: CalenderingParameters
    slitting_scrap_pct: float = 1.5
    vacuum_drying_scrap_pct: float = 0.5


@dataclass
class ElectrodeLineResult:
    batch: ElectrodeBatch
    stage_throughput_m2_per_hr: float
    stage_yield_pct: float
    stage_scrap_pct: float
    stage_energy_kwh: float
    machine_utilisation_pct: dict[str, float]


class ElectrodeProductionLine:
    """MATERIAL PREP -> MIXING -> COATING -> DRYING -> CALENDERING -> SLITTING -> VACUUM DRY -> STORAGE."""

    def __init__(self, rng: np.random.Generator | None = None) -> None:
        self.rng = rng or np.random.default_rng()
        self.mixer = MixingProcess(rng=self.rng)
        self.coater = CoatingMachine(rng=self.rng)
        self.calender = CalenderingModel()
        self.stored_batches: list[ElectrodeBatch] = []

    def run_batch(self, config: ElectrodeLineConfig, batch_size_kg: float, material_batch_ids: list[str]) -> ElectrodeLineResult:
        mix = self.mixer.run(config.mixing_recipe, batch_size_kg)
        coat = self.coater.run(config.coating_params, slurry_quality_score=mix.quality_score)
        cal = self.calender.compute(config.calendering_params)

        yield_after_mixing = mix.yield_pct
        yield_after_coating = yield_after_mixing * (1 - coat.scrap_pct / 100.0)
        yield_after_slitting = yield_after_coating * (1 - config.slitting_scrap_pct / 100.0)
        final_yield_pct = yield_after_slitting * (1 - config.vacuum_drying_scrap_pct / 100.0)
        total_scrap_pct = 100.0 - final_yield_pct

        total_energy = mix.energy_kwh + coat.energy_kwh_per_hr  # coater energy already per-hr basis

        batch = ElectrodeBatch(
            batch_id=next_serial(f"ELEC-{config.electrode_type.upper()}"),
            electrode_type=config.electrode_type,
            material_batch_ids=material_batch_ids,
            thickness_um=cal.thickness_um,
            density_g_cc=cal.density_g_cc,
            coating_uniformity_std_pct=coat.thickness_uniformity_std_pct,
            yield_pct=final_yield_pct,
            scrap_pct=total_scrap_pct,
        )
        self.stored_batches.append(batch)

        utilisation = {
            "mixer": float(np.clip(mix.cycle_time_min / 60.0, 0.0, 1.0) * 100.0),
            "coater": float(np.clip(coat.throughput_m2_per_hr / (coat.throughput_m2_per_hr + 1e-6), 0.0, 1.0) * 100.0),
            "calender": 100.0,
        }

        return ElectrodeLineResult(
            batch=batch,
            stage_throughput_m2_per_hr=coat.throughput_m2_per_hr,
            stage_yield_pct=final_yield_pct,
            stage_scrap_pct=total_scrap_pct,
            stage_energy_kwh=total_energy,
            machine_utilisation_pct=utilisation,
        )
