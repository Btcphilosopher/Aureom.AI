import math

from apex_horizon_engine.physics.collision import CircleBody, detect_collision, impulse_magnitude, resolve_collision


def test_non_overlapping_bodies_do_not_collide():
    a = CircleBody("a", 0, 0, 1.0, 1000, 0, 0)
    b = CircleBody("b", 10, 0, 1.0, 1000, 0, 0)
    assert detect_collision(a, b) is None


def test_overlapping_bodies_collide_with_correct_normal():
    a = CircleBody("a", 0, 0, 1.5, 1000, 0, 0)
    b = CircleBody("b", 2.0, 0, 1.5, 1000, 0, 0)
    info = detect_collision(a, b)
    assert info is not None
    assert info.penetration_m > 0
    assert math.isclose(info.normal_x, 1.0, abs_tol=1e-6)


def test_resolve_collision_conserves_momentum_roughly():
    a = CircleBody("a", 0, 0, 1.0, 1200, 10.0, 0.0)
    b = CircleBody("b", 1.8, 0, 1.0, 1200, -10.0, 0.0)
    info = detect_collision(a, b)
    momentum_before = a.mass_kg * a.vx + b.mass_kg * b.vx
    resolve_collision(a, b, info, restitution=0.3)
    momentum_after = a.mass_kg * a.vx + b.mass_kg * b.vx
    assert math.isclose(momentum_before, momentum_after, rel_tol=1e-6)
    # A head-on hit should reverse (or at least reduce) each body's velocity.
    assert a.vx < 10.0
    assert b.vx > -10.0


def test_heavier_body_pushes_lighter_body_harder():
    heavy = CircleBody("heavy", 0, 0, 1.0, 5000, 10.0, 0.0)
    light = CircleBody("light", 1.8, 0, 1.0, 800, 0.0, 0.0)
    info = detect_collision(heavy, light)
    resolve_collision(heavy, light, info, restitution=0.2)
    assert light.vx > 0
    assert abs(light.vx) > abs(heavy.vx)


def test_impulse_magnitude_scales_with_speed():
    low = impulse_magnitude(1200, 1200, impact_speed_mps=2.0)
    high = impulse_magnitude(1200, 1200, impact_speed_mps=20.0)
    assert high > low
