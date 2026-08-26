"""
"F1 telemetry meets cyberpunk racing OS": rolling telemetry history plus
derived analytics -- horsepower curve, tire temperature trace, drift
angle trace, and a coarse braking heatmap bucketed by track position.
Pure aggregation over ``vehicles.vehicle_model.TelemetrySample`` history;
keeps a bounded ring buffer so a long free-roam session doesn't grow
memory unbounded.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Tuple

from apex_horizon_engine.utils.config import EngineCurve
from apex_horizon_engine.vehicles.vehicle_model import TelemetrySample

MAX_HISTORY = 3600  # 60s at 60Hz


@dataclass
class TelemetryRecorder:
    history: Deque[TelemetrySample] = field(default_factory=lambda: deque(maxlen=MAX_HISTORY))
    brake_heat_buckets: Dict[int, float] = field(default_factory=dict)

    def record(self, sample: TelemetrySample, brake_input: float, track_progress_frac: float) -> None:
        self.history.append(sample)
        bucket = int(track_progress_frac * 40) % 40
        current = self.brake_heat_buckets.get(bucket, 0.0)
        self.brake_heat_buckets[bucket] = current * 0.98 + brake_input * 0.15

    def horsepower_curve(self, engine: EngineCurve) -> List[Tuple[float, float]]:
        curve = []
        for rpm, torque in engine.points:
            hp = torque * rpm * 2.0 * 3.141592653589793 / 60.0 / 745.7
            curve.append((round(rpm), round(hp, 1)))
        return curve

    def tire_temp_trace(self, n: int = 120) -> List[Tuple[float, float]]:
        recent = list(self.history)[-n:]
        return [(s.tire_temp_front_c, s.tire_temp_rear_c) for s in recent]

    def drift_angle_trace(self, n: int = 120) -> List[float]:
        return [s.drift_angle_deg for s in list(self.history)[-n:]]

    def lap_delta(self, lap_time_s: float, best_lap_time_s: float) -> float:
        return round(lap_time_s - best_lap_time_s, 3)

    def average_slip_severity(self, n: int = 120) -> Tuple[float, float]:
        recent = list(self.history)[-n:]
        if not recent:
            return 0.0, 0.0
        f = sum(s.front_slip_severity for s in recent) / len(recent)
        r = sum(s.rear_slip_severity for s in recent) / len(recent)
        return round(f, 3), round(r, 3)

    def braking_heatmap(self) -> Dict[int, float]:
        return dict(sorted(self.brake_heat_buckets.items()))
