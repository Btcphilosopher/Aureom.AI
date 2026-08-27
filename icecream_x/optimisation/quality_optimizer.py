"""Convenience wrapper: optimise process conditions purely for quality score."""

from __future__ import annotations

from icecream_x.analytics.quality import QualityWeights, quality_score
from icecream_x.core.engine import PipelineResult, ProcessProfile
from icecream_x.formulation.recipe import Recipe
from icecream_x.optimisation.process_optimizer import (
    OptimisationResult,
    ParameterSpec,
    optimise_process,
)


def _quality_objective(weights: QualityWeights) -> callable:
    def objective(result: PipelineResult) -> float:
        return quality_score(result.final_state, weights).overall_score

    return objective


def maximise_quality(
    recipe: Recipe,
    base_profile: ProcessProfile,
    parameters: list[ParameterSpec],
    *,
    weights: QualityWeights = QualityWeights(),
    max_iterations: int = 100,
) -> OptimisationResult:
    return optimise_process(
        recipe,
        base_profile,
        parameters,
        _quality_objective(weights),
        maximise=True,
        max_iterations=max_iterations,
    )
