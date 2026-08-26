import random

from apex_horizon_engine.ai.adaptive_ai import PlayerStyleModel


def test_repeated_drifting_raises_drift_style_weight():
    model = PlayerStyleModel(_rng=random.Random(0))
    baseline = model.weights["drift"]
    for _ in range(200):
        model.observe_tick(drift_phase="drift", lat_accel_g=0.8, long_accel_g=0.1,
                            off_road=False, near_top_speed=False)
    assert model.weights["drift"] > baseline
    assert model.weights["drift"] > model.weights["offroad"]


def test_event_completion_is_a_stronger_signal_than_a_single_tick():
    model = PlayerStyleModel(_rng=random.Random(0))
    before = model.weights["circuit"]
    model.observe_event_completed("circuit", finished_well=True)
    after_event = model.weights["circuit"]
    model.observe_tick(drift_phase="grip", lat_accel_g=0.6, long_accel_g=0.0,
                        off_road=False, near_top_speed=False)
    after_tick = model.weights["circuit"]
    assert (after_event - before) > abs(after_tick - after_event)


def test_decay_pulls_unobserved_styles_back_toward_neutral():
    model = PlayerStyleModel(_rng=random.Random(0))
    model.weights["drift"] = 0.9
    for _ in range(500):
        model.decay_toward_neutral(dt_s=1.0)
    assert model.weights["drift"] < 0.9
    assert model.weights["drift"] > 0.25  # decays toward 0.3, not to zero


def test_rival_archetype_bias_is_a_probability_distribution():
    model = PlayerStyleModel(_rng=random.Random(0))
    biases = model.rival_archetype_bias()
    assert abs(sum(biases.values()) - 1.0) < 1e-6
    assert all(v >= 0 for v in biases.values())


def test_sample_archetype_returns_a_known_archetype():
    model = PlayerStyleModel(_rng=random.Random(1))
    archetype = model.sample_archetype()
    assert archetype in model.rival_archetype_bias()


def test_drift_focused_player_biases_rival_pool_toward_drift():
    model = PlayerStyleModel(_rng=random.Random(0))
    for _ in range(400):
        model.observe_tick(drift_phase="drift", lat_accel_g=0.9, long_accel_g=0.1,
                            off_road=False, near_top_speed=False)
    biases = model.rival_archetype_bias()
    assert biases["drift_focused"] > biases["rally_specialist"]
