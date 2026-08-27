"""Hardening tunnel equipment definition.

Convective cold-air blast tunnel that takes product from the freezer
outlet (typically -5 to -6 degC, ~50% ice) down to a hard, storable state
(typically -18 degC or colder, >~80% ice). Modelled as forced-convection
cooling of a slab/cylinder-like product package with a characteristic
half-thickness, using a simple lumped or semi-infinite convective
boundary condition in :mod:`icecream_x.processing.hardening`.
"""

from __future__ import annotations

from dataclasses import dataclass

from icecream_x.utils.validation import require_positive


@dataclass(frozen=True, slots=True)
class HardeningTunnel:
    name: str
    air_temperature_c: float
    air_velocity_m_s: float
    heat_transfer_coefficient_w_m2_k: float
    tunnel_length_m: float
    belt_speed_m_s: float
    fan_power_kw: float
    refrigeration_power_kw: float

    def __post_init__(self) -> None:
        require_positive(self.tunnel_length_m, "tunnel_length_m")
        require_positive(self.belt_speed_m_s, "belt_speed_m_s")
        require_positive(self.heat_transfer_coefficient_w_m2_k, "heat_transfer_coefficient_w_m2_k")

    @property
    def transit_time_s(self) -> float:
        return self.tunnel_length_m / self.belt_speed_m_s


BLAST_TUNNEL_DEFAULT = HardeningTunnel(
    name="Blast Hardening Tunnel",
    air_temperature_c=-35.0,
    air_velocity_m_s=4.0,
    heat_transfer_coefficient_w_m2_k=45.0,
    tunnel_length_m=30.0,
    belt_speed_m_s=30.0 / (45.0 * 60.0),  # ~45 minute transit by default
    fan_power_kw=18.0,
    refrigeration_power_kw=90.0,
)
