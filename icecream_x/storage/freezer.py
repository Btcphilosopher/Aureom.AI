"""Cold-storage facility model (retail cabinet, cold store, transport reefer).

Distinct from :mod:`icecream_x.equipment.freezer`, which models the
*processing-line* scraped-surface freezer barrel that performs freezing +
aeration. This module models a static/quasi-static storage environment:
a cabinet, warehouse, or truck holding already-hardened product at a
setpoint temperature.
"""

from __future__ import annotations

from dataclasses import dataclass

from icecream_x.utils.validation import require_positive


@dataclass(frozen=True, slots=True)
class StorageFacility:
    name: str
    setpoint_temperature_c: float
    #: First-order thermal lag time constant (s) between ambient air
    #: temperature and product core temperature -- represents package
    #: thermal mass damping short excursions (a large tub responds more
    #: slowly than a thin novelty bar). 0 = product instantly tracks
    #: ambient air temperature.
    thermal_lag_time_constant_s: float = 1800.0
    refrigeration_power_kw: float = 5.0
    heat_transfer_coefficient_w_m2_k: float = 15.0

    def __post_init__(self) -> None:
        if self.thermal_lag_time_constant_s < 0:
            raise ValueError("thermal_lag_time_constant_s must be >= 0")
        require_positive(self.refrigeration_power_kw, "refrigeration_power_kw")


RETAIL_CABINET = StorageFacility(
    name="Retail Display Cabinet",
    setpoint_temperature_c=-18.0,
    thermal_lag_time_constant_s=900.0,
    refrigeration_power_kw=3.5,
)

COLD_STORE = StorageFacility(
    name="Distribution Cold Store",
    setpoint_temperature_c=-25.0,
    thermal_lag_time_constant_s=7200.0,
    refrigeration_power_kw=45.0,
)

REFRIGERATED_TRANSPORT = StorageFacility(
    name="Refrigerated Truck",
    setpoint_temperature_c=-20.0,
    thermal_lag_time_constant_s=3600.0,
    refrigeration_power_kw=8.0,
)

HOME_FREEZER = StorageFacility(
    name="Domestic Freezer",
    setpoint_temperature_c=-18.0,
    thermal_lag_time_constant_s=1800.0,
    refrigeration_power_kw=0.15,
)
