"""
Safety architecture: HydroFlux is a decision-support and simulation system.

The optimiser is free to explore the full operating envelope in search of
the best economic or energy outcome, but its recommendations are never
executed directly. Every optimiser output passes through a
:class:`SafetyGovernor`, which clips or rejects anything that violates hard
engineering, environmental or grid limits and returns a
:class:`PermittedAction`. HydroFlux always keeps ``OPTIMAL`` and
``PERMITTED`` as two distinct concepts -- see
:class:`hydroflux.core.engine.GenerationPotential`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class HardConstraints:
    """Non-negotiable engineering / environmental / grid limits.

    These are never relaxed by the optimiser -- they represent dam safety,
    turbine protection, environmental licence conditions and grid
    protection limits that must hold regardless of the objective function.
    """

    max_reservoir_level_m: Optional[float] = None
    min_reservoir_level_m: Optional[float] = None
    max_turbine_flow_m3s: Optional[float] = None
    max_ramp_rate_mw_per_min: Optional[float] = None
    min_environmental_flow_m3s: float = 0.0
    max_grid_export_mw: Optional[float] = None
    turbine_overspeed_fraction: float = 1.4  # fraction of rated speed/flow that trips protection


@dataclass
class PermittedAction:
    """The result of running an optimiser's proposed action through the
    :class:`SafetyGovernor`."""

    requested: dict
    permitted: dict
    was_clipped: bool
    violated_constraints: list[str] = field(default_factory=list)


class SafetyGovernor:
    """Enforces :class:`HardConstraints` on optimiser output.

    ``enforce`` never raises for an out-of-envelope request -- it clips to
    the permitted envelope and records what was violated, so the caller
    (engine, dispatcher, digital twin) always has both the OPTIMAL value the
    optimiser wanted and the PERMITTED value it is safe to act on.
    """

    def __init__(self, constraints: HardConstraints):
        self.constraints = constraints

    def enforce(self, requested: dict) -> PermittedAction:
        permitted = dict(requested)
        violated: list[str] = []
        c = self.constraints

        flow = requested.get("flow_m3s")
        if flow is not None:
            if c.min_environmental_flow_m3s is not None and flow < c.min_environmental_flow_m3s:
                permitted["flow_m3s"] = c.min_environmental_flow_m3s
                violated.append("min_environmental_flow_m3s")
            if c.max_turbine_flow_m3s is not None and permitted["flow_m3s"] > c.max_turbine_flow_m3s:
                permitted["flow_m3s"] = c.max_turbine_flow_m3s
                violated.append("max_turbine_flow_m3s")

        level = requested.get("reservoir_level_m")
        if level is not None:
            if c.max_reservoir_level_m is not None and level > c.max_reservoir_level_m:
                permitted["reservoir_level_m"] = c.max_reservoir_level_m
                violated.append("max_reservoir_level_m")
            if c.min_reservoir_level_m is not None and permitted["reservoir_level_m"] < c.min_reservoir_level_m:
                permitted["reservoir_level_m"] = c.min_reservoir_level_m
                violated.append("min_reservoir_level_m")

        export = requested.get("export_mw")
        if export is not None and c.max_grid_export_mw is not None and export > c.max_grid_export_mw:
            permitted["export_mw"] = c.max_grid_export_mw
            violated.append("max_grid_export_mw")

        power = requested.get("power_mw")
        rated = requested.get("rated_power_mw")
        if power is not None and rated is not None:
            limit = rated * c.turbine_overspeed_fraction
            if power > limit:
                permitted["power_mw"] = limit
                violated.append("turbine_overspeed_fraction")

        return PermittedAction(
            requested=dict(requested),
            permitted=permitted,
            was_clipped=bool(violated),
            violated_constraints=violated,
        )
