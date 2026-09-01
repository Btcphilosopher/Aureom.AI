"""
High-level BMS simulation (spec item 34).

This is a conceptual, informational model of BMS *functions* -- voltage/
temperature monitoring, SoC/SoH estimation, passive balancing, fault
flagging -- for the digital twin's own analytics. It is NOT certified
safety-critical control software and must never be used to make real
charge/discharge/protection decisions on a physical pack.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class CellTelemetry:
    voltage_v: float
    temperature_c: float
    capacity_ah: float


@dataclass
class BMSFault:
    code: str
    message: str
    severity: str  # "warning" | "critical"


@dataclass
class BMSReading:
    soc_pct: float
    soh_pct: float
    min_cell_voltage_v: float
    max_cell_voltage_v: float
    voltage_imbalance_v: float
    max_cell_temp_c: float
    balancing_active_cells: list[int]
    faults: list[BMSFault]


class BMSSimulation:
    def __init__(self, ov_threshold_v: float = 4.25, uv_threshold_v: float = 2.5,
                 ot_threshold_c: float = 60.0, imbalance_threshold_v: float = 0.05) -> None:
        self.ov_threshold_v = ov_threshold_v
        self.uv_threshold_v = uv_threshold_v
        self.ot_threshold_c = ot_threshold_c
        self.imbalance_threshold_v = imbalance_threshold_v

    def estimate_soc(self, nominal_capacity_ah: float, remaining_capacity_ah: float) -> float:
        return float(np.clip(100.0 * remaining_capacity_ah / max(nominal_capacity_ah, 1e-6), 0.0, 100.0))

    def estimate_soh(self, current_capacity_ah: float, rated_capacity_ah: float) -> float:
        return float(np.clip(100.0 * current_capacity_ah / max(rated_capacity_ah, 1e-6), 0.0, 110.0))

    def evaluate(self, cells: list[CellTelemetry], nominal_capacity_ah: float, rated_capacity_ah: float) -> BMSReading:
        voltages = np.array([c.voltage_v for c in cells])
        temps = np.array([c.temperature_c for c in cells])
        avg_capacity = float(np.mean([c.capacity_ah for c in cells])) if cells else 0.0

        soc = self.estimate_soc(nominal_capacity_ah, avg_capacity)
        soh = self.estimate_soh(avg_capacity, rated_capacity_ah)

        min_v, max_v = float(voltages.min()), float(voltages.max())
        imbalance = max_v - min_v
        # Passive balancing bleeds the highest-voltage cells down towards the pack minimum.
        balancing_cells = [i for i, v in enumerate(voltages) if v > min_v + self.imbalance_threshold_v]

        faults: list[BMSFault] = []
        if max_v > self.ov_threshold_v:
            faults.append(BMSFault("OVERVOLTAGE", f"Cell voltage {max_v:.3f}V exceeds {self.ov_threshold_v}V", "critical"))
        if min_v < self.uv_threshold_v:
            faults.append(BMSFault("UNDERVOLTAGE", f"Cell voltage {min_v:.3f}V below {self.uv_threshold_v}V", "critical"))
        if float(temps.max()) > self.ot_threshold_c:
            faults.append(BMSFault("OVERTEMPERATURE", f"Cell temperature {float(temps.max()):.1f}C exceeds {self.ot_threshold_c}C", "critical"))
        if imbalance > self.imbalance_threshold_v * 3:
            faults.append(BMSFault("CELL_IMBALANCE", f"Voltage spread {imbalance:.3f}V exceeds tolerance", "warning"))

        return BMSReading(
            soc_pct=soc, soh_pct=soh, min_cell_voltage_v=min_v, max_cell_voltage_v=max_v,
            voltage_imbalance_v=imbalance, max_cell_temp_c=float(temps.max()),
            balancing_active_cells=balancing_cells, faults=faults,
        )
