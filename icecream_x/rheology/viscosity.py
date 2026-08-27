"""Mixture viscosity model.

Ice cream mix is treated as a concentrated suspension/emulsion: fat
globules, casein micelles/protein aggregates, dissolved hydrocolloids,
and (once frozen) ice crystals are all dispersed in a continuous sugar/
salt solution ("serum"). Two effects are combined:

1. **Krieger-Dougherty crowding**: the well-established model for the
   relative viscosity of a concentrated suspension of the continuous
   phase's own viscosity, ``eta_serum``:

       eta_r = (1 - phi/phi_max) ** (-[eta] * phi_max)

   where ``phi`` is the dispersed-phase volume fraction (fat + ice +
   insoluble/hydrated solids), ``phi_max`` the maximum packing fraction,
   and ``[eta]`` the intrinsic (Einstein) viscosity coefficient
   (2.5 for hard spheres; ice cream mixes are usually modelled with a
   modestly higher effective value to reflect non-spherical/aggregated
   particles -- see ``INTRINSIC_VISCOSITY_COEFFICIENT``).

2. **Stabiliser thickening**: hydrocolloid stabilisers dramatically
   increase serum viscosity even at <0.5% usage by forming an entangled
   polymer network. This is modelled with a simple empirical exponential
   thickening factor, ``exp(k_stabiliser * stabiliser_mass_fraction)``.
   The rate constant is a representative order-of-magnitude default; the
   whole factor is designed to be replaced/recalibrated against
   viscometer data per stabiliser system.

3. **Non-Newtonian (shear-thinning) behaviour** is layered on top by
   :mod:`icecream_x.rheology.shear`, which treats this module's Newtonian
   viscosity estimate as the *consistency index* of a power-law fluid.

All of this is explicitly an engineering approximation, not a
first-principles emulsion-rheology solver. The point is a physically
motivated, monotonic, and modular structure: increasing fat, ice, or
stabiliser content increases predicted viscosity, and the empirical
constants are isolated so plant/lab data can recalibrate them without
restructuring the model.
"""

from __future__ import annotations

from dataclasses import dataclass

from icecream_x.rheology.temperature_dependence import water_viscosity_pa_s
from icecream_x.thermodynamics.ice_fraction import PhaseState
from icecream_x.thermodynamics.thermal_conductivity import (
    rho_fat_kg_m3,
    rho_ice_kg_m3,
    rho_water_liquid_kg_m3,
)

#: Maximum random-packing volume fraction of the dispersed phase.
MAX_PACKING_FRACTION = 0.63

#: Effective intrinsic (Einstein) viscosity coefficient. 2.5 for ideal hard
#: spheres; ice cream dispersed-phase particles (fat globule clusters,
#: partially-coalesced fat, ice crystals) are non-spherical and
#: interacting, so a higher effective value is used as a default.
INTRINSIC_VISCOSITY_COEFFICIENT = 3.5

#: Empirical stabiliser thickening-rate constant (dimensionless, applied to
#: stabiliser mass fraction as a percentage, i.e. 0.3% -> 0.3).
STABILISER_THICKENING_RATE = 1.8

#: Sugar/serum-solute thickening-rate constant, applied to total dissolved
#: sugar mass fraction of the serum phase (0-1).
SUGAR_THICKENING_RATE = 2.2


@dataclass(frozen=True, slots=True)
class RheologyState:
    apparent_viscosity_pa_s: float
    serum_viscosity_pa_s: float
    dispersed_phase_volume_fraction: float
    relative_viscosity: float


def dispersed_phase_volume_fraction(phase: PhaseState, temp_c: float) -> float:
    """Volume fraction of the mix occupied by fat + ice (the dispersed phases)."""
    if phase.total_mass_kg <= 0:
        return 0.0
    fat_v = phase.fat_kg / rho_fat_kg_m3(temp_c)
    ice_v = phase.ice_kg / rho_ice_kg_m3(temp_c)
    unfrozen_v = phase.unfrozen_water_kg / rho_water_liquid_kg_m3(temp_c)
    # Non-fat solids are largely solubilised/hydrated into the serum phase
    # and are folded into the serum-thickening term rather than counted as
    # a hard dispersed volume here.
    total_v = fat_v + ice_v + unfrozen_v
    if total_v <= 0:
        return 0.0
    return (fat_v + ice_v) / total_v


def serum_viscosity_pa_s(
    temperature_k: float, sugar_mass_fraction_of_serum: float, stabiliser_mass_fraction: float
) -> float:
    """Continuous-phase (serum) viscosity, including sugar/stabiliser thickening."""
    base = water_viscosity_pa_s(temperature_k)
    sugar_factor = _safe_exp(SUGAR_THICKENING_RATE * sugar_mass_fraction_of_serum)
    stabiliser_factor = _safe_exp(STABILISER_THICKENING_RATE * 100.0 * stabiliser_mass_fraction)
    return base * sugar_factor * stabiliser_factor


def _safe_exp(x: float) -> float:
    import math

    return math.exp(min(x, 50.0))


def mixture_viscosity(
    phase: PhaseState,
    sugar_mass_fraction_of_serum: float,
    stabiliser_mass_fraction: float,
) -> RheologyState:
    """Estimate the (zero-shear/Newtonian-reference) apparent viscosity of the mix."""
    temp_c = phase.temperature_c
    eta_serum = serum_viscosity_pa_s(
        phase.temperature_k, sugar_mass_fraction_of_serum, stabiliser_mass_fraction
    )
    phi = dispersed_phase_volume_fraction(phase, temp_c)
    phi_capped = min(phi, MAX_PACKING_FRACTION * 0.999)
    relative_viscosity = (1.0 - phi_capped / MAX_PACKING_FRACTION) ** (
        -INTRINSIC_VISCOSITY_COEFFICIENT * MAX_PACKING_FRACTION
    )
    eta_apparent = eta_serum * relative_viscosity
    return RheologyState(
        apparent_viscosity_pa_s=eta_apparent,
        serum_viscosity_pa_s=eta_serum,
        dispersed_phase_volume_fraction=phi,
        relative_viscosity=relative_viscosity,
    )
