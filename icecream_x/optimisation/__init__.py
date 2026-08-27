"""Optimisation engine: formulation, process, freezer, energy, and quality optimisation."""

from __future__ import annotations

from icecream_x.optimisation.energy_optimizer import minimise_energy
from icecream_x.optimisation.formulation_optimizer import (
    FormulationOptimisationResult,
    IngredientBound,
    optimise_formulation,
)
from icecream_x.optimisation.freezer_optimizer import (
    maximise_throughput_with_quality_floor,
    throughput_quality_pareto_front,
)
from icecream_x.optimisation.process_optimizer import (
    OptimisationResult,
    ParameterSpec,
    optimise_process,
    pareto_front,
)
from icecream_x.optimisation.quality_optimizer import maximise_quality

__all__ = [
    "minimise_energy",
    "FormulationOptimisationResult",
    "IngredientBound",
    "optimise_formulation",
    "maximise_throughput_with_quality_floor",
    "throughput_quality_pareto_front",
    "OptimisationResult",
    "ParameterSpec",
    "optimise_process",
    "pareto_front",
    "maximise_quality",
]
