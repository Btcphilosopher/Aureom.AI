"""Production-throughput analytics.

Estimates batch cycle time and line throughput from a
:class:`~icecream_x.core.engine.PipelineResult`, and how sensitive
throughput is to freezer/homogeniser settings -- the numbers
:mod:`icecream_x.optimisation.freezer_optimizer` and
:mod:`icecream_x.economics.unit_economics` build on for
cost-per-unit-time and capacity-planning questions.
"""

from __future__ import annotations

from dataclasses import dataclass

from icecream_x.core.engine import PipelineResult


@dataclass(frozen=True, slots=True)
class ProductionRateResult:
    cycle_time_s: float
    batch_mass_kg: float
    throughput_kg_per_hour: float
    throughput_litres_per_hour: float
    batches_per_shift: float


def production_rate(
    pipeline_result: PipelineResult,
    product_density_kg_m3: float,
    *,
    shift_duration_s: float = 8 * 3600.0,
) -> ProductionRateResult:
    cycle_time_s = pipeline_result.final_state.elapsed_time_s
    batch_mass_kg = pipeline_result.recipe.batch_mass_kg
    throughput_kg_per_hour = batch_mass_kg / (cycle_time_s / 3600.0) if cycle_time_s > 0 else 0.0
    throughput_litres_per_hour = throughput_kg_per_hour / (product_density_kg_m3 / 1000.0)
    batches_per_shift = shift_duration_s / cycle_time_s if cycle_time_s > 0 else 0.0

    return ProductionRateResult(
        cycle_time_s=cycle_time_s,
        batch_mass_kg=batch_mass_kg,
        throughput_kg_per_hour=throughput_kg_per_hour,
        throughput_litres_per_hour=throughput_litres_per_hour,
        batches_per_shift=batches_per_shift,
    )
