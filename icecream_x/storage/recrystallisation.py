"""Recrystallisation orchestration: apply ice-crystal growth over a storage timestep.

Thin wrapper over :mod:`icecream_x.microstructure.ice_crystals` that
knows how to pull the driving temperature and cycling-amplitude signals
out of a :class:`~icecream_x.core.state.ProductState` /
:class:`~icecream_x.storage.temperature_history.TemperatureProfile` pair,
kept as its own module (rather than inlined into
:mod:`icecream_x.storage.cold_chain`) so it can also be used directly for
post-hoc "what would recrystallisation have done under this alternative
temperature history" analysis (see :mod:`icecream_x.scenarios.experiments`).
"""

from __future__ import annotations

from icecream_x.core.state import ProductState
from icecream_x.microstructure.ice_crystals import IceCrystalState, grow_by_recrystallisation
from icecream_x.thermodynamics.phase_equilibrium import evaluate as evaluate_thermal


def step_recrystallisation(
    state: ProductState, temperature_k: float, dt_s: float, cycling_amplitude_k: float
) -> IceCrystalState | None:
    """Advance ``state``'s ice-crystal population by one storage timestep."""
    crystals = state.microstructure.ice_crystals
    if crystals is None:
        return None
    ice_fraction = evaluate_thermal(state.composition, temperature_k).phase.ice_mass_fraction
    return grow_by_recrystallisation(
        crystals,
        temperature_k,
        dt_s,
        ice_mass_fraction=ice_fraction,
        cycling_amplitude_k=cycling_amplitude_k,
    )
