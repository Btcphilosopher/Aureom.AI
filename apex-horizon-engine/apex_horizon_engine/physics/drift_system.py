"""
Drift detection, state machine, and scoring.

Drift is not a separate physics mode -- it is read out of the same rigid
body state everything else uses (heading vs. velocity-vector angle,
combined with rear slip severity from the tire model). This module only
classifies that state and scores it; it never touches forces directly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum


class DriftPhase(str, Enum):
    GRIP = "grip"
    TRANSITION = "transition"
    DRIFT = "drift"
    SPINOUT = "spinout"


ENTER_DRIFT_DEG = 12.0
EXIT_DRIFT_DEG = 6.0
SPINOUT_DEG = 75.0


@dataclass
class DriftState:
    phase: DriftPhase = DriftPhase.GRIP
    drift_angle_deg: float = 0.0
    time_in_drift_s: float = 0.0
    current_run_score: float = 0.0
    total_score: float = 0.0
    best_run_score: float = 0.0
    combo_multiplier: float = 1.0
    _linked_runs: int = field(default=0, repr=False)


def compute_drift_angle_deg(vx_mps: float, vy_mps: float) -> float:
    """Angle between the car's heading (its own x-axis) and its actual
    velocity vector -- 0 means pointing exactly where it's going."""
    if abs(vx_mps) < 0.05 and abs(vy_mps) < 0.05:
        return 0.0
    return math.degrees(math.atan2(abs(vy_mps), max(0.01, vx_mps)))


def update_drift_state(
    state: DriftState,
    dt: float,
    vx_mps: float,
    vy_mps: float,
    rear_slip_severity: float,
    throttle: float,
    speed_mps: float,
) -> DriftState:
    angle = compute_drift_angle_deg(vx_mps, vy_mps)
    state.drift_angle_deg = angle
    speed_kph = speed_mps * 3.6

    if angle >= SPINOUT_DEG and speed_kph > 15:
        state.phase = DriftPhase.SPINOUT
    elif state.phase in (DriftPhase.DRIFT, DriftPhase.TRANSITION):
        if angle < EXIT_DRIFT_DEG or speed_kph < 8:
            state.phase = DriftPhase.GRIP
        else:
            state.phase = DriftPhase.DRIFT
    else:
        if angle >= ENTER_DRIFT_DEG and rear_slip_severity > 0.35 and speed_kph > 15:
            state.phase = DriftPhase.TRANSITION if angle < ENTER_DRIFT_DEG * 1.5 else DriftPhase.DRIFT
        else:
            state.phase = DriftPhase.GRIP

    if state.phase in (DriftPhase.DRIFT, DriftPhase.TRANSITION):
        state.time_in_drift_s += dt
        # Score rewards angle, speed, and throttle control (a coasting slide
        # scores less than one held on the throttle -- rewards commitment).
        angle_factor = min(1.6, angle / 45.0)
        control_factor = 0.5 + 0.5 * throttle
        gain = angle_factor * (speed_kph / 100.0) * control_factor * state.combo_multiplier * dt * 45.0
        state.current_run_score += max(0.0, gain)
        state.combo_multiplier = min(4.0, state.combo_multiplier + dt * 0.15)
    elif state.phase == DriftPhase.SPINOUT:
        _bank_run(state, busted=True)
        state.time_in_drift_s = 0.0
        state.combo_multiplier = 1.0
    else:
        if state.time_in_drift_s > 0.0:
            _bank_run(state, busted=False)
        state.time_in_drift_s = 0.0
        state.combo_multiplier = max(1.0, state.combo_multiplier - dt * 0.6)

    return state


def _bank_run(state: DriftState, busted: bool) -> None:
    banked = state.current_run_score * (0.3 if busted else 1.0)
    state.total_score += banked
    state.best_run_score = max(state.best_run_score, banked)
    state.current_run_score = 0.0
