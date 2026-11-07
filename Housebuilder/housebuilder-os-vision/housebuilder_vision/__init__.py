"""Aureom.AI Housebuilder.OS Vision - image evidence to an editable building twin, quantities and costs.

A conceptual reconstruction tool: photos, renders and elevation drawings become an
editable parametric building model with labelled provenance (observed / inferred /
user-confirmed / assumed / unknown), a traceable bill of quantities, layered cost
estimates, digital simulations and an uncertainty simulation.  It is not a measured
survey, not construction-ready BIM and makes no compliance, structural-adequacy or
certified energy claims.

The pipeline functions are importable from the package root (loaded lazily, so
``import housebuilder_vision`` stays light)::

    from housebuilder_vision import run_pipeline, simulate_uncertainty, __version__
"""

from __future__ import annotations

from typing import Any

__version__ = "0.1.0"

#: Names re-exported lazily from :mod:`housebuilder_vision.pipeline`.
_PIPELINE_EXPORTS = (
    "analyse_images",
    "generate_geometry_hypotheses",
    "calibrate_scale",
    "build_parametric_twin",
    "apply_construction_assemblies",
    "calculate_quantities",
    "estimate_construction_cost",
    "calculate_incremental_cost",
    "simulate_uncertainty",
    "compare_build_scenarios",
    "export_project",
    "run_digital_simulations",
    "run_pipeline",
    "PipelineResult",
    "ENGINE_FUNCTIONS",
)

__all__ = ["__version__", *_PIPELINE_EXPORTS]


def __getattr__(name: str) -> Any:
    if name in _PIPELINE_EXPORTS:
        from . import pipeline

        value = getattr(pipeline, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module 'housebuilder_vision' has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_PIPELINE_EXPORTS))
