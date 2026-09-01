"""Machine digital twin (spec item 16): state machine + telemetry."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from batteryfactory.datamodel.models import MachineState

# Legal state transitions -- a twin can only move through the states a real
# machine controller would allow.
_ALLOWED_TRANSITIONS: dict[MachineState, set[MachineState]] = {
    MachineState.OFFLINE: {MachineState.STARTING},
    MachineState.STARTING: {MachineState.RUNNING, MachineState.FAULT},
    MachineState.RUNNING: {MachineState.IDLE, MachineState.CHANGEOVER, MachineState.MAINTENANCE, MachineState.FAULT, MachineState.OFFLINE},
    MachineState.IDLE: {MachineState.RUNNING, MachineState.CHANGEOVER, MachineState.MAINTENANCE, MachineState.OFFLINE},
    MachineState.CHANGEOVER: {MachineState.RUNNING, MachineState.FAULT},
    MachineState.MAINTENANCE: {MachineState.STARTING, MachineState.OFFLINE},
    MachineState.FAULT: {MachineState.MAINTENANCE, MachineState.OFFLINE},
}


@dataclass
class MachineTelemetry:
    temperature_c: float = 25.0
    vibration_mm_s: float = 0.5
    energy_kwh_cumulative: float = 0.0


@dataclass
class MachineTwinConfig:
    machine_id: str
    name: str
    stage: str
    cycle_time_s: float
    rated_power_kw: float
    base_failure_rate_per_hr: float = 0.002  # baseline hazard, ramps with wear (see maintenance engine)


class MachineTwin:
    def __init__(self, config: MachineTwinConfig, rng: np.random.Generator | None = None) -> None:
        self.config = config
        self.state = MachineState.OFFLINE
        self.telemetry = MachineTelemetry()
        self.rng = rng or np.random.default_rng()
        self.runtime_hours = 0.0
        self.downtime_hours = 0.0
        self.fault_count = 0
        self.completed_units = 0
        self.state_log: list[MachineState] = [MachineState.OFFLINE]

    def transition(self, new_state: MachineState) -> bool:
        if new_state not in _ALLOWED_TRANSITIONS.get(self.state, set()):
            return False
        self.state = new_state
        self.state_log.append(new_state)
        return True

    def step(self, dt_hours: float) -> None:
        """Advance the twin by dt_hours, updating telemetry, runtime and possibly faulting."""
        if self.state == MachineState.RUNNING:
            self.runtime_hours += dt_hours
            self.telemetry.energy_kwh_cumulative += self.config.rated_power_kw * dt_hours
            self.telemetry.temperature_c = float(np.clip(
                self.rng.normal(self.telemetry.temperature_c * 0.9 + 32.0 * 0.1, 0.4), 15.0, 90.0
            ))
            self.telemetry.vibration_mm_s = float(max(0.1, self.rng.normal(0.6 + self.runtime_hours * 1e-5, 0.05)))

            hazard = self.config.base_failure_rate_per_hr * (1.0 + self.runtime_hours / 20000.0)
            if self.rng.random() < hazard * dt_hours:
                self.transition(MachineState.FAULT)
                self.fault_count += 1
        else:
            self.downtime_hours += dt_hours

    @property
    def utilisation_pct(self) -> float:
        total = self.runtime_hours + self.downtime_hours
        return 100.0 * self.runtime_hours / total if total > 0 else 0.0

    @property
    def cycles_per_hour(self) -> float:
        return 3600.0 / self.config.cycle_time_s if self.config.cycle_time_s > 0 else 0.0
