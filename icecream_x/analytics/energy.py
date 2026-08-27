"""Energy consumption analytics for a production-line run.

Breaks the total energy recorded on the final
:class:`~icecream_x.core.state.ProductState` down by process stage (using
each stage's own result object from
:class:`~icecream_x.core.engine.PipelineResult`), and expresses it per
batch, per litre, and per kilogram.
"""

from __future__ import annotations

from dataclasses import dataclass

from icecream_x.core.engine import PipelineResult


@dataclass(frozen=True, slots=True)
class EnergyBreakdown:
    heating_kwh: float
    homogenisation_kwh: float
    freezing_kwh: float
    hardening_kwh: float
    total_kwh: float
    kwh_per_kg: float
    kwh_per_litre: float


def energy_breakdown(pipeline_result: PipelineResult, product_density_kg_m3: float) -> EnergyBreakdown:
    heating_j = max(pipeline_result.pasteurisation.heating_energy_j, 0.0)
    homogenisation_j = (
        pipeline_result.homogenised_state.cumulative_energy_j
        - pipeline_result.pasteurisation.final_state.cumulative_energy_j
    )
    freezing_j = pipeline_result.freezing.refrigeration_energy_j
    hardening_j = pipeline_result.hardening.refrigeration_energy_j

    total_j = pipeline_result.final_state.cumulative_energy_j
    batch_mass_kg = pipeline_result.recipe.batch_mass_kg

    def kwh(j: float) -> float:
        return j / 3_600_000.0

    total_kwh = kwh(total_j)
    kwh_per_kg = total_kwh / batch_mass_kg if batch_mass_kg > 0 else 0.0
    kwh_per_litre = kwh_per_kg * (product_density_kg_m3 / 1000.0)

    return EnergyBreakdown(
        heating_kwh=kwh(heating_j),
        homogenisation_kwh=kwh(homogenisation_j),
        freezing_kwh=kwh(freezing_j),
        hardening_kwh=kwh(hardening_j),
        total_kwh=total_kwh,
        kwh_per_kg=kwh_per_kg,
        kwh_per_litre=kwh_per_litre,
    )
