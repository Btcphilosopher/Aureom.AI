"""Time-integration primitives shared across processing steps.

The key numerical-stability decision in ICECREAM-X is that temperature is
never integrated directly via ``dT/dt = Q / (m * cp)``. Near the freezing
point, the *apparent* specific heat spikes sharply (see
:mod:`icecream_x.thermodynamics.enthalpy`) as latent heat is
absorbed/released, which makes a direct temperature ODE numerically stiff
and step-size sensitive right in the most physically important region.

Instead, every thermal process step integrates **specific enthalpy**,
which is a smooth, monotonic function of both time (for a fixed heat
input) and temperature. Temperature is recovered by inverting the
enthalpy relationship (root-finding) only when a temperature value is
actually needed for output or for evaluating temperature-dependent
properties (heat-transfer coefficients, viscosity, ...). This is the
standard "enthalpy method" used in food/materials freezing simulation
precisely because it remains stable across phase transitions without
requiring adaptive step-size control.
"""

from __future__ import annotations

from dataclasses import dataclass

from icecream_x.formulation.composition import Composition
from icecream_x.thermodynamics.enthalpy import (
    EnthalpyTable,
    specific_enthalpy_j_kg,
    temperature_from_enthalpy_k,
)


@dataclass(frozen=True, slots=True)
class EnthalpyStepResult:
    temperature_k: float
    specific_enthalpy_j_kg: float
    heat_added_j: float


def enthalpy_step(
    composition: Composition,
    current_temperature_k: float,
    heat_rate_w: float,
    mass_kg: float,
    dt_s: float,
    reference_temperature_k: float,
    *,
    search_bounds_k: tuple[float, float] = (203.15, 353.15),
    table: EnthalpyTable | None = None,
) -> EnthalpyStepResult:
    """Advance one explicit enthalpy-method timestep.

    ``heat_rate_w`` is the net heat flow *into* the product (positive =
    heating, negative = cooling), evaluated at the start of the step
    (explicit/forward Euler in enthalpy space).

    Pass a pre-built :class:`~icecream_x.thermodynamics.enthalpy.EnthalpyTable`
    via ``table`` when calling this repeatedly for the same composition in a
    tight loop (e.g. a process-step time-stepping loop) -- it replaces the
    per-call numerical integration/root-find with fast interpolation.
    """
    if mass_kg <= 0:
        raise ValueError("mass_kg must be > 0")
    if dt_s < 0:
        raise ValueError("dt_s must be >= 0")

    heat_added_j = heat_rate_w * dt_s
    if table is not None:
        h_current = table.specific_enthalpy_j_kg(current_temperature_k)
        h_new = h_current + heat_added_j / mass_kg
        t_new = table.temperature_from_enthalpy_k(h_new)
    else:
        h_current = specific_enthalpy_j_kg(composition, current_temperature_k, reference_temperature_k)
        h_new = h_current + heat_added_j / mass_kg
        t_new = temperature_from_enthalpy_k(
            composition, h_new, reference_temperature_k, search_bounds_k=search_bounds_k
        )
    return EnthalpyStepResult(temperature_k=t_new, specific_enthalpy_j_kg=h_new, heat_added_j=heat_added_j)


def time_grid(total_duration_s: float, dt_s: float) -> list[float]:
    """A list of time offsets [0, dt, 2*dt, ..., total_duration_s]."""
    if total_duration_s < 0 or dt_s <= 0:
        raise ValueError("total_duration_s must be >= 0 and dt_s must be > 0")
    n_steps = max(int(total_duration_s // dt_s), 0)
    grid = [i * dt_s for i in range(n_steps + 1)]
    if grid[-1] < total_duration_s - 1e-9:
        grid.append(total_duration_s)
    return grid
