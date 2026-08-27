"""Freezer-specific optimisation: throughput vs. quality trade-off.

The scraped-surface freezer is usually the production-rate bottleneck:
running it faster (higher ``design_throughput_kg_s``) increases line
throughput but shortens barrel residence time, which (via
:mod:`icecream_x.processing.freezing`) tends to leave the product less
frozen/less developed at the freezer outlet, pushing more of the ice
formation (and hence quality-determining crystal nucleation) onto the
hardening tunnel where crystals grow larger. This module exposes that
trade-off directly via :func:`throughput_quality_pareto_front` and a
constrained single-objective variant,
:func:`maximise_throughput_with_quality_floor`.
"""

from __future__ import annotations

from icecream_x.analytics.production import production_rate
from icecream_x.analytics.quality import QualityWeights, quality_score
from icecream_x.core.engine import PipelineResult, ProcessProfile
from icecream_x.formulation.recipe import Recipe
from icecream_x.optimisation.process_optimizer import (
    OptimisationResult,
    ParameterSpec,
    optimise_process,
    pareto_front,
)

QUALITY_SHORTFALL_PENALTY_PER_POINT = 50.0  # kg/h-equivalent penalty units


def _throughput(result: PipelineResult) -> float:
    density = result.final_state.product_density_kg_m3()
    return production_rate(result, density).throughput_kg_per_hour


def _quality(weights: QualityWeights):
    def f(result: PipelineResult) -> float:
        return quality_score(result.final_state, weights).overall_score

    return f


def maximise_throughput_with_quality_floor(
    recipe: Recipe,
    base_profile: ProcessProfile,
    parameters: list[ParameterSpec],
    *,
    minimum_quality_score: float = 60.0,
    quality_weights: QualityWeights = QualityWeights(),
    max_iterations: int = 100,
) -> OptimisationResult:
    quality_fn = _quality(quality_weights)

    def objective(result: PipelineResult) -> float:
        throughput = _throughput(result)
        q = quality_fn(result)
        shortfall = max(minimum_quality_score - q, 0.0)
        return throughput - shortfall * QUALITY_SHORTFALL_PENALTY_PER_POINT

    return optimise_process(
        recipe, base_profile, parameters, objective, maximise=True, max_iterations=max_iterations
    )


def throughput_quality_pareto_front(
    recipe: Recipe,
    base_profile: ProcessProfile,
    parameters: list[ParameterSpec],
    *,
    quality_weights: QualityWeights = QualityWeights(),
    n_weight_samples: int = 9,
) -> list[dict[str, float]]:
    return pareto_front(
        recipe,
        base_profile,
        parameters,
        objectives=[
            ("throughput_kg_per_hour", _throughput, True),
            ("quality_score", _quality(quality_weights), True),
        ],
        n_weight_samples=n_weight_samples,
    )
