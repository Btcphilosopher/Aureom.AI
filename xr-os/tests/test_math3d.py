"""Spatial mathematics tests: Vector3, Quaternion, Transform."""

import math

import pytest

from xr_os.core.math3d import Quaternion, Transform, Vector3


def test_vector_add_sub_scale():
    a = Vector3(1, 2, 3)
    b = Vector3(4, 5, 6)
    assert (a + b).as_tuple() == (5.0, 7.0, 9.0)
    assert (b - a).as_tuple() == (3.0, 3.0, 3.0)
    assert (a * 2).as_tuple() == (2.0, 4.0, 6.0)


def test_vector_length_and_normalize():
    v = Vector3(3, 4, 0)
    assert v.length() == pytest.approx(5.0)
    n = v.normalized()
    assert n.length() == pytest.approx(1.0)


def test_vector_dot_cross():
    x = Vector3(1, 0, 0)
    y = Vector3(0, 1, 0)
    assert x.dot(y) == 0.0
    assert x.cross(y).as_tuple() == pytest.approx((0.0, 0.0, 1.0))


def test_vector_distance_and_lerp():
    a = Vector3(0, 0, 0)
    b = Vector3(2, 0, 0)
    assert a.distance_to(b) == pytest.approx(2.0)
    mid = a.lerp(b, 0.5)
    assert mid.as_tuple() == pytest.approx((1.0, 0.0, 0.0))


def test_quaternion_identity_rotates_nothing():
    q = Quaternion.identity()
    v = Vector3(1, 2, 3)
    result = q.rotate(v)
    assert result.as_tuple() == pytest.approx(v.as_tuple())


def test_quaternion_90deg_yaw_rotates_forward_to_right():
    q = Quaternion.from_axis_angle(Vector3(0, 1, 0), math.pi / 2)
    forward = Vector3(0, 0, -1)
    rotated = q.rotate(forward)
    assert rotated.as_tuple() == pytest.approx((-1.0, 0.0, 0.0), abs=1e-6)


def test_quaternion_conjugate_undoes_rotation():
    q = Quaternion.from_axis_angle(Vector3(0, 1, 0), 1.234)
    v = Vector3(1, 0.5, -0.25)
    rotated = q.rotate(v)
    restored = q.conjugate().rotate(rotated)
    assert restored.as_tuple() == pytest.approx(v.as_tuple(), abs=1e-9)


def test_quaternion_slerp_at_endpoints():
    a = Quaternion.identity()
    b = Quaternion.from_axis_angle(Vector3(0, 1, 0), math.pi / 2)
    assert a.slerp(b, 0.0).as_tuple() == pytest.approx(a.as_tuple())
    assert a.slerp(b, 1.0).as_tuple() == pytest.approx(b.as_tuple())


def test_transform_combine_translates_child_in_parent_space():
    parent = Transform(Vector3(1, 0, 0), Quaternion.from_axis_angle(Vector3(0, 1, 0), math.pi / 2))
    child = Transform(Vector3(1, 0, 0))  # 1m along local +X
    world = parent.combine(child)
    # parent faces -X after a +90deg yaw of +X axis rotated: local +X -> world -Z
    assert world.position.as_tuple() == pytest.approx((1.0, 0.0, -1.0), abs=1e-6)


def test_transform_inverse_round_trips():
    t = Transform(Vector3(2, 3, 4), Quaternion.from_axis_angle(Vector3(0, 1, 0), 0.7))
    point = Vector3(1, 1, 1)
    world_point = t.transform_point(point)
    local_point = t.inverse().transform_point(world_point)
    assert local_point.as_tuple() == pytest.approx(point.as_tuple(), abs=1e-9)
