"""Temperature dependence of viscosity.

Two pieces:

1. **Serum (continuous-phase) viscosity**: the viscosity of the aqueous
   sugar/protein solution that fat globules, ice crystals and air cells
   are dispersed in. Its temperature dependence is dominated by the
   temperature dependence of water viscosity itself, modelled with the
   standard Vogel-Fulcher-Tammann (VFT) correlation for liquid water
   (constants as tabulated in engineering handbooks, e.g. Perry's
   Chemical Engineers' Handbook; valid ~273-373 K):

       mu_water(T) = A * 10^(B / (T - C))   [Pa s]
       A = 2.414e-5 Pa s, B = 247.8 K, C = 140 K

2. **Bulk mixture viscosity Arrhenius scaling**: an activation-energy-based
   scale factor sometimes used as a simpler drop-in correction when a
   reference viscosity at one temperature is known (e.g. from a plant
   measurement) and only the *shape* of the temperature dependence is
   needed. ``ACTIVATION_ENERGY_VISCOUS_FLOW_J_PER_MOL`` is a
   representative value for a concentrated dairy mix and is intended to
   be replaced with a fitted value once real viscometer data is
   available (see :mod:`icecream_x.digital_twin.calibration`).
"""

from __future__ import annotations

import math

GAS_CONSTANT_J_PER_MOL_K = 8.314462618

VFT_A_PA_S = 2.414e-5
VFT_B_K = 247.8
VFT_C_K = 140.0

#: Representative activation energy for viscous flow of a concentrated
#: dairy/sugar mix, J/mol. Order-of-magnitude literature value; calibrate
#: per formulation where precision matters.
ACTIVATION_ENERGY_VISCOUS_FLOW_J_PER_MOL = 25_000.0


def water_viscosity_pa_s(temperature_k: float) -> float:
    """Dynamic viscosity of pure liquid water via the VFT correlation."""
    if temperature_k <= VFT_C_K:
        raise ValueError(f"Temperature {temperature_k} K is below VFT validity range")
    exponent = VFT_B_K / (temperature_k - VFT_C_K)
    return VFT_A_PA_S * (10.0**exponent)


def arrhenius_scale_factor(
    temperature_k: float,
    reference_temperature_k: float,
    activation_energy_j_per_mol: float = ACTIVATION_ENERGY_VISCOUS_FLOW_J_PER_MOL,
) -> float:
    """Ratio eta(T) / eta(T_ref) predicted by an Arrhenius viscosity law."""
    return math.exp(
        (activation_energy_j_per_mol / GAS_CONSTANT_J_PER_MOL_K)
        * (1.0 / temperature_k - 1.0 / reference_temperature_k)
    )
