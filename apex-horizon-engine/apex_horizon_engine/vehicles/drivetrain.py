"""
Drivetrain: engine RPM, torque curve lookup, gearing, auto-shift logic,
and AWD/RWD/FWD axle torque split.

Wheel torque is *derived* every tick from wheel speed (via the gear ratio
chain) and the engine's torque curve -- there is no "acceleration curve"
asset anywhere; the acceleration curve the player feels is an emergent
property of gearing x torque curve x mass x drag, exactly like a real car.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from apex_horizon_engine.utils.config import DrivetrainLayout, DrivetrainSpec, EngineCurve

WHEEL_RADIUS_M = 0.33  # reasonable default rolling radius; vehicle_model may override


@dataclass
class DrivetrainState:
    gear_index: int = 1          # 1-based; 0 = reverse
    rpm: float = 900.0
    shift_timer_s: float = 0.0
    shifting: bool = False
    time_since_shift_s: float = 1.0  # cooldown tracker; starts "ready to shift"


def wheel_rps_from_speed(speed_mps: float, wheel_radius_m: float = WHEEL_RADIUS_M) -> float:
    return speed_mps / (2.0 * math.pi * max(0.05, wheel_radius_m))


def _engine_rpm_for_gear(spec: DrivetrainSpec, wheel_rps: float, gear_index: int) -> float:
    if spec.is_electric:
        # Single-speed reduction gear -- "RPM" here is motor RPM.
        ratio = spec.gear_ratios[0] * spec.final_drive
        return abs(wheel_rps) * 60.0 * ratio
    if gear_index <= 0:
        ratio = 3.6 * spec.final_drive  # fixed reverse ratio
    else:
        idx = min(gear_index, len(spec.gear_ratios)) - 1
        ratio = spec.gear_ratios[idx] * spec.final_drive
    return abs(wheel_rps) * 60.0 * ratio


def step_drivetrain(
    spec: DrivetrainSpec,
    engine: EngineCurve,
    state: DrivetrainState,
    dt: float,
    throttle: float,
    speed_mps: float,
    wheel_radius_m: float = WHEEL_RADIUS_M,
) -> float:
    """Advance gear/shift state and return total axle torque (Nm) at the
    wheels for this tick (before front/rear split)."""
    throttle = max(0.0, min(1.0, throttle))
    wheel_rps = wheel_rps_from_speed(speed_mps, wheel_radius_m)
    state.time_since_shift_s += dt

    # The flywheel has its own (small but nonzero) rotational inertia, so
    # RPM chases the gear-implied target rather than teleporting to it --
    # this also keeps a single noisy tick of wheel slip from immediately
    # tripping the shift logic below.
    flywheel_lag_s = 0.06
    smoothing = min(1.0, dt / flywheel_lag_s)

    if state.shifting:
        state.shift_timer_s -= dt
        if state.shift_timer_s <= 0:
            state.shifting = False
        target_rpm = _engine_rpm_for_gear(spec, wheel_rps, state.gear_index)
        state.rpm += (target_rpm - state.rpm) * smoothing
        return 0.0  # torque interrupt during the shift

    target_rpm = _engine_rpm_for_gear(spec, wheel_rps, state.gear_index)
    idle = engine.idle_rpm
    state.rpm += (max(idle, target_rpm) - state.rpm) * smoothing

    can_shift = state.time_since_shift_s >= max(0.25, spec.shift_time_s * 2.0)
    if can_shift and not spec.is_electric and len(spec.gear_ratios) > 1:
        if state.rpm >= engine.redline_rpm * 0.97 and throttle > 0.05 and state.gear_index < len(spec.gear_ratios):
            state.gear_index += 1
            state.shifting = True
            state.shift_timer_s = spec.shift_time_s
            state.time_since_shift_s = 0.0
        elif state.rpm <= engine.redline_rpm * 0.30 and state.gear_index > 1:
            projected = _engine_rpm_for_gear(spec, wheel_rps, state.gear_index - 1)
            if projected < engine.redline_rpm * 0.92:
                state.gear_index -= 1
                state.shifting = True
                state.shift_timer_s = spec.shift_time_s * 0.6
                state.time_since_shift_s = 0.0

    engine_torque = engine.torque_at(state.rpm) * throttle

    if spec.is_electric:
        total_ratio = spec.gear_ratios[0] * spec.final_drive
    elif state.gear_index <= 0:
        total_ratio = 3.6 * spec.final_drive
    else:
        idx = min(state.gear_index, len(spec.gear_ratios)) - 1
        total_ratio = spec.gear_ratios[idx] * spec.final_drive

    axle_torque = engine_torque * total_ratio * spec.drivetrain_efficiency
    return axle_torque


def split_axle_torque(spec: DrivetrainSpec, total_axle_torque_nm: float) -> tuple[float, float]:
    """Return ``(front_torque, rear_torque)`` given the drivetrain layout."""
    if spec.layout == DrivetrainLayout.FWD:
        return total_axle_torque_nm, 0.0
    if spec.layout == DrivetrainLayout.RWD:
        return 0.0, total_axle_torque_nm
    front = total_axle_torque_nm * spec.front_torque_split
    rear = total_axle_torque_nm * (1.0 - spec.front_torque_split)
    return front, rear


def braking_torque(brake_input: float, mass_kg: float, brake_bias_front: float = 0.62) -> tuple[float, float]:
    """Simple brake model: total decelerating force proportional to pedal
    input and vehicle mass, split front/rear by a fixed bias (front-biased
    braking is standard because braking transfers load forward)."""
    brake_input = max(0.0, min(1.0, brake_input))
    max_brake_force_n = mass_kg * 11.5  # ~1.15g max braking capability
    total = brake_input * max_brake_force_n
    return total * brake_bias_front, total * (1.0 - brake_bias_front)
