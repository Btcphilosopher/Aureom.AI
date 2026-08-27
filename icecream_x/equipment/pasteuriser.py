"""Pasteuriser equipment definition.

Distinguishes target temperature, holding time, and heating/cooling rate
as separate configurable parameters (rather than treating pasteurisation
as an instantaneous event) so :mod:`icecream_x.processing.pasteurisation`
can simulate the full thermal history: ramp up, hold, ramp down.
"""

from __future__ import annotations

from dataclasses import dataclass

from icecream_x.equipment.heat_exchanger import HeatExchanger
from icecream_x.utils.validation import require_positive


@dataclass(frozen=True, slots=True)
class Pasteuriser:
    name: str
    target_temperature_c: float
    holding_time_s: float
    heating_rate_c_per_s: float
    cooling_rate_c_per_s: float
    heating_exchanger: HeatExchanger
    cooling_exchanger: HeatExchanger
    pump_power_kw: float = 1.5

    def __post_init__(self) -> None:
        require_positive(self.holding_time_s, "holding_time_s")
        require_positive(self.heating_rate_c_per_s, "heating_rate_c_per_s")
        require_positive(self.cooling_rate_c_per_s, "cooling_rate_c_per_s")


#: HTST (High-Temperature-Short-Time) is the industry-standard regime for
#: ice cream mix: >= 80 degC for >= 25 s is a common specification
#: (exact regulatory minima vary by jurisdiction -- treat this as a
#: representative default, not a compliance guarantee).
HTST_DEFAULT = Pasteuriser(
    name="HTST Pasteuriser",
    target_temperature_c=83.0,
    holding_time_s=25.0,
    heating_rate_c_per_s=1.2,
    cooling_rate_c_per_s=1.5,
    heating_exchanger=HeatExchanger(
        name="Heating section", area_m2=8.0, overall_heat_transfer_coefficient_w_m2_k=2500.0
    ),
    cooling_exchanger=HeatExchanger(
        name="Cooling section", area_m2=10.0, overall_heat_transfer_coefficient_w_m2_k=2200.0
    ),
)

#: LTLT (Low-Temperature-Long-Time / vat / batch) pasteurisation.
LTLT_DEFAULT = Pasteuriser(
    name="LTLT Batch Pasteuriser",
    target_temperature_c=69.0,
    holding_time_s=1800.0,
    heating_rate_c_per_s=0.05,
    cooling_rate_c_per_s=0.08,
    heating_exchanger=HeatExchanger(
        name="Vat jacket (heating)", area_m2=4.0, overall_heat_transfer_coefficient_w_m2_k=600.0
    ),
    cooling_exchanger=HeatExchanger(
        name="Vat jacket (cooling)", area_m2=4.0, overall_heat_transfer_coefficient_w_m2_k=550.0
    ),
)
