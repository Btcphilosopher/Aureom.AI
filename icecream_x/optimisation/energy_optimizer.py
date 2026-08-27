"""Convenience wrapper: optimise process conditions to minimise energy consumption.

Supports an optional quality floor (minimum acceptable quality score) via
a penalty term, so the optimiser cannot simply run the freezer or
hardening tunnel to a barely-frozen, energy-cheap but unsellable product.
"""

from __future__ import annotations

from icecream_x.analytics.quality import QualityWeights, quality_score
from icecream_x.core.engine import PipelineResult, ProcessProfile
from icecream_x.formulation.recipe import Recipe
from icecream_x.optimisation.process_optimizer import (
    OptimisationResult,
    ParameterSpec,
    optimise_process,
)

#: Penalty applied per point of quality-score shortfall below the floor.
QUALITY_SHORTFALL_PENALTY_PER_POINT = 5.0  # kWh-equivalent penalty units


def minimise_energy(
    recipe: Recipe,
    base_profile: ProcessProfile,
    parameters: list[ParameterSpec],
    *,
    minimum_quality_score: float = 0.0,
    quality_weights: QualityWeights = QualityWeights(),
    max_iterations: int = 100,
) -> OptimisationResult:
    def objective(result: PipelineResult) -> float:
        energy_kwh = result.final_state.cumulative_energy_j / 3_600_000.0
        if minimum_quality_score > 0:
            q = quality_score(result.final_state, quality_weights).overall_score
            shortfall = max(minimum_quality_score - q, 0.0)
            energy_kwh += shortfall * QUALITY_SHORTFALL_PENALTY_PER_POINT
        return -energy_kwh  # optimise_process maximises; we want to minimise energy

    return optimise_process(
        recipe, base_profile, parameters, objective, maximise=True, max_iterations=max_iterations
    )
