"""Air-cell (bubble) population model.

Air is whipped into the mix in the freezer barrel simultaneously with
freezing. Cell size is governed primarily by the shear intensity in the
barrel and by how effectively the fat/protein/emulsifier system can
stabilise newly-formed bubble surfaces before they coalesce; cell
*stability* over storage is governed by the same surface chemistry plus
how rigid the surrounding matrix is (colder / more ice = less mobility =
more stable).

As with :mod:`icecream_x.microstructure.ice_crystals`, the functional
forms here are simplified, explicitly empirical relationships capturing
known qualitative trends (higher shear -> smaller cells; more emulsifier
-> smaller, more stable cells), not a fitted bubble-breakup/coalescence
population balance.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

CELL_SIZE_SHEAR_COEFFICIENT_UM = 900.0
CELL_SIZE_SHEAR_EXPONENT = 0.4
CELL_SIZE_EMULSIFIER_SENSITIVITY = 25.0  # diameter reduction (um) per mass-% emulsifier
MIN_CELL_DIAMETER_UM = 10.0

STABILITY_EMULSIFIER_WEIGHT = 6.0
STABILITY_FAT_DESTABILISATION_WEIGHT = 3.0


@dataclass(frozen=True, slots=True)
class AirCellState:
    mean_diameter_um: float
    air_volume_fraction: float
    stability_index: float  # 0 (unstable) .. 1 (very stable)


def estimate_air_cell_size_um(
    wall_shear_rate_1_per_s: float, emulsifier_mass_fraction: float
) -> float:
    base = CELL_SIZE_SHEAR_COEFFICIENT_UM * max(wall_shear_rate_1_per_s, 1.0) ** (
        -CELL_SIZE_SHEAR_EXPONENT
    )
    reduction = CELL_SIZE_EMULSIFIER_SENSITIVITY * 100.0 * emulsifier_mass_fraction
    return max(base - reduction, MIN_CELL_DIAMETER_UM)


def estimate_stability_index(
    emulsifier_mass_fraction: float, fat_destabilisation_degree: float
) -> float:
    """A 0-1 engineering index of air-cell resistance to coalescence/collapse.

    Increases with emulsifier level and with the degree of fat
    destabilisation (a partially-coalesced fat network mechanically
    reinforces the cell walls -- a well-established structural role of
    fat in ice cream, see :mod:`icecream_x.microstructure.fat_network`).
    """
    raw = (
        STABILITY_EMULSIFIER_WEIGHT * 100.0 * emulsifier_mass_fraction
        + STABILITY_FAT_DESTABILISATION_WEIGHT * fat_destabilisation_degree
    )
    return 1.0 - math.exp(-raw)


def air_cell_state(
    wall_shear_rate_1_per_s: float,
    emulsifier_mass_fraction: float,
    fat_destabilisation_degree: float,
    air_volume_fraction: float,
) -> AirCellState:
    diameter = estimate_air_cell_size_um(wall_shear_rate_1_per_s, emulsifier_mass_fraction)
    stability = estimate_stability_index(emulsifier_mass_fraction, fat_destabilisation_degree)
    return AirCellState(
        mean_diameter_um=diameter,
        air_volume_fraction=air_volume_fraction,
        stability_index=stability,
    )
