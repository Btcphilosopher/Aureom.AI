import math

from apex_horizon_engine.utils.config import TireCompound
from apex_horizon_engine.vehicles.tire_model import (
    WheelTireState, compute_tire_forces, slip_angle_from_velocity, slip_ratio_from_speeds,
)

COMPOUND = TireCompound(name="Test", mu_peak=1.1, peak_slip_ratio=0.13, peak_slip_angle_deg=8.0, wear_rate=0.01)


def test_zero_slip_gives_zero_force():
    wheel = WheelTireState()
    fx, fy, sev = compute_tire_forces(COMPOUND, wheel, normal_load_n=6000, slip_ratio=0.0,
                                       slip_angle_deg=0.0, surface_grip_mult=1.0)
    assert abs(fx) < 1e-6
    assert abs(fy) < 1e-6
    assert sev == 0.0


def test_force_increases_then_saturates_past_peak_slip():
    wheel = WheelTireState()
    fx_at_peak, _, _ = compute_tire_forces(COMPOUND, wheel, 6000, slip_ratio=COMPOUND.peak_slip_ratio,
                                            slip_angle_deg=0.0, surface_grip_mult=1.0)
    fx_deep_slip, _, _ = compute_tire_forces(COMPOUND, wheel, 6000, slip_ratio=COMPOUND.peak_slip_ratio * 6,
                                              slip_angle_deg=0.0, surface_grip_mult=1.0)
    # Deep slip never produces *more* longitudinal force than the peak.
    assert fx_deep_slip <= fx_at_peak + 1e-6
    # But it doesn't collapse to zero either -- there's a sliding floor.
    assert fx_deep_slip > 0.0


def test_friction_ellipse_caps_combined_force():
    wheel = WheelTireState()
    fx, fy, _ = compute_tire_forces(COMPOUND, wheel, normal_load_n=6000,
                                     slip_ratio=COMPOUND.peak_slip_ratio,
                                     slip_angle_deg=COMPOUND.peak_slip_angle_deg,
                                     surface_grip_mult=1.0)
    fmax = COMPOUND.mu_peak * 6000 * 1.02  # small tolerance
    assert math.hypot(fx, fy) <= fmax


def test_surface_grip_scales_force_linearly_at_low_slip():
    wheel = WheelTireState()
    fx_dry, _, _ = compute_tire_forces(COMPOUND, wheel, 6000, slip_ratio=0.02, slip_angle_deg=0.0,
                                        surface_grip_mult=1.0)
    fx_wet, _, _ = compute_tire_forces(COMPOUND, wheel, 6000, slip_ratio=0.02, slip_angle_deg=0.0,
                                        surface_grip_mult=0.5)
    assert fx_wet == fx_dry * 0.5


def test_slip_ratio_sign_matches_wheelspin_vs_lockup():
    # Wheel spinning faster than the ground -> positive slip ratio.
    assert slip_ratio_from_speeds(wheel_angular_speed_rad_s=50.0, wheel_radius_m=0.33, road_speed_mps=10.0) > 0
    # Wheel locked (near-zero rotation) while still moving -> negative slip ratio.
    assert slip_ratio_from_speeds(wheel_angular_speed_rad_s=0.0, wheel_radius_m=0.33, road_speed_mps=10.0) < 0


def test_slip_angle_zero_when_moving_straight():
    assert abs(slip_angle_from_velocity(lateral_mps=0.0, longitudinal_mps=20.0)) < 1e-6


def test_wheel_heats_up_under_sustained_slip_and_cools_when_idle():
    wheel = WheelTireState(temperature_c=20.0)
    for _ in range(200):
        wheel.step_temperature(dt=1 / 60, slip_severity=1.0, ambient_c=20.0)
    hot_temp = wheel.temperature_c
    assert hot_temp > 25.0

    for _ in range(600):
        wheel.step_temperature(dt=1 / 60, slip_severity=0.0, ambient_c=20.0)
    assert wheel.temperature_c < hot_temp
