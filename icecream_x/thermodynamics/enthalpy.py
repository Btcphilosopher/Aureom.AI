"""Apparent specific heat and enthalpy, including latent heat of freezing.

This module combines the sensible-heat mixture model
(:mod:`icecream_x.thermodynamics.heat_capacity`) with the ice-fraction
model (:mod:`icecream_x.thermodynamics.ice_fraction`) using the
*apparent specific heat method* standard in food-freezing engineering
(see e.g. Pham, 1987): near the freezing curve, a temperature increase
both heats the mix sensibly *and* melts some ice, absorbing latent heat.
The two effects are combined into a single apparent ``cp(T)`` that spikes
around the freezing point, then integrated to obtain enthalpy relative to
a reference temperature.

    cp_apparent(T) = cp_sensible(T) + L_f * d(unfrozen_water_kg)/dT / total_mass_kg

``d(unfrozen_water_kg)/dT`` is obtained analytically (see
:mod:`icecream_x.thermodynamics.ice_fraction`), avoiding the numerical
noise of a finite-difference derivative and keeping the model
numerically stable for small timesteps.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.integrate import cumulative_trapezoid, quad

from icecream_x.formulation.composition import Composition
from icecream_x.thermodynamics.heat_capacity import mixture_specific_heat_j_kg_k
from icecream_x.thermodynamics.ice_fraction import (
    d_unfrozen_water_d_temperature,
    phase_state_at_temperature,
)
from icecream_x.thermodynamics.latent_heat import LATENT_HEAT_FUSION_WATER_J_KG


def apparent_specific_heat_j_kg_k(composition: Composition, temperature_k: float) -> float:
    """Apparent (sensible + latent) specific heat at a given temperature."""
    if composition.total_mass_kg <= 0:
        raise ValueError("Cannot compute specific heat of an empty composition")

    from icecream_x.thermodynamics.freezing_point import (
        initial_freezing_point_k,
        total_colligative_solute_moles,
    )

    temp_c = temperature_k - 273.15
    state = phase_state_at_temperature(composition, temperature_k)
    cp_sensible = mixture_specific_heat_j_kg_k(
        composition, temp_c, state.unfrozen_water_kg, state.ice_kg
    )

    tf0 = initial_freezing_point_k(composition) if composition.water_kg > 0 else 0.0
    solute_moles = total_colligative_solute_moles(composition)
    d_unfrozen_dT = d_unfrozen_water_d_temperature(temperature_k, solute_moles, tf0)
    latent_term = LATENT_HEAT_FUSION_WATER_J_KG * d_unfrozen_dT / composition.total_mass_kg
    return cp_sensible + latent_term


@dataclass(frozen=True, slots=True)
class EnthalpyResult:
    reference_temperature_k: float
    temperature_k: float
    specific_enthalpy_j_kg: float
    total_enthalpy_j: float


def specific_enthalpy_j_kg(
    composition: Composition, temperature_k: float, reference_temperature_k: float
) -> float:
    """Specific enthalpy (J/kg of mix) relative to ``reference_temperature_k``.

    Computed by numerically integrating the apparent specific heat, which
    correctly folds in the latent heat released/absorbed as ice
    melts/forms between the reference and target temperatures.
    """
    if temperature_k == reference_temperature_k:
        return 0.0

    def integrand(t_k: float) -> float:
        return apparent_specific_heat_j_kg_k(composition, t_k)

    value, _abserr = quad(
        integrand, reference_temperature_k, temperature_k, limit=200, epsabs=1e-3
    )
    return value


def enthalpy_state(
    composition: Composition, temperature_k: float, reference_temperature_k: float
) -> EnthalpyResult:
    h_specific = specific_enthalpy_j_kg(composition, temperature_k, reference_temperature_k)
    return EnthalpyResult(
        reference_temperature_k=reference_temperature_k,
        temperature_k=temperature_k,
        specific_enthalpy_j_kg=h_specific,
        total_enthalpy_j=h_specific * composition.total_mass_kg,
    )


def temperature_from_enthalpy_k(
    composition: Composition,
    target_specific_enthalpy_j_kg: float,
    reference_temperature_k: float,
    *,
    search_bounds_k: tuple[float, float] = (203.15, 353.15),
) -> float:
    """Invert the enthalpy relationship to find T for a given specific enthalpy.

    Uses bisection (`scipy.optimize.brentq`) since ``specific_enthalpy_j_kg``
    is monotonically increasing in temperature (apparent cp > 0 everywhere).
    """
    from scipy.optimize import brentq

    def f(t_k: float) -> float:
        return (
            specific_enthalpy_j_kg(composition, t_k, reference_temperature_k)
            - target_specific_enthalpy_j_kg
        )

    lo, hi = search_bounds_k
    return brentq(f, lo, hi, xtol=1e-6)


class EnthalpyTable:
    """A pre-tabulated, interpolated H(T) relationship for one composition.

    :func:`specific_enthalpy_j_kg` (quad-based) integrates the apparent
    specific heat fresh on every call, which is correct but wasteful --
    and numerically fiddly -- when a process step needs thousands of
    repeated (composition-fixed) enthalpy/temperature look-ups in a tight
    timestep loop (e.g. :mod:`icecream_x.processing.freezing`). This
    class instead integrates the apparent specific heat *once* over a
    fine temperature grid (cumulative trapezoidal rule, via
    ``scipy.integrate.cumulative_trapezoid``) and serves all subsequent
    queries via fast monotonic linear interpolation -- both
    ``specific_enthalpy_j_kg`` and its inverse, since H(T) is monotonic
    (apparent cp > 0 everywhere).
    """

    def __init__(
        self,
        composition: Composition,
        reference_temperature_k: float,
        *,
        t_min_k: float = 203.15,
        t_max_k: float = 353.15,
        n_points: int = 3000,
    ) -> None:
        if not (t_min_k < reference_temperature_k < t_max_k):
            raise ValueError("reference_temperature_k must lie within [t_min_k, t_max_k]")
        self.composition = composition
        self.reference_temperature_k = reference_temperature_k
        temps = np.linspace(t_min_k, t_max_k, n_points)
        cps = np.array([apparent_specific_heat_j_kg_k(composition, float(t)) for t in temps])
        cumulative_h = cumulative_trapezoid(cps, temps, initial=0.0)
        h_at_reference = float(np.interp(reference_temperature_k, temps, cumulative_h))
        self._temps = temps
        self._h = cumulative_h - h_at_reference

    def specific_enthalpy_j_kg(self, temperature_k: float) -> float:
        return float(np.interp(temperature_k, self._temps, self._h))

    def temperature_from_enthalpy_k(self, specific_enthalpy_j_kg: float) -> float:
        return float(np.interp(specific_enthalpy_j_kg, self._h, self._temps))
