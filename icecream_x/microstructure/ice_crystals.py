"""Ice-crystal population model.

**What this model is, and is not.** Real ice-crystal populations in ice
cream are polydisperse and their evolution involves coupled nucleation,
diffusion-limited growth, and Ostwald ripening (recrystallisation) that
would properly require a population-balance PDE. This module implements a
much simpler, explicitly empirical, single-parameter (mean diameter, plus
a distribution width) tracking model that reproduces the two
qualitative/semi-quantitative behaviours that matter most for process
decisions:

1. **Faster freezing => smaller initial crystals.** Rapid heat removal in
   the scraped-surface freezer creates many nucleation sites, so the
   available water freezes into many small crystals rather than a few
   large ones. Modelled as an inverse power law in freezing rate.
2. **Warmer / fluctuating storage => crystal growth (recrystallisation).**
   Above the recrystallisation threshold, water preferentially migrates
   from small crystals to large ones (Ostwald ripening) via classic
   Lifshitz-Slyozov-Wagner (LSW) cube-law kinetics, ``d^3(t) = d^3(0) + k*t``,
   accelerated by higher storage temperature (Arrhenius) and by
   temperature cycling (repeated partial melt/refreeze).

All rate constants below are representative, order-of-magnitude defaults
consistent with the qualitative literature trends (e.g. Hartel, *Ice
Crystallization During the Manufacture of Ice Cream*; Donhowe & Hartel,
1996 on recrystallisation kinetics) rather than a fit to a specific
plant's data. They are grouped at module level for straightforward
recalibration -- see :mod:`icecream_x.digital_twin.calibration`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

GAS_CONSTANT_J_PER_MOL_K = 8.314462618

# --- initial nucleation/growth in the freezer ---------------------------
NUCLEATION_SIZE_COEFFICIENT_UM = 55.0
NUCLEATION_SIZE_EXPONENT = 0.35
MIN_CRYSTAL_DIAMETER_UM = 5.0
DEFAULT_DISTRIBUTION_CV = 0.45  # coefficient of variation, dimensionless

# --- recrystallisation during storage ------------------------------------
#: LSW growth-rate constant at the reference temperature, um^3/s.
RECRYSTALLISATION_RATE_REF_UM3_S = 45.0
RECRYSTALLISATION_REFERENCE_TEMPERATURE_K = 258.15  # -15 degC
RECRYSTALLISATION_ACTIVATION_ENERGY_J_PER_MOL = 55_000.0
#: Extra growth-rate contribution per (K of cycling amplitude)^2, um^3/s.
CYCLING_GROWTH_COEFFICIENT_UM3_S_PER_K2 = 8.0


@dataclass(frozen=True, slots=True)
class IceCrystalState:
    mean_diameter_um: float
    distribution_cv: float = DEFAULT_DISTRIBUTION_CV

    @property
    def distribution_std_um(self) -> float:
        return self.mean_diameter_um * self.distribution_cv


def initial_crystal_state(freezing_rate_c_per_s: float) -> IceCrystalState:
    """Mean initial ice-crystal diameter as a function of freezing rate.

    ``freezing_rate_c_per_s`` should be the (positive) rate of temperature
    decrease through the active-freezing region of the freezer barrel.
    Faster freezing (larger rate) yields smaller crystals.
    """
    freezing_rate_c_per_min = max(freezing_rate_c_per_s, 1e-6) * 60.0
    diameter = NUCLEATION_SIZE_COEFFICIENT_UM * freezing_rate_c_per_min ** (
        -NUCLEATION_SIZE_EXPONENT
    )
    return IceCrystalState(mean_diameter_um=max(diameter, MIN_CRYSTAL_DIAMETER_UM))


def _recrystallisation_rate_um3_s(temperature_k: float, cycling_amplitude_k: float) -> float:
    arrhenius = math.exp(
        -(RECRYSTALLISATION_ACTIVATION_ENERGY_J_PER_MOL / GAS_CONSTANT_J_PER_MOL_K)
        * (1.0 / temperature_k - 1.0 / RECRYSTALLISATION_REFERENCE_TEMPERATURE_K)
    )
    base_rate = RECRYSTALLISATION_RATE_REF_UM3_S * arrhenius
    cycling_rate = CYCLING_GROWTH_COEFFICIENT_UM3_S_PER_K2 * cycling_amplitude_k**2
    return base_rate + cycling_rate


def grow_by_recrystallisation(
    state: IceCrystalState,
    temperature_k: float,
    duration_s: float,
    *,
    ice_mass_fraction: float,
    cycling_amplitude_k: float = 0.0,
) -> IceCrystalState:
    """Advance the crystal population by ``duration_s`` of storage at ``temperature_k``.

    Growth is suppressed (no driving force) when there is no ice present
    (``ice_mass_fraction <= 0``, i.e. the product is not actually frozen).
    """
    if duration_s < 0:
        raise ValueError("duration_s must be >= 0")
    if ice_mass_fraction <= 0.0 or duration_s == 0.0:
        return state
    rate = _recrystallisation_rate_um3_s(temperature_k, cycling_amplitude_k)
    d0_cubed = state.mean_diameter_um**3
    d_new_cubed = d0_cubed + rate * duration_s
    d_new = d_new_cubed ** (1.0 / 3.0)
    return IceCrystalState(mean_diameter_um=d_new, distribution_cv=state.distribution_cv)
