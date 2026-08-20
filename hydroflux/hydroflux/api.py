"""
The public HydroFlux API (specification section 51):

    result = hydroflux.simulate(system, resource_data)
    result = hydroflux.optimize(system, resource_data, constraints, objective="max_revenue")
    table  = hydroflux.compare(scenarios)

Everything here is a thin, documented wrapper over
:class:`hydroflux.core.engine.HydroFluxEngine` -- use the engine directly
for more control (custom policies, inspecting intermediate results).
"""

from __future__ import annotations

from typing import Any, Optional, Union

import pandas as pd

from hydroflux.core.config import HydroSystemConfig
from hydroflux.core.engine import HydroFluxEngine
from hydroflux.core.safety import HardConstraints, SafetyGovernor
from hydroflux.core.timeseries import ResourceTimeSeries
from hydroflux.optimisation.objectives import ObjectiveWeights
from hydroflux.reporting.reporting import ComparisonEngine, SimulationResult


def simulate(
    system: HydroSystemConfig,
    resource_data: ResourceTimeSeries,
    policy: Optional[dict] = None,
    scenario_name: str = "baseline",
) -> SimulationResult:
    """Run a single simulation pass with a given (or default) operating
    policy. Use this to evaluate a specific, already-decided operating
    strategy; use :func:`optimize` to search for the best one."""

    engine = HydroFluxEngine(system)
    return engine.simulate(resource_data, policy=policy, scenario_name=scenario_name)


def optimize(
    system: HydroSystemConfig,
    resource_data: ResourceTimeSeries,
    constraints: Optional[HardConstraints] = None,
    objective: str = "max_revenue",
    weights: Optional[ObjectiveWeights] = None,
    algorithm: str = "differential_evolution",
    seed: Optional[int] = None,
    **algorithm_kwargs,
) -> SimulationResult:
    """Search for the operating policy that maximises ``objective`` (or a
    custom weighted combination via ``weights``), then return the fully
    simulated result for the best policy found.

    ``constraints``, if supplied, is a :class:`HardConstraints` safety
    envelope. The optimiser itself is never restricted by it -- it searches
    the full physical/economic space (the OPTIMAL) -- but the returned
    result is checked against it afterwards via :class:`SafetyGovernor`,
    and any peak-generation / reservoir-level constraint that the optimum
    would have violated is recorded in ``constraint_violations`` so callers
    can see exactly where OPTIMAL and PERMITTED diverge (see specification
    sections 41 and 52).
    """

    engine = HydroFluxEngine(system)
    result, policy_result = engine.optimise(
        resource_data, objective=objective, weights=weights, algorithm=algorithm, seed=seed, **algorithm_kwargs
    )

    if constraints is not None:
        governor = SafetyGovernor(constraints)
        checks = [
            {"power_mw": result.peak_generation_mw, "rated_power_mw": system.rated_power_mw},
        ]
        if result.reservoir_level_m is not None and len(result.reservoir_level_m):
            checks.append({"reservoir_level_m": float(result.reservoir_level_m.max())})
            checks.append({"reservoir_level_m": float(result.reservoir_level_m.min())})
        for request in checks:
            permitted = governor.enforce(request)
            if permitted.was_clipped:
                result.constraint_violations.append(
                    f"safety governor: {permitted.violated_constraints} on {request} -> {permitted.permitted}"
                )

    return result


def compare(scenarios: dict[str, Union[SimulationResult, dict[str, Any]]]) -> pd.DataFrame:
    """Compare multiple named scenarios. Each value in ``scenarios`` is
    either an already-computed :class:`SimulationResult`, or a dict with
    ``{"system": HydroSystemConfig, "resource_data": ResourceTimeSeries,
    "policy": Optional[dict]}`` to simulate on the fly."""

    results: dict[str, SimulationResult] = {}
    for name, value in scenarios.items():
        if isinstance(value, SimulationResult):
            results[name] = value
        elif isinstance(value, dict):
            engine = HydroFluxEngine(value["system"])
            results[name] = engine.simulate(value["resource_data"], policy=value.get("policy"), scenario_name=name)
        else:
            raise TypeError(f"compare() scenario '{name}' must be a SimulationResult or a dict, got {type(value)}")

    return ComparisonEngine.compare(results)
