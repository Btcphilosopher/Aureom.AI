"""
Factory safety monitoring (spec item 36).

Conceptual: flags conditions that need operator attention. It does NOT
autonomously override any safety system, interlock, or control loop.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AlarmSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class SafetyAlarm:
    source: str
    alarm_type: str
    severity: AlarmSeverity
    message: str
    value: float
    threshold: float


@dataclass
class SafetyThresholds:
    max_dry_room_humidity_pct: float = 2.0
    max_process_temp_c: float = 45.0
    max_formation_temp_c: float = 60.0
    min_ventilation_ach: float = 4.0
    max_machine_vibration_mm_s: float = 4.5


class SafetyMonitor:
    """Evaluates simulated sensor readings against thresholds and raises
    alarms **for operator review** -- it never actuates anything itself."""

    def __init__(self, thresholds: SafetyThresholds | None = None) -> None:
        self.thresholds = thresholds or SafetyThresholds()

    def evaluate(self, readings: dict[str, float], machine_faults: dict[str, bool] | None = None) -> list[SafetyAlarm]:
        alarms: list[SafetyAlarm] = []
        t = self.thresholds
        machine_faults = machine_faults or {}

        if "dry_room_humidity_pct" in readings and readings["dry_room_humidity_pct"] > t.max_dry_room_humidity_pct:
            alarms.append(SafetyAlarm("dry_room", "humidity_excursion", AlarmSeverity.WARNING,
                                       "Dry room humidity above target -- risk to electrode/electrolyte moisture spec.",
                                       readings["dry_room_humidity_pct"], t.max_dry_room_humidity_pct))
        if "process_temp_c" in readings and readings["process_temp_c"] > t.max_process_temp_c:
            alarms.append(SafetyAlarm("process", "temperature_excursion", AlarmSeverity.WARNING,
                                       "Process temperature above normal operating band.",
                                       readings["process_temp_c"], t.max_process_temp_c))
        if "formation_temp_c" in readings and readings["formation_temp_c"] > t.max_formation_temp_c:
            alarms.append(SafetyAlarm("formation", "temperature_excursion", AlarmSeverity.CRITICAL,
                                       "Formation cell temperature approaching thermal-runaway precursor range -- operator review required.",
                                       readings["formation_temp_c"], t.max_formation_temp_c))
        if "ventilation_ach" in readings and readings["ventilation_ach"] < t.min_ventilation_ach:
            alarms.append(SafetyAlarm("hvac", "ventilation_low", AlarmSeverity.CRITICAL,
                                       "Air change rate below minimum -- solvent/off-gas accumulation risk.",
                                       readings["ventilation_ach"], t.min_ventilation_ach))
        for machine_id, faulted in machine_faults.items():
            if faulted:
                alarms.append(SafetyAlarm(machine_id, "equipment_fault", AlarmSeverity.WARNING,
                                           f"{machine_id} reporting a fault state.", 1.0, 0.0))

        return alarms
