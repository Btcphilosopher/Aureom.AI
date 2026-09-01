"""Industrial robotics model (spec item 17)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np


class RobotRole(str, Enum):
    MATERIAL_HANDLING = "material_handling"
    CELL_MOVEMENT = "cell_movement"
    ASSEMBLY = "assembly"
    PALLETISATION = "palletisation"
    INSPECTION = "inspection"


@dataclass
class RobotTwin:
    robot_id: str
    role: RobotRole
    nominal_cycle_time_s: float
    fault_rate_per_hr: float = 0.001

    busy_seconds: float = 0.0
    idle_seconds: float = 0.0
    queue_seconds: float = 0.0
    fault_count: int = 0
    cycles_completed: int = 0

    def run_cycle(self, rng: np.random.Generator, queue_wait_s: float = 0.0) -> float:
        """Executes one work cycle; returns actual cycle time (s)."""
        self.queue_seconds += queue_wait_s
        if rng.random() < self.fault_rate_per_hr * (self.nominal_cycle_time_s / 3600.0):
            self.fault_count += 1
            actual = self.nominal_cycle_time_s * rng.uniform(3.0, 8.0)  # fault recovery penalty
        else:
            actual = float(rng.normal(self.nominal_cycle_time_s, self.nominal_cycle_time_s * 0.05))
        self.busy_seconds += actual
        self.cycles_completed += 1
        return actual

    @property
    def utilisation_pct(self) -> float:
        total = self.busy_seconds + self.idle_seconds
        return 100.0 * self.busy_seconds / total if total > 0 else 0.0

    @property
    def avg_queue_time_s(self) -> float:
        return self.queue_seconds / self.cycles_completed if self.cycles_completed else 0.0
