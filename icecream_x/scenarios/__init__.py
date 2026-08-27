"""Scenario library: example recipes, process profiles, storage profiles, and experiments."""

from __future__ import annotations

from icecream_x.scenarios.experiments import (
    EXPERIMENT_LIBRARY,
    Experiment,
    ExperimentComparison,
    run_experiment,
)
from icecream_x.scenarios.processing_profiles import PROCESSING_PROFILE_LIBRARY
from icecream_x.scenarios.recipes import RECIPE_LIBRARY
from icecream_x.scenarios.storage_profiles import STORAGE_PROFILE_LIBRARY

__all__ = [
    "RECIPE_LIBRARY",
    "PROCESSING_PROFILE_LIBRARY",
    "STORAGE_PROFILE_LIBRARY",
    "EXPERIMENT_LIBRARY",
    "Experiment",
    "ExperimentComparison",
    "run_experiment",
]
