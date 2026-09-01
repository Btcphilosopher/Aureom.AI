"""Coating machine digital twin (spec item 9)."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class CoatingParameters:
    line_speed_m_min: float
    target_thickness_um: float
    web_width_mm: float
    drying_zone_temp_c: float


@dataclass
class CoatingDefects:
    thickness_variation_pct: float
    edge_defect_rate: float
    coating_gap_rate: float
    contamination_rate: float

    @property
    def total_defect_rate(self) -> float:
        return min(1.0, self.thickness_variation_pct / 100.0 + self.edge_defect_rate
                    + self.coating_gap_rate + self.contamination_rate)


@dataclass
class CoatingResult:
    actual_thickness_um: float
    thickness_uniformity_std_pct: float
    defects: CoatingDefects
    throughput_m2_per_hr: float
    energy_kwh_per_hr: float
    scrap_pct: float


class CoatingMachine:
    """
    Higher line speed and thinner target coatings both drive up defect rates
    -- a real coating trade-off, not an arbitrary penalty: faster webs give
    the slurry less levelling time and drying zones less residence time.
    """

    def __init__(self, rated_power_kw: float = 180.0, rng: np.random.Generator | None = None) -> None:
        self.rated_power_kw = rated_power_kw
        self.rng = rng or np.random.default_rng()

    def run(self, params: CoatingParameters, slurry_quality_score: float) -> CoatingResult:
        speed_stress = np.clip(params.line_speed_m_min / 40.0, 0.3, 3.0)
        slurry_penalty = 1.0 - np.clip(slurry_quality_score, 0.0, 1.0)

        uniformity_std_pct = float(np.clip(1.2 * speed_stress + 3.0 * slurry_penalty, 0.3, 15.0))
        actual_thickness = float(self.rng.normal(params.target_thickness_um, params.target_thickness_um * uniformity_std_pct / 100.0))

        thickness_variation_pct = uniformity_std_pct
        edge_defect_rate = float(np.clip(0.002 * speed_stress + 0.01 * slurry_penalty, 0.0, 0.2))
        coating_gap_rate = float(np.clip(0.001 * speed_stress + 0.02 * slurry_penalty, 0.0, 0.2))
        contamination_rate = float(np.clip(0.0015 + 0.01 * slurry_penalty, 0.0, 0.1))
        defects = CoatingDefects(thickness_variation_pct, edge_defect_rate, coating_gap_rate, contamination_rate)

        throughput = params.line_speed_m_min * 60.0 * (params.web_width_mm / 1000.0)
        drying_energy_factor = 1.0 + max(0.0, params.drying_zone_temp_c - 80.0) * 0.01
        energy_kwh_per_hr = self.rated_power_kw * drying_energy_factor

        scrap_pct = float(np.clip(defects.total_defect_rate * 100.0, 0.0, 40.0))

        return CoatingResult(
            actual_thickness_um=actual_thickness,
            thickness_uniformity_std_pct=uniformity_std_pct,
            defects=defects,
            throughput_m2_per_hr=float(throughput),
            energy_kwh_per_hr=float(energy_kwh_per_hr),
            scrap_pct=scrap_pct,
        )
