"""Generic heat exchanger equipment model.

Used by the pasteuriser (heating/regeneration/cooling sections) and by
any other process step that needs to estimate an outlet temperature or
heat duty from equipment sizing rather than an idealised instantaneous
temperature change.

The outlet-temperature model assumes the exchanger's utility side
(steam, chilled glycol, etc.) is large enough to stay at an approximately
constant temperature -- the standard "constant surrounding temperature"
heat-exchanger solution:

    T_out = T_utility + (T_in - T_utility) * exp(-UA / (m_dot * cp))

This is exact for one side condensing/evaporating (steam heating,
refrigerant cooling) and a good approximation for a well-oversized
recirculating glycol/water loop; it is not a full two-fluid
effectiveness-NTU solution (see docstring note below for when to extend
it).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from icecream_x.utils.validation import require_positive


@dataclass(frozen=True, slots=True)
class HeatExchanger:
    name: str
    area_m2: float
    overall_heat_transfer_coefficient_w_m2_k: float

    def __post_init__(self) -> None:
        require_positive(self.area_m2, "area_m2")
        require_positive(self.overall_heat_transfer_coefficient_w_m2_k, "U")

    @property
    def ua_w_per_k(self) -> float:
        return self.area_m2 * self.overall_heat_transfer_coefficient_w_m2_k

    def outlet_temperature_k(
        self,
        inlet_temperature_k: float,
        utility_temperature_k: float,
        mass_flow_kg_s: float,
        specific_heat_j_kg_k: float,
    ) -> float:
        """Outlet temperature assuming a constant-temperature utility stream.

        For counter-current exchangers where *both* streams change
        temperature significantly (e.g. regenerative pasteuriser
        recuperation sections), a two-stream effectiveness-NTU model is
        more accurate; this constant-utility-temperature approximation is
        used here for simplicity and is most accurate for heating with
        condensing steam or cooling with an evaporating/large-flow
        refrigerant loop.
        """
        require_positive(mass_flow_kg_s, "mass_flow_kg_s")
        require_positive(specific_heat_j_kg_k, "specific_heat_j_kg_k")
        ntu = self.ua_w_per_k / (mass_flow_kg_s * specific_heat_j_kg_k)
        return utility_temperature_k + (inlet_temperature_k - utility_temperature_k) * math.exp(
            -ntu
        )

    def heat_duty_w(
        self,
        inlet_temperature_k: float,
        outlet_temperature_k: float,
        mass_flow_kg_s: float,
        specific_heat_j_kg_k: float,
    ) -> float:
        """Sensible heat duty implied by an observed/target temperature change."""
        return mass_flow_kg_s * specific_heat_j_kg_k * (outlet_temperature_k - inlet_temperature_k)
