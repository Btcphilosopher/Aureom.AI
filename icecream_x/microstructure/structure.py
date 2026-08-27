"""Unified microstructure state.

Combines the ice-crystal, air-cell, and fat-network sub-states into one
:class:`MicrostructureState` representing:

    ICE CRYSTALS + AIR CELLS + FAT NETWORK + SERUM PHASE

as required by the product spec. The serum phase itself (the unfrozen
aqueous solution) is characterised elsewhere by
:class:`icecream_x.thermodynamics.ice_fraction.PhaseState` and
:class:`icecream_x.rheology.viscosity.RheologyState`; this module simply
carries a reference viscosity value alongside the three particulate
sub-states so a single object fully describes "what the product looks
like" at a point in time.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from icecream_x.microstructure.air_cells import AirCellState
from icecream_x.microstructure.fat_network import FatNetworkState
from icecream_x.microstructure.ice_crystals import IceCrystalState


@dataclass(frozen=True, slots=True)
class MicrostructureState:
    ice_crystals: IceCrystalState | None
    air_cells: AirCellState | None
    fat_network: FatNetworkState | None
    serum_viscosity_pa_s: float = 0.0

    @classmethod
    def initial(cls) -> "MicrostructureState":
        """The (undeveloped) microstructure of a freshly-mixed, unfrozen liquid."""
        return cls(ice_crystals=None, air_cells=None, fat_network=None, serum_viscosity_pa_s=0.0)

    def with_ice_crystals(self, ice_crystals: IceCrystalState) -> "MicrostructureState":
        return replace(self, ice_crystals=ice_crystals)

    def with_air_cells(self, air_cells: AirCellState) -> "MicrostructureState":
        return replace(self, air_cells=air_cells)

    def with_fat_network(self, fat_network: FatNetworkState) -> "MicrostructureState":
        return replace(self, fat_network=fat_network)

    def with_serum_viscosity(self, viscosity_pa_s: float) -> "MicrostructureState":
        return replace(self, serum_viscosity_pa_s=viscosity_pa_s)

    def summary(self) -> dict[str, float | None]:
        return {
            "mean_ice_crystal_diameter_um": (
                round(self.ice_crystals.mean_diameter_um, 2) if self.ice_crystals else None
            ),
            "mean_air_cell_diameter_um": (
                round(self.air_cells.mean_diameter_um, 2) if self.air_cells else None
            ),
            "air_cell_stability_index": (
                round(self.air_cells.stability_index, 3) if self.air_cells else None
            ),
            "fat_globule_diameter_um": (
                round(self.fat_network.globule_diameter_um, 3) if self.fat_network else None
            ),
            "fat_destabilisation_degree": (
                round(self.fat_network.destabilisation_degree, 3) if self.fat_network else None
            ),
            "solid_fat_fraction": (
                round(self.fat_network.solid_fat_fraction, 3) if self.fat_network else None
            ),
        }
