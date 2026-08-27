"""Aeration / overrun: incorporation of air.

Air is physically whipped in during the freezer pass (see
:mod:`icecream_x.processing.freezing`); this step is kept separate so
overrun can be set/experimented with independently of the thermal
freezing simulation (e.g. "what if we increase overrun at constant
freezer settings?" -- Experiment C in the spec).

    overrun_pct = 100 * (volume_after - volume_before) / volume_before
                = 100 * air_volume_fraction / (1 - air_volume_fraction)

Overrun directly reduces product density and (via the air-cell model)
influences the melting/structural-collapse behaviour simulated in
:mod:`icecream_x.processing.hardening` and downstream melting analytics.
"""

from __future__ import annotations

from icecream_x.core.events import EventLog
from icecream_x.core.state import ProcessStage, ProductState
from icecream_x.microstructure.air_cells import air_cell_state
from icecream_x.utils.validation import require_non_negative


def overrun_pct_to_air_volume_fraction(overrun_pct: float) -> float:
    require_non_negative(overrun_pct, "overrun_pct")
    return overrun_pct / (100.0 + overrun_pct)


def air_volume_fraction_to_overrun_pct(air_volume_fraction: float) -> float:
    if not (0.0 <= air_volume_fraction < 1.0):
        raise ValueError("air_volume_fraction must be in [0, 1)")
    return 100.0 * air_volume_fraction / (1.0 - air_volume_fraction)


def aerate(
    state: ProductState,
    target_overrun_pct: float,
    *,
    wall_shear_rate_1_per_s: float = 500.0,
    event_log: EventLog | None = None,
) -> ProductState:
    """Set the product's overrun and update the air-cell microstructure."""
    air_fraction = overrun_pct_to_air_volume_fraction(target_overrun_pct)
    fractions = state.composition.as_fractions()
    fat_state = state.microstructure.fat_network
    destab = fat_state.destabilisation_degree if fat_state else 0.0

    air_state = air_cell_state(
        wall_shear_rate_1_per_s=wall_shear_rate_1_per_s,
        emulsifier_mass_fraction=fractions["emulsifier"],
        fat_destabilisation_degree=destab,
        air_volume_fraction=air_fraction,
    )
    new_microstructure = state.microstructure.with_air_cells(air_state)

    new_state = state.evolve(
        stage=ProcessStage.AERATED,
        microstructure=new_microstructure,
        air_volume_fraction=air_fraction,
    )

    if event_log is not None:
        event_log.record(
            state.elapsed_time_s,
            ProcessStage.AERATED.value,
            f"Aerated to {target_overrun_pct:.0f}% overrun",
            air_cell_diameter_um=round(air_state.mean_diameter_um, 2),
            stability_index=round(air_state.stability_index, 3),
        )
    return new_state
