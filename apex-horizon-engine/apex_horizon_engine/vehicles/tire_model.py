"""
Per-wheel tire force model.

Implements a simplified "magic formula" slip curve (grip rises smoothly
from zero to a peak at the compound's characteristic slip value, then
falls off toward a sliding-friction floor past the peak) combined through
a friction ellipse so longitudinal and lateral demand compete for the same
finite contact patch -- exactly the mechanism that makes trail-braking
into a corner, or flooring the throttle mid-corner, cost you grip in the
other direction. Temperature and wear both scale the available peak
directly, so an underheated tire on lap 1 and a cooked one on lap 20
behave differently without either being hard-coded.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from apex_horizon_engine.utils.config import TireCompound

GRAVITY = 9.81


@dataclass
class WheelTireState:
    """Mutable, per-wheel runtime state -- one of these lives per corner
    of the car inside ``vehicles.vehicle_model.VehicleState``."""

    temperature_c: float = 20.0
    wear_fraction: float = 0.0     # 0 = fresh, 1 = fully worn (grip floor)
    distance_km: float = 0.0

    def grip_multiplier(self, compound: TireCompound) -> float:
        temp_delta = abs(self.temperature_c - compound.optimal_temp_c)
        temp_mult = max(0.55, 1.0 - compound.temp_sensitivity * temp_delta)
        wear_mult = max(0.5, 1.0 - self.wear_fraction * 0.5)
        return temp_mult * wear_mult

    def step_wear(self, dt: float, speed_mps: float, slip_severity: float, compound: TireCompound) -> None:
        self.distance_km += speed_mps * dt / 1000.0
        wear_this_tick = compound.wear_rate * (speed_mps * dt / 1000.0) * (0.4 + 1.6 * slip_severity)
        self.wear_fraction = min(1.0, self.wear_fraction + wear_this_tick)

    def step_temperature(self, dt: float, slip_severity: float, ambient_c: float) -> None:
        heat_gain = slip_severity * 38.0 * dt           # friction work heats the tire
        cooling = (self.temperature_c - ambient_c) * 0.35 * dt
        self.temperature_c += heat_gain - cooling
        self.temperature_c = max(ambient_c, min(self.temperature_c, 160.0))


def _slip_curve(x: float) -> float:
    """Normalized grip fraction vs. ``slip / peak_slip``. Rises smoothly
    to 1.0 at x=1 (the magic-formula "hump"), then relaxes toward a
    sliding-friction floor as slip keeps increasing past the optimum --
    this is what makes an over-slipped wheel keep losing grip instead of
    the naive (and wrong) "more slip = more force" model."""
    sign = 1.0 if x >= 0 else -1.0
    ax = abs(x)
    if ax <= 1.0:
        frac = math.sin(math.pi / 2.0 * ax)
    else:
        over = ax - 1.0
        frac = max(0.70, 1.0 - 0.35 * over)
    return sign * frac


def compute_tire_forces(
    compound: TireCompound,
    wheel: WheelTireState,
    normal_load_n: float,
    slip_ratio: float,
    slip_angle_deg: float,
    surface_grip_mult: float,
) -> tuple[float, float, float]:
    """Return ``(Fx_n, Fy_n, slip_severity)`` for one wheel.

    ``surface_grip_mult`` folds in road surface + weather (wet tarmac,
    sand, gravel...) supplied by ``physics.traction_model``.
    """
    if normal_load_n <= 0:
        return 0.0, 0.0, 0.0

    mu_effective = compound.mu_peak * wheel.grip_multiplier(compound) * surface_grip_mult
    fmax = mu_effective * normal_load_n

    x_long = slip_ratio / max(1e-4, compound.peak_slip_ratio)
    x_lat = slip_angle_deg / max(1e-4, compound.peak_slip_angle_deg)

    fx_desired = _slip_curve(x_long) * fmax
    fy_desired = _slip_curve(x_lat) * fmax

    # Friction ellipse: the two demands share one finite contact patch.
    magnitude = math.hypot(fx_desired, fy_desired)
    if magnitude > fmax and magnitude > 1e-6:
        scale = fmax / magnitude
        fx_desired *= scale
        fy_desired *= scale

    slip_severity = min(1.0, math.hypot(x_long, x_lat) / 1.4)
    return fx_desired, fy_desired, slip_severity


def slip_ratio_from_speeds(wheel_angular_speed_rad_s: float, wheel_radius_m: float, road_speed_mps: float) -> float:
    """Standard SAE slip ratio: 0 = pure rolling, +1 = full wheelspin,
    -1 = full lockup. ``wheel_angular_speed_rad_s`` is the wheel's spin
    rate in radians/second (not RPM, not revolutions/second)."""
    wheel_surface_speed = wheel_angular_speed_rad_s * wheel_radius_m
    denom = max(0.5, abs(road_speed_mps))
    return (wheel_surface_speed - road_speed_mps) / denom


def slip_angle_from_velocity(lateral_mps: float, longitudinal_mps: float) -> float:
    """Slip angle in degrees between the wheel's heading and its actual
    velocity vector at the contact patch."""
    if abs(longitudinal_mps) < 0.3:
        longitudinal_mps = 0.3 if longitudinal_mps >= 0 else -0.3
    return math.degrees(math.atan2(lateral_mps, abs(longitudinal_mps)))
