"""XR physics engine tests: gravity, collision, grabbing/throwing."""

import pytest

from xr_os.core.math3d import Vector3
from xr_os.physics.engine import RigidBody, StaticPlane, XRPhysicsEngine


def test_gravity_pulls_body_down():
    engine = XRPhysicsEngine()
    body = engine.add_body(RigidBody(position=Vector3(0, 5, 0)))
    for _ in range(10):
        engine.step(1 / 90)
    assert body.position.y < 5.0
    assert body.velocity.y < 0.0


def test_body_rests_on_floor_plane():
    engine = XRPhysicsEngine()
    engine.add_plane(StaticPlane(point=Vector3(0, 0, 0), normal=Vector3(0, 1, 0)))
    body = engine.add_body(RigidBody(position=Vector3(0, 1, 0), radius=0.1, restitution=0.0))
    for _ in range(300):
        engine.step(1 / 90)
    assert body.position.y == pytest.approx(0.1, abs=0.01)


def test_collision_with_floor_produces_contact():
    engine = XRPhysicsEngine()
    engine.add_plane(StaticPlane(point=Vector3(0, 0, 0), normal=Vector3(0, 1, 0)))
    engine.add_body(RigidBody(position=Vector3(0, 0.5, 0), radius=0.1))
    all_contacts = []
    for _ in range(120):
        all_contacts.extend(engine.step(1 / 90))
    assert len(all_contacts) > 0


def test_two_spheres_bounce_apart():
    engine = XRPhysicsEngine(gravity=Vector3.zero())
    a = engine.add_body(RigidBody(position=Vector3(-0.15, 0, 0), velocity=Vector3(1, 0, 0), radius=0.1))
    b = engine.add_body(RigidBody(position=Vector3(0.15, 0, 0), velocity=Vector3(-1, 0, 0), radius=0.1))
    for _ in range(30):
        engine.step(1 / 90)
    assert a.velocity.x < 0.0
    assert b.velocity.x > 0.0


def test_grab_move_and_throw():
    engine = XRPhysicsEngine(gravity=Vector3.zero())
    ball = engine.add_body(RigidBody(position=Vector3.zero(), radius=0.05))
    engine.grab(ball.id, holder_id="right_hand")
    assert ball.is_grabbed

    engine.move_grabbed(ball.id, Vector3(0, 0, 0), dt=1 / 90)
    engine.move_grabbed(ball.id, Vector3(0.1, 0, 0), dt=1 / 90)
    assert ball.velocity.x > 0.0  # tracked velocity while held, ready for a throw

    engine.release(ball.id, throw_velocity=Vector3(5, 0, 0))
    assert not ball.is_grabbed
    assert ball.velocity.as_tuple() == pytest.approx((5.0, 0.0, 0.0))

    engine.step(1 / 90)
    assert ball.position.x > 0.0


def test_static_body_never_moves():
    engine = XRPhysicsEngine()
    static_body = engine.add_body(RigidBody(position=Vector3(0, 1, 0), is_static=True))
    for _ in range(60):
        engine.step(1 / 90)
    assert static_body.position.as_tuple() == pytest.approx((0.0, 1.0, 0.0))


def test_sync_planes_from_spatial_map():
    from xr_os.slam.mapping import Plane, PlaneType

    engine = XRPhysicsEngine()

    class FakeMap:
        planes = [Plane(point=Vector3(0, 0, 0), normal=Vector3(0, 1, 0), plane_type=PlaneType.FLOOR)]

    engine.sync_planes_from_spatial_map(FakeMap())
    assert len(engine.planes) == 1
    assert engine.planes[0].label == "floor"
