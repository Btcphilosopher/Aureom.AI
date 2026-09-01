"""Water & utilities model (spec item 28): consumption tracked per utility, normalised by output."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class UtilityConsumption:
    process_water_l: float = 0.0
    cooling_water_l: float = 0.0
    wastewater_l: float = 0.0
    compressed_air_nm3: float = 0.0
    nitrogen_nm3: float = 0.0
    hvac_kwh: float = 0.0


@dataclass
class UtilityIntensity:
    """Per-unit-produced intensities -- the metric plant engineers actually track."""

    process_water_l_per_cell: float
    cooling_water_l_per_cell: float
    compressed_air_nm3_per_cell: float
    nitrogen_nm3_per_cell: float
    hvac_kwh_per_cell: float


class WaterUtilitiesModel:
    def compute_intensity(self, consumption: UtilityConsumption, cells_produced: int) -> UtilityIntensity:
        n = max(cells_produced, 1)
        return UtilityIntensity(
            process_water_l_per_cell=consumption.process_water_l / n,
            cooling_water_l_per_cell=consumption.cooling_water_l / n,
            compressed_air_nm3_per_cell=consumption.compressed_air_nm3 / n,
            nitrogen_nm3_per_cell=consumption.nitrogen_nm3 / n,
            hvac_kwh_per_cell=consumption.hvac_kwh / n,
        )

    def estimate_consumption(self, cells_produced: int) -> UtilityConsumption:
        """Model-assumption per-cell utility factors for a prismatic/pouch LFP-class line."""
        return UtilityConsumption(
            process_water_l=cells_produced * 0.35,
            cooling_water_l=cells_produced * 1.2,
            wastewater_l=cells_produced * 0.30,
            compressed_air_nm3=cells_produced * 0.08,
            nitrogen_nm3=cells_produced * 0.05,
            hvac_kwh=cells_produced * 0.15,
        )
