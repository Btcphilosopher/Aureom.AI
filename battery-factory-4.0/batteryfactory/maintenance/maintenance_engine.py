"""
Predictive maintenance (spec item 23): Weibull-based reliability model on
simulated telemetry, with hazard accelerated by observed vibration and
temperature anomalies -- a wear-and-tear proxy, not (yet) a model trained
on real failure records.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from batteryfactory.machines.machine_twin import MachineTwin


@dataclass
class WeibullParams:
    shape: float = 2.0          # >1: increasing hazard rate (wear-out)
    characteristic_life_hr: float = 15000.0


@dataclass
class MaintenancePrediction:
    machine_id: str
    runtime_hours: float
    failure_probability_next_week: float
    remaining_useful_life_hours: float
    recommended_maintenance_window_hours: float
    anomaly_score: float


class PredictiveMaintenanceEngine:
    def __init__(self, baseline_vibration_mm_s: float = 0.6, baseline_temp_c: float = 32.0) -> None:
        self.baseline_vibration = baseline_vibration_mm_s
        self.baseline_temp = baseline_temp_c

    def _anomaly_score(self, twin: MachineTwin) -> float:
        vibration_z = max(0.0, (twin.telemetry.vibration_mm_s - self.baseline_vibration) / max(self.baseline_vibration, 1e-6))
        temp_z = max(0.0, (twin.telemetry.temperature_c - self.baseline_temp) / max(self.baseline_temp, 1e-6))
        return vibration_z + temp_z

    def predict(self, twin: MachineTwin, params: WeibullParams = WeibullParams()) -> MaintenancePrediction:
        anomaly = self._anomaly_score(twin)
        # Anomalies shrink the effective characteristic life -- a rough proxy
        # for accelerated wear, not a physically calibrated degradation model.
        effective_life = params.characteristic_life_hr / (1.0 + anomaly)

        t = max(twin.runtime_hours, 1e-6)
        reliability_now = math.exp(-((t / effective_life) ** params.shape))
        reliability_next_week = math.exp(-(((t + 168.0) / effective_life) ** params.shape))
        failure_probability_next_week = 1.0 - (reliability_next_week / reliability_now if reliability_now > 0 else 0.0)
        failure_probability_next_week = max(0.0, min(1.0, failure_probability_next_week))

        # Expected remaining life to a target reliability threshold.
        target_reliability = 0.5
        rul_hours = max(0.0, effective_life * (-math.log(target_reliability)) ** (1.0 / params.shape) - t)

        recommended_window = max(24.0, rul_hours * 0.5)

        return MaintenancePrediction(
            machine_id=twin.config.machine_id,
            runtime_hours=twin.runtime_hours,
            failure_probability_next_week=failure_probability_next_week,
            remaining_useful_life_hours=rul_hours,
            recommended_maintenance_window_hours=recommended_window,
            anomaly_score=anomaly,
        )
