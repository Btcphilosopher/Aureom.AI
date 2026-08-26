from apex_horizon_engine.physics.drift_system import DriftPhase, DriftState, update_drift_state


def test_pointing_straight_stays_in_grip_phase():
    state = DriftState()
    for _ in range(30):
        update_drift_state(state, dt=1 / 60, vx_mps=20.0, vy_mps=0.0, rear_slip_severity=0.1,
                            throttle=0.5, speed_mps=20.0)
    assert state.phase == DriftPhase.GRIP


def test_large_slip_angle_with_grip_loss_enters_drift():
    state = DriftState()
    for _ in range(60):
        update_drift_state(state, dt=1 / 60, vx_mps=15.0, vy_mps=8.0, rear_slip_severity=0.6,
                            throttle=0.7, speed_mps=17.0)
    assert state.phase in (DriftPhase.DRIFT, DriftPhase.TRANSITION)
    assert state.drift_angle_deg > 0


def test_extreme_angle_triggers_spinout():
    state = DriftState()
    update_drift_state(state, dt=1 / 60, vx_mps=1.0, vy_mps=20.0, rear_slip_severity=0.9,
                        throttle=0.5, speed_mps=20.0)
    assert state.phase == DriftPhase.SPINOUT


def test_scoring_accumulates_while_drifting_and_banks_on_exit():
    state = DriftState()
    for _ in range(120):
        update_drift_state(state, dt=1 / 60, vx_mps=15.0, vy_mps=9.0, rear_slip_severity=0.6,
                            throttle=0.8, speed_mps=17.0)
    assert state.current_run_score > 0
    for _ in range(60):
        update_drift_state(state, dt=1 / 60, vx_mps=20.0, vy_mps=0.0, rear_slip_severity=0.0,
                            throttle=0.3, speed_mps=20.0)
    assert state.total_score > 0
    assert state.current_run_score == 0
