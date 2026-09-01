"""Dry room digital twin (spec item 12)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class DryRoomState:
    dew_point_c: float
    humidity_pct: float
    temperature_c: float
    airflow_m3_per_hr: float


@dataclass
class DryRoomResult:
    dehumidification_load_kw: float
    hvac_energy_kwh: float
    humidity_pct: float
    within_spec: bool


class DryRoom:
    """
    Moisture removal load scales with air-exchange rate and the humidity
    difference vs. ambient (a simplified psychrometric mass-balance), and
    production throughput increases the moisture ingress load through
    material handling and door cycling -- so pushing more cells through the
    line without adding dehumidification capacity drives humidity, and
    energy, up together.
    """

    def __init__(self, target_dew_point_c: float = -40.0, floor_area_m2: float = 5000.0,
                 ambient_humidity_ratio_g_kg: float = 8.0, rng: np.random.Generator | None = None) -> None:
        self.target_dew_point_c = target_dew_point_c
        self.floor_area_m2 = floor_area_m2
        self.ambient_humidity_ratio_g_kg = ambient_humidity_ratio_g_kg
        self.rng = rng or np.random.default_rng()

    def simulate_hour(self, production_throughput_cells_per_hr: float, ambient_temp_c: float = 22.0) -> DryRoomResult:
        target_humidity_ratio_g_kg = max(0.05, 10 ** ((self.target_dew_point_c + 100) / 50))  # crude monotonic proxy
        air_exchange_rate = 4.0 + production_throughput_cells_per_hr / 5000.0  # more door cycling under load
        moisture_load_g_per_hr = (
            air_exchange_rate * self.floor_area_m2 * 3.0
            * (self.ambient_humidity_ratio_g_kg - target_humidity_ratio_g_kg)
        )
        dehumidification_load_kw = max(0.0, moisture_load_g_per_hr * 0.00068)  # latent heat proxy, kW per g/hr removed
        hvac_energy_kwh = dehumidification_load_kw * 1.0 * self.rng.normal(1.0, 0.03)

        achieved_humidity_pct = float(np.clip(
            2.0 + (production_throughput_cells_per_hr / 20000.0) - (dehumidification_load_kw / 500.0),
            0.3, 15.0,
        ))
        within_spec = achieved_humidity_pct <= 2.0

        return DryRoomResult(
            dehumidification_load_kw=float(dehumidification_load_kw),
            hvac_energy_kwh=float(max(0.0, hvac_energy_kwh)),
            humidity_pct=achieved_humidity_pct,
            within_spec=within_spec,
        )
