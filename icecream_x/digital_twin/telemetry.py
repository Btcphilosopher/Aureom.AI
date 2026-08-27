"""Telemetry ingestion.

A minimal, sensor-agnostic representation of real plant measurements
flowing into the digital twin: a timestamped, named, unit-tagged value.
Recognised sensor names (used by
:mod:`icecream_x.digital_twin.state_estimator`) include
``"temperature_c"``, ``"overrun_pct"``, ``"line_speed_kg_s"`` and
``"torque_pct"`` (a common proxy for freezer viscosity/consistency), but
any name can be recorded and later consumed by custom estimator logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class TelemetryReading:
    timestamp_s: float
    sensor_name: str
    value: float
    unit: str = ""


@dataclass(slots=True)
class TelemetryStream:
    readings: list[TelemetryReading] = field(default_factory=list)

    def record(self, timestamp_s: float, sensor_name: str, value: float, unit: str = "") -> None:
        self.readings.append(TelemetryReading(timestamp_s, sensor_name, value, unit))

    def latest(self, sensor_name: str, *, before_or_at_s: float | None = None) -> TelemetryReading | None:
        candidates = [r for r in self.readings if r.sensor_name == sensor_name]
        if before_or_at_s is not None:
            candidates = [r for r in candidates if r.timestamp_s <= before_or_at_s]
        if not candidates:
            return None
        return max(candidates, key=lambda r: r.timestamp_s)

    def series(self, sensor_name: str) -> list[tuple[float, float]]:
        return [(r.timestamp_s, r.value) for r in self.readings if r.sensor_name == sensor_name]
