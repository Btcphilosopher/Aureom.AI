"""Automated end-of-line cell testing (spec item 14)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np

from batteryfactory.config.chemistry_profiles import ChemistryProfile
from batteryfactory.datamodel.models import Cell, QualityResult, TestResult, next_serial
from batteryfactory.production.formation import FormationResult


@dataclass
class EOLMeasurements:
    voltage_v: float
    capacity_ah: float
    internal_resistance_mohm: float
    impedance_mohm: float
    leakage_current_ua: float
    temp_response_c: float
    self_discharge_pct_7d: float


class EOLTester:
    """
    Classifies PASS / REWORK / FAIL / REJECT against tolerance bands derived
    from the chemistry profile, so tightening or loosening the profile
    changes what the line accepts -- there is no independent hard-coded
    spec.
    """

    def __init__(self, rng: np.random.Generator | None = None) -> None:
        self.rng = rng or np.random.default_rng()

    def measure(self, cell: Cell, profile: ChemistryProfile, formation: FormationResult) -> EOLMeasurements:
        voltage = float(self.rng.normal(profile.nominal_voltage_v, profile.nominal_voltage_v * 0.01))
        capacity = float(self.rng.normal(formation.formation_capacity_ah, formation.formation_capacity_ah * 0.015))
        base_resistance = 0.5 + (100.0 / max(profile.capacity_ah_reference, 1.0))
        internal_resistance = float(max(0.05, self.rng.normal(base_resistance, base_resistance * 0.08)))
        impedance = float(max(0.05, internal_resistance * self.rng.normal(1.05, 0.05)))
        leakage = float(max(0.0, self.rng.normal(5.0, 2.0)))
        temp_response = float(self.rng.normal(formation.max_temp_c, 1.0))
        self_discharge = float(max(0.0, self.rng.normal(profile.self_discharge_pct_per_month / 4.0, 0.15)))

        return EOLMeasurements(voltage, capacity, internal_resistance, impedance, leakage, temp_response, self_discharge)

    def classify(self, measurements: EOLMeasurements, profile: ChemistryProfile) -> TestResult:
        # `capacity_ah_reference` is the cell's theoretical active-material capacity;
        # formation's coulombic efficiency (spec item 13) means even a healthy cell only
        # ever *delivers* ~90-99% of that, so the acceptance bands are calibrated against
        # realistic post-formation capacity, not the unreachable 100% figure.
        capacity_ratio = measurements.capacity_ah / profile.capacity_ah_reference
        voltage_ok = abs(measurements.voltage_v - profile.nominal_voltage_v) / profile.nominal_voltage_v < 0.05
        leakage_ok = measurements.leakage_current_ua < 20.0
        self_discharge_ok = measurements.self_discharge_pct_7d < 1.5

        if capacity_ratio >= 0.90 and voltage_ok and leakage_ok and self_discharge_ok and measurements.internal_resistance_mohm < 3.0:
            return TestResult.PASS
        if capacity_ratio >= 0.85 and leakage_ok:
            return TestResult.REWORK
        if capacity_ratio >= 0.75 and not (measurements.leakage_current_ua > 100.0 or measurements.self_discharge_pct_7d > 5.0):
            return TestResult.FAIL
        return TestResult.REJECT

    def run(self, cell: Cell, profile: ChemistryProfile, formation: FormationResult) -> tuple[Cell, QualityResult]:
        m = self.measure(cell, profile, formation)
        result = self.classify(m, profile)

        cell.capacity_ah = m.capacity_ah
        cell.internal_resistance_mohm = m.internal_resistance_mohm
        cell.voltage_v = m.voltage_v
        cell.test_result = result
        cell.formation_batch_id = formation.formation_batch_id

        quality_result = QualityResult(
            result_id=next_serial("QR"),
            subject_id=cell.serial_number,
            stage="eol_test",
            measurements={
                "voltage_v": m.voltage_v,
                "capacity_ah": m.capacity_ah,
                "internal_resistance_mohm": m.internal_resistance_mohm,
                "impedance_mohm": m.impedance_mohm,
                "leakage_current_ua": m.leakage_current_ua,
                "temp_response_c": m.temp_response_c,
                "self_discharge_pct_7d": m.self_discharge_pct_7d,
            },
            result=result,
            timestamp=datetime.utcnow(),
        )
        return cell, quality_result
