"""Fat-globule network model.

Homogenisation breaks milkfat into small globules coated with a
protein/emulsifier membrane. During freezing, shear in the barrel plus
emulsifier-driven protein displacement causes controlled *partial
coalescence*: globules stick together into clusters and chains that form
a network reinforcing air-cell walls and giving ice cream its
characteristic melt-resistant, creamy structure. The fraction of fat that
has undergone this partial coalescence is conventionally called the
**fat destabilisation degree** and is a real, measured quality-control
parameter in the ice cream industry (via fat globule size / free-fat
assays); it is *not* the same as fat crystallisation (solid fat content),
which is tracked separately below.

Fat crystallinity (the solid fraction of the fat phase, driven by
temperature alone) is approximated with a simple sigmoidal solid-fat-
content curve broadly consistent with the shape of published
milkfat SFC-vs-temperature curves; it is a representative approximation,
not a melting-curve fit for a specific fat blend.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from icecream_x.equipment.homogeniser import Homogeniser

# --- globule size from homogenisation -------------------------------
GLOBULE_SIZE_COEFFICIENT_UM = 45.0
GLOBULE_SIZE_PRESSURE_EXPONENT = 0.6  # Walstra-style d ~ P^-0.6
GLOBULE_SIZE_PASS_REDUCTION_PER_PASS = 0.15  # fractional diameter reduction per extra pass
MIN_GLOBULE_DIAMETER_UM = 0.3

# --- destabilisation kinetics in the freezer -------------------------
DESTABILISATION_SHEAR_COEFFICIENT = 0.012
DESTABILISATION_EMULSIFIER_COEFFICIENT = 60.0
DESTABILISATION_MAX = 0.85

# --- fat crystallinity (solid fat content) sigmoid --------------------
SFC_MIDPOINT_C = 15.0
SFC_STEEPNESS = 0.35


@dataclass(frozen=True, slots=True)
class FatNetworkState:
    globule_diameter_um: float
    destabilisation_degree: float  # 0 (fully emulsified) .. 1 (fully coalesced)
    solid_fat_fraction: float  # 0..1, of the fat phase


def homogenised_globule_diameter_um(homogeniser: Homogeniser) -> float:
    pressure_bar = max(homogeniser.total_pressure_bar, 1.0)
    diameter = GLOBULE_SIZE_COEFFICIENT_UM * pressure_bar**(-GLOBULE_SIZE_PRESSURE_EXPONENT)
    diameter *= (1.0 - GLOBULE_SIZE_PASS_REDUCTION_PER_PASS) ** (homogeniser.passes - 1)
    return max(diameter, MIN_GLOBULE_DIAMETER_UM)


def destabilisation_degree(
    shear_exposure: float, emulsifier_mass_fraction: float, initial_degree: float = 0.0
) -> float:
    """Fraction of fat partially coalesced, given cumulative shear exposure.

    ``shear_exposure`` is a dimensionless proxy for cumulative
    shear*time (e.g. wall shear rate integrated over residence time in
    the freezer barrel). Emulsifiers accelerate destabilisation by
    displacing protein from the globule surface.
    """
    rate = DESTABILISATION_SHEAR_COEFFICIENT * (
        1.0 + DESTABILISATION_EMULSIFIER_COEFFICIENT * emulsifier_mass_fraction
    )
    progress = 1.0 - math.exp(-rate * shear_exposure)
    return initial_degree + (DESTABILISATION_MAX - initial_degree) * progress


def solid_fat_fraction(temperature_c: float) -> float:
    """Approximate solid fraction of the fat phase as a sigmoid of temperature."""
    return 1.0 / (1.0 + math.exp(SFC_STEEPNESS * (temperature_c - SFC_MIDPOINT_C)))
