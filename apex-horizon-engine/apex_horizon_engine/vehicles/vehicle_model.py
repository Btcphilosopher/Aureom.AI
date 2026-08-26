"""
Vehicle assembly: wires drivetrain + suspension + aero + tires + physics
traction/damage into one rigid-body vehicle that can be stepped forward in
time.

Model shape: a planar (2D) rigid body with a two-axle ("bicycle model")
tire layout. Each axle additionally gets its own rotational wheel-speed
state integrated from drive/brake torque against the tire's reaction
force -- this is what makes wheelspin, lockup, and traction loss emerge
from the sim instead of being faked: pin the throttle on a loose surface
and the driven axle's wheel speed will genuinely run away from the
vehicle's ground speed until the tire model claws grip back.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from apex_horizon_engine.physics.damage_model import (
    DamageState, apply_offroad_wear, axle_grip_multiplier,
    drag_multiplier, steering_authority_multiplier, torque_multiplier,
)
from apex_horizon_engine.physics.drift_system import DriftState, update_drift_state
from apex_horizon_engine.physics.traction_model import SurfaceCondition, resolve_axle_forces, rolling_resistance_force_n
from apex_horizon_engine.utils.config import VehicleSpec
from apex_horizon_engine.vehicles.aero_system import compute_aero_forces
from apex_horizon_engine.vehicles.drivetrain import DrivetrainState, braking_torque, split_axle_torque, step_drivetrain
from apex_horizon_engine.vehicles.suspension import (
    SuspensionState, axle_normal_loads, lateral_transfer_n, static_axle_loads, update_suspension,
)
from apex_horizon_engine.vehicles.tire_model import (
    WheelTireState, slip_ratio_from_speeds,
)

GRAVITY = 9.81
WHEEL_INERTIA_KG_M2_DEFAULT = 1.6
MAX_STEER_DEG = 32.0


def _clamp(value: float, lo: float, hi: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return max(lo, min(hi, value))


@dataclass
class VehicleControls:
    throttle: float = 0.0   # 0..1
    brake: float = 0.0      # 0..1
    steering: float = 0.0   # -1..1 (left..right)
    handbrake: bool = False


@dataclass
class TelemetrySample:
    speed_kph: float
    rpm: float
    gear: int
    front_slip_severity: float
    rear_slip_severity: float
    front_load_n: float
    rear_load_n: float
    roll_angle_deg: float
    drift_phase: str
    drift_angle_deg: float
    long_accel_g: float
    lat_accel_g: float
    tire_temp_front_c: float
    tire_temp_rear_c: float


@dataclass
class VehicleState:
    x: float = 0.0
    y: float = 0.0
    heading_rad: float = 0.0
    vx: float = 0.0   # body-frame forward speed (m/s)
    vy: float = 0.0   # body-frame lateral speed (m/s)
    yaw_rate: float = 0.0  # rad/s

    w_front: float = 0.0   # front axle wheel angular speed, rad/s
    w_rear: float = 0.0

    drivetrain: DrivetrainState = field(default_factory=DrivetrainState)
    suspension: SuspensionState = field(default_factory=SuspensionState)
    tire_front: WheelTireState = field(default_factory=WheelTireState)
    tire_rear: WheelTireState = field(default_factory=WheelTireState)
    drift: DriftState = field(default_factory=DriftState)
    damage: DamageState = field(default_factory=DamageState)

    odometer_m: float = 0.0
    prev_ax: float = 0.0
    prev_ay: float = 0.0

    @property
    def speed_mps(self) -> float:
        return math.hypot(self.vx, self.vy)


class Vehicle:
    """A spec (what the car *is*) bound to a state (what the car is
    *doing right now*). Multiple ``Vehicle`` instances can share the same
    (read-only) ``VehicleSpec`` -- see ``utils.config.get_vehicle_preset``
    for cloning semantics."""

    def __init__(self, spec: VehicleSpec, state: VehicleState | None = None):
        self.spec = spec
        self.state = state or VehicleState()
        front_dist_frac = 1.0 - spec.weight_dist_front
        self.dist_cg_to_front_m = spec.wheelbase_m * front_dist_frac
        self.dist_cg_to_rear_m = spec.wheelbase_m * spec.weight_dist_front
        self.wheel_radius_m = max(0.28, min(0.40, 0.30 + spec.mass_kg * 0.00006))
        self.yaw_inertia = spec.mass_kg * (spec.wheelbase_m * 0.5) ** 2 * 1.15
        # Lumped rotational inertia of both wheels on an axle. Scaled gently
        # with vehicle mass (bigger cars run bigger/heavier wheels).
        self.wheel_inertia = 1.9 + spec.mass_kg * 0.0009

    def step(self, dt: float, controls: VehicleControls, condition: SurfaceCondition,
              ambient_temp_c: float = 20.0, substeps: int = 4) -> TelemetrySample:
        """Advance the vehicle by ``dt`` seconds.

        Internally split into ``substeps`` finer integration steps. Wheel
        rotational dynamics are numerically stiff (small inertia against
        four-figure torques at low gear), so integrating them at the
        outer 60 Hz tick alone can ring/oscillate; a handful of substeps
        keeps that subsystem stable without slowing down the rest of the
        engine, which only ever observes the aggregate result.
        """
        sample = None
        sub_dt = dt / max(1, substeps)
        for _ in range(max(1, substeps)):
            sample = self._integrate(sub_dt, controls, condition, ambient_temp_c)
        return sample

    def _integrate(self, dt: float, controls: VehicleControls, condition: SurfaceCondition,
                    ambient_temp_c: float = 20.0) -> TelemetrySample:
        s = self.state
        spec = self.spec

        steer_authority = steering_authority_multiplier(s.damage)
        max_steer_rad = math.radians(MAX_STEER_DEG) * (1.0 - 0.45 * min(1.0, s.speed_mps / 40.0))
        delta = controls.steering * max_steer_rad * steer_authority

        aero = compute_aero_forces(spec.aero, s.speed_mps, drag_multiplier(s.damage))
        static_loads = static_axle_loads(spec.mass_kg, spec.weight_dist_front)
        axle_loads = axle_normal_loads(
            static_loads, spec.mass_kg, spec.cg_height_m, spec.wheelbase_m,
            s.prev_ax, aero.downforce_front_n, aero.downforce_rear_n,
        )

        lat_transfer = lateral_transfer_n(spec.mass_kg, spec.cg_height_m, spec.track_width_m,
                                           s.prev_ay, spec.suspension.anti_roll_bar)
        update_suspension(spec.suspension, s.suspension, dt, s.prev_ay, s.prev_ax)

        driven_wheel_surface_speed = (
            s.w_front * self.wheel_radius_m * spec.drivetrain.front_torque_split
            + s.w_rear * self.wheel_radius_m * (1.0 - spec.drivetrain.front_torque_split)
        ) if spec.drivetrain.layout.value == "AWD" else (
            s.w_front * self.wheel_radius_m if spec.drivetrain.layout.value == "FWD" else s.w_rear * self.wheel_radius_m
        )

        axle_torque = step_drivetrain(spec.drivetrain, spec.engine, s.drivetrain, dt,
                                       controls.throttle, driven_wheel_surface_speed, self.wheel_radius_m)
        axle_torque *= torque_multiplier(s.damage)
        drive_front_nm, drive_rear_nm = split_axle_torque(spec.drivetrain, axle_torque)

        brake_front_n, brake_rear_n = braking_torque(controls.brake, spec.mass_kg)
        if controls.handbrake:
            brake_rear_n += spec.mass_kg * 4.0
        brake_front_nm = brake_front_n * self.wheel_radius_m
        brake_rear_nm = brake_rear_n * self.wheel_radius_m

        slip_ratio_f = slip_ratio_from_speeds(s.w_front, self.wheel_radius_m, s.vx)
        slip_ratio_r = slip_ratio_from_speeds(s.w_rear, self.wheel_radius_m, s.vx)

        alpha_f = delta - math.atan2(s.vy + self.dist_cg_to_front_m * s.yaw_rate, max(0.05, abs(s.vx)))
        alpha_r = -math.atan2(s.vy - self.dist_cg_to_rear_m * s.yaw_rate, max(0.05, abs(s.vx)))
        if s.vx < 0:
            alpha_f, alpha_r = -alpha_f, -alpha_r

        fx_f, fy_f, sev_f = resolve_axle_forces(spec.tires, s.tire_front, axle_loads.front_n,
                                                 slip_ratio_f, math.degrees(alpha_f), condition)
        fx_r, fy_r, sev_r = resolve_axle_forces(spec.tires, s.tire_rear, axle_loads.rear_n,
                                                 slip_ratio_r, math.degrees(alpha_r), condition)
        fx_f *= axle_grip_multiplier(s.damage, "front")
        fx_r *= axle_grip_multiplier(s.damage, "rear")
        fy_f *= axle_grip_multiplier(s.damage, "front")
        fy_r *= axle_grip_multiplier(s.damage, "rear")

        # -- wheel rotational dynamics (this is where wheelspin/lockup emerge) --
        rr_f = rolling_resistance_force_n(axle_loads.front_n) * self.wheel_radius_m
        rr_r = rolling_resistance_force_n(axle_loads.rear_n) * self.wheel_radius_m
        dw_f = (drive_front_nm - fx_f * self.wheel_radius_m
                - math.copysign(min(brake_front_nm, abs(s.w_front) * self.wheel_inertia / max(dt, 1e-4) + 1),
                                 s.w_front if abs(s.w_front) > 0.01 else 1.0)
                - math.copysign(rr_f, s.w_front if abs(s.w_front) > 0.01 else 1.0)) / self.wheel_inertia
        dw_r = (drive_rear_nm - fx_r * self.wheel_radius_m
                - math.copysign(min(brake_rear_nm, abs(s.w_rear) * self.wheel_inertia / max(dt, 1e-4) + 1),
                                 s.w_rear if abs(s.w_rear) > 0.01 else 1.0)
                - math.copysign(rr_r, s.w_rear if abs(s.w_rear) > 0.01 else 1.0)) / self.wheel_inertia
        s.w_front += dw_f * dt
        s.w_rear += dw_r * dt
        if abs(s.w_front) < 0.02 and drive_front_nm < 1 and brake_front_nm > 5:
            s.w_front = 0.0
        if abs(s.w_rear) < 0.02 and drive_rear_nm < 1 and brake_rear_nm > 5:
            s.w_rear = 0.0

        # -- body forces (front axle forces rotated into the body frame by steering) --
        fx_body_f = fx_f * math.cos(delta) - fy_f * math.sin(delta)
        fy_body_f = fx_f * math.sin(delta) + fy_f * math.cos(delta)
        fx_body_r, fy_body_r = fx_r, fy_r

        drag_signed = -aero.drag_n * (1 if s.vx >= 0 else -1)
        rr_total = -rolling_resistance_force_n(axle_loads.front_n + axle_loads.rear_n) * (1 if s.vx >= 0 else -1)

        fx_total = fx_body_f + fx_body_r + drag_signed + rr_total
        fy_total = fy_body_f + fy_body_r
        yaw_moment = (self.dist_cg_to_front_m * fy_body_f) - (self.dist_cg_to_rear_m * fy_body_r)

        # Specific force (what an onboard accelerometer -- or the driver's
        # inner ear -- actually feels) vs. coordinate acceleration (what
        # the ODE needs to integrate vx/vy in a rotating body frame) are
        # different things: coordinate accel includes the Coriolis-like
        # vx*yaw_rate / vy*yaw_rate coupling term, specific force doesn't.
        # Weight transfer and telemetry both want specific force; only the
        # velocity integration wants the coupled coordinate version.
        ax_felt = fx_total / spec.mass_kg
        ay_felt = fy_total / spec.mass_kg
        ax = ax_felt + s.vy * s.yaw_rate
        ay = ay_felt - s.vx * s.yaw_rate
        yaw_accel = yaw_moment / self.yaw_inertia

        s.vx += ax * dt
        s.vy += ay * dt
        s.yaw_rate += yaw_accel * dt
        s.prev_ax, s.prev_ay = ax_felt, ay_felt

        # Defensive numerical safety rail. The stiff wheel/tire feedback
        # loop (and, in ``core.engine``, collision impulses from a packed
        # traffic cluster) can occasionally push a substep outside any
        # physically sane envelope; clamp state to generous-but-finite
        # bounds and recover from an outright NaN/Inf rather than letting
        # it propagate silently through the rest of the simulation.
        s.vx = _clamp(s.vx, -105.0, 105.0)
        s.vy = _clamp(s.vy, -35.0, 35.0)
        s.yaw_rate = _clamp(s.yaw_rate, -10.0, 10.0)
        s.w_front = _clamp(s.w_front, -900.0, 900.0)
        s.w_rear = _clamp(s.w_rear, -900.0, 900.0)
        if not all(math.isfinite(v) for v in (s.vx, s.vy, s.yaw_rate, s.w_front, s.w_rear)):
            s.vx = s.vy = s.yaw_rate = s.w_front = s.w_rear = 0.0

        s.heading_rad += s.yaw_rate * dt
        s.x += (s.vx * math.cos(s.heading_rad) - s.vy * math.sin(s.heading_rad)) * dt
        s.y += (s.vx * math.sin(s.heading_rad) + s.vy * math.cos(s.heading_rad)) * dt
        s.odometer_m += s.speed_mps * dt

        s.tire_front.step_wear(dt, s.speed_mps, sev_f, spec.tires)
        s.tire_rear.step_wear(dt, s.speed_mps, sev_r, spec.tires)
        s.tire_front.step_temperature(dt, sev_f, ambient_temp_c)
        s.tire_rear.step_temperature(dt, sev_r, ambient_temp_c)

        apply_offroad_wear(s.damage, dt, condition.off_road, s.speed_mps)

        update_drift_state(s.drift, dt, s.vx, s.vy, sev_r, controls.throttle, s.speed_mps)

        return TelemetrySample(
            speed_kph=s.speed_mps * 3.6,
            rpm=s.drivetrain.rpm,
            gear=s.drivetrain.gear_index,
            front_slip_severity=sev_f,
            rear_slip_severity=sev_r,
            front_load_n=axle_loads.front_n,
            rear_load_n=axle_loads.rear_n,
            roll_angle_deg=math.degrees(s.suspension.roll_angle_rad),
            drift_phase=s.drift.phase.value,
            drift_angle_deg=s.drift.drift_angle_deg,
            long_accel_g=ax_felt / GRAVITY,
            lat_accel_g=ay_felt / GRAVITY,
            tire_temp_front_c=s.tire_front.temperature_c,
            tire_temp_rear_c=s.tire_rear.temperature_c,
        )
