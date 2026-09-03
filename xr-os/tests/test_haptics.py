"""Haptic engine tests: COLLISION -> PHYSICS -> HAPTIC EVENT -> ACTUATOR."""

import pytest

from xr_os.core.math3d import Vector3
from xr_os.haptics.haptics import ActuatorTarget, HapticEngine, LoggingActuator
from xr_os.physics.engine import CollisionContact, RigidBody, StaticPlane, XRPhysicsEngine


def test_direct_trigger_reaches_actuator():
    engine = HapticEngine()
    actuator = LoggingActuator(ActuatorTarget.RIGHT_CONTROLLER)
    engine.register_actuator(actuator)

    engine.trigger(ActuatorTarget.RIGHT_CONTROLLER, intensity=0.5, duration_ms=40)
    assert actuator.last() is not None
    assert actuator.last().intensity == pytest.approx(0.5)


def test_trigger_clamps_intensity_to_unit_range():
    engine = HapticEngine()
    actuator = LoggingActuator(ActuatorTarget.LEFT_HAND_GLOVE)
    engine.register_actuator(actuator)
    engine.trigger(ActuatorTarget.LEFT_HAND_GLOVE, intensity=5.0)
    assert actuator.last().intensity == 1.0


def test_collision_pipeline_routes_to_bound_actuator():
    engine = HapticEngine()
    actuator = LoggingActuator(ActuatorTarget.RIGHT_CONTROLLER)
    engine.register_actuator(actuator)
    engine.bind_body("hand_body", ActuatorTarget.RIGHT_CONTROLLER)

    contact = CollisionContact(body_id="hand_body", other_id="wall", point=Vector3(0, 0, 0), normal=Vector3(0, 1, 0), impulse=2.0)
    events = engine.handle_collisions([contact])
    assert len(events) == 1
    assert actuator.last() is events[0]


def test_unbound_body_produces_no_haptic_event():
    engine = HapticEngine()
    contact = CollisionContact(body_id="unbound", other_id="wall", point=Vector3.zero(), normal=Vector3(0, 1, 0), impulse=1.0)
    assert engine.handle_collisions([contact]) == []


def test_real_physics_collision_drives_haptics_end_to_end():
    physics = XRPhysicsEngine()
    physics.add_plane(StaticPlane(point=Vector3.zero(), normal=Vector3(0, 1, 0)))
    ball = physics.add_body(RigidBody(position=Vector3(0, 0.15, 0), radius=0.1))

    haptics = HapticEngine()
    actuator = LoggingActuator(ActuatorTarget.RIGHT_CONTROLLER)
    haptics.register_actuator(actuator)
    haptics.bind_body(ball.id, ActuatorTarget.RIGHT_CONTROLLER)

    for _ in range(60):
        contacts = physics.step(1 / 90)
        haptics.handle_collisions(contacts)

    assert len(actuator.history) > 0
    assert all(0.0 <= e.intensity <= 1.0 for e in actuator.history)
