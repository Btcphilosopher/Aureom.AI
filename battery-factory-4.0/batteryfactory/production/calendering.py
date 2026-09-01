"""Calendering (roll-pressing) model with sensitivity analysis (spec item 10)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class CalenderingParameters:
    roller_pressure_kn_m: float
    target_thickness_um: float
    line_speed_m_min: float
    temperature_c: float


@dataclass
class CalenderingResult:
    thickness_um: float
    density_g_cc: float
    porosity_pct: float
    springback_pct: float


class CalenderingModel:
    """
    Pressure compacts the coating: thickness falls and density rises with
    roller pressure, following a diminishing-returns (log) compaction curve,
    with elastic springback partially recovering thickness after the nip,
    which increases at higher line speed (less dwell time under pressure).
    """

    def __init__(self, base_density_g_cc: float = 2.2, max_density_g_cc: float = 3.6) -> None:
        self.base_density_g_cc = base_density_g_cc
        self.max_density_g_cc = max_density_g_cc

    def compute(self, params: CalenderingParameters) -> CalenderingResult:
        compaction = 1.0 - np.exp(-params.roller_pressure_kn_m / 250.0)
        density = self.base_density_g_cc + (self.max_density_g_cc - self.base_density_g_cc) * compaction
        porosity_pct = float(np.clip(45.0 * (1.0 - compaction), 10.0, 45.0))

        springback_pct = float(np.clip(2.0 + params.line_speed_m_min * 0.05 - params.temperature_c * 0.01, 0.5, 12.0))
        thickness_um = params.target_thickness_um * (1.0 - compaction * 0.5) * (1.0 + springback_pct / 100.0)

        return CalenderingResult(
            thickness_um=float(thickness_um),
            density_g_cc=float(density),
            porosity_pct=porosity_pct,
            springback_pct=springback_pct,
        )

    def sensitivity_analysis(self, base: CalenderingParameters, pressures_kn_m: list[float]) -> list[CalenderingResult]:
        return [self.compute(CalenderingParameters(p, base.target_thickness_um, base.line_speed_m_min, base.temperature_c))
                for p in pressures_kn_m]
