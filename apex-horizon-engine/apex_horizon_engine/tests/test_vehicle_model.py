import math

from apex_horizon_engine.physics.traction_model import SurfaceCondition
from apex_horizon_engine.utils.config import get_vehicle_preset
from apex_horizon_engine.vehicles.vehicle_model import Vehicle, VehicleControls

DT = 1 / 60


def _drive_straight(vehicle_id: str, seconds: float, throttle: float = 1.0):
    vehicle = Vehicle(get_vehicle_preset(vehicle_id))
    condition = SurfaceCondition(base_grip=1.0, wetness=0.0)
    controls = VehicleControls(throttle=throttle)
    telemetry = None
    for _ in range(int(seconds / DT)):
        telemetry = vehicle.step(DT, controls, condition)
    return vehicle, telemetry


def test_full_throttle_accelerates_from_standstill():
    vehicle, telemetry = _drive_straight("meridian_gt_hatch", seconds=8.0)
    assert telemetry.speed_kph > 40.0
    assert vehicle.state.x > 0  # actually moved forward


def test_hypercar_is_faster_than_hatchback_after_launch():
    _, hatch_telemetry = _drive_straight("meridian_gt_hatch", seconds=6.0)
    _, hyper_telemetry = _drive_straight("solace_hypercar", seconds=6.0)
    assert hyper_telemetry.speed_kph > hatch_telemetry.speed_kph


def test_braking_reduces_speed():
    vehicle, telemetry = _drive_straight("ironclad_v8_muscle", seconds=6.0)
    speed_before = telemetry.speed_kph
    condition = SurfaceCondition(base_grip=1.0, wetness=0.0)
    brake_controls = VehicleControls(throttle=0.0, brake=1.0)
    for _ in range(90):
        telemetry = vehicle.step(DT, brake_controls, condition)
    assert telemetry.speed_kph < speed_before


def test_no_input_and_no_motion_stays_essentially_stationary():
    vehicle = Vehicle(get_vehicle_preset("meridian_gt_hatch"))
    condition = SurfaceCondition(base_grip=1.0)
    controls = VehicleControls()
    for _ in range(120):
        telemetry = vehicle.step(DT, controls, condition)
    assert telemetry.speed_kph < 1.0


def test_state_never_produces_nan_over_a_long_run():
    vehicle, telemetry = _drive_straight("arclight_ev_hyper", seconds=15.0)
    s = vehicle.state
    for value in (s.x, s.y, s.vx, s.vy, s.yaw_rate, telemetry.speed_kph, telemetry.rpm):
        assert math.isfinite(value)


def test_hard_cornering_produces_measurable_lateral_g():
    vehicle = Vehicle(get_vehicle_preset("vagrant_drift_spec"))
    condition = SurfaceCondition(base_grip=1.0)
    controls = VehicleControls(throttle=0.8, steering=0.0)
    for _ in range(240):
        vehicle.step(DT, controls, condition)
    controls.steering = 0.8
    max_lat_g = 0.0
    for _ in range(120):
        telemetry = vehicle.step(DT, controls, condition)
        max_lat_g = max(max_lat_g, abs(telemetry.lat_accel_g))
    assert max_lat_g > 0.15


def test_damage_reduces_top_speed_capability():
    from apex_horizon_engine.physics.damage_model import DamageState

    vehicle_healthy, telemetry_healthy = _drive_straight("meridian_gt_hatch", seconds=6.0)

    vehicle_damaged = Vehicle(get_vehicle_preset("meridian_gt_hatch"))
    vehicle_damaged.state.damage = DamageState(body_damage=0.8, engine_damage=0.7)
    condition = SurfaceCondition(base_grip=1.0)
    controls = VehicleControls(throttle=1.0)
    telemetry_damaged = None
    for _ in range(int(6.0 / DT)):
        telemetry_damaged = vehicle_damaged.step(DT, controls, condition)

    assert telemetry_damaged.speed_kph < telemetry_healthy.speed_kph
