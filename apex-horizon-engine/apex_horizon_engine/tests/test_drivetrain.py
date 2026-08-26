from apex_horizon_engine.utils.config import get_vehicle_preset
from apex_horizon_engine.vehicles.drivetrain import (
    DrivetrainState, braking_torque, split_axle_torque, step_drivetrain,
)


def test_fwd_layout_sends_all_torque_to_front():
    spec = get_vehicle_preset("meridian_gt_hatch")
    front, rear = split_axle_torque(spec.drivetrain, 500.0)
    assert front == 500.0
    assert rear == 0.0


def test_rwd_layout_sends_all_torque_to_rear():
    spec = get_vehicle_preset("ironclad_v8_muscle")
    front, rear = split_axle_torque(spec.drivetrain, 500.0)
    assert front == 0.0
    assert rear == 500.0


def test_awd_layout_splits_torque_both_axles():
    spec = get_vehicle_preset("solace_hypercar")
    front, rear = split_axle_torque(spec.drivetrain, 500.0)
    assert front > 0
    assert rear > 0
    assert abs((front + rear) - 500.0) < 1e-6


def test_braking_biases_toward_front_axle():
    front, rear = braking_torque(brake_input=1.0, mass_kg=1400)
    assert front > rear


def test_zero_throttle_produces_little_or_no_axle_torque():
    spec = get_vehicle_preset("meridian_gt_hatch")
    state = DrivetrainState()
    torque = step_drivetrain(spec.drivetrain, spec.engine, state, dt=1 / 60, throttle=0.0, speed_mps=0.0)
    assert torque == 0.0


def test_shifting_interrupts_torque_delivery():
    spec = get_vehicle_preset("meridian_gt_hatch")
    state = DrivetrainState(gear_index=1, time_since_shift_s=10.0)
    # A wheel speed consistent with near-redline RPM in 1st gear, held for
    # a couple dozen ticks so the flywheel-lag smoothing has time to catch
    # up to the target before checking that it actually triggers a shift.
    for _ in range(40):
        step_drivetrain(spec.drivetrain, spec.engine, state, dt=1 / 60, throttle=1.0, speed_mps=19.0)
        if state.shifting:
            break
    assert state.shifting is True
    # The tick *after* a shift begins is when torque delivery is actually
    # cut (the triggering tick itself still returns that tick's torque).
    torque_mid_shift = step_drivetrain(spec.drivetrain, spec.engine, state, dt=1 / 60, throttle=1.0, speed_mps=19.0)
    assert torque_mid_shift == 0.0
