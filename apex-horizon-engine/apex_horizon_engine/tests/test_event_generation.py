from apex_horizon_engine.utils.config import WORLD_ZONES
from apex_horizon_engine.world.event_generation import EventGenerator, EventType
from apex_horizon_engine.world.weather_system import WeatherKind


def test_generate_returns_valid_event():
    gen = EventGenerator(seed=1)
    zone = WORLD_ZONES["meridian_city"]
    spec = gen.generate(zone, WeatherKind.CLEAR, reputation_by_discipline={})
    assert isinstance(spec.event_type, EventType)
    assert spec.zone_id == zone.zone_id
    assert spec.rival_count > 0
    assert spec.reward_credits > 0


def test_high_tier_events_gated_behind_reputation():
    gen = EventGenerator(seed=2)
    zone = WORLD_ZONES["silica_flats"]
    low_rep = {"endurance": 0.0}
    seen_types = set()
    for _ in range(200):
        spec = gen.generate(zone, WeatherKind.CLEAR, reputation_by_discipline=low_rep)
        seen_types.add(spec.event_type)
    assert EventType.ENDURANCE not in seen_types  # requires tier 4 (24+ rep)


def test_style_preference_shifts_event_distribution_toward_drift():
    gen = EventGenerator(seed=3)
    zone = WORLD_ZONES["meridian_city"]
    rep = {"street": 20.0, "circuit": 20.0, "drift": 20.0, "offroad": 20.0, "endurance": 20.0}

    def count_drift(style_prefs, n=300):
        counts = 0
        for _ in range(n):
            spec = gen.generate(zone, WeatherKind.CLEAR, rep, style_prefs)
            if spec.event_type == EventType.DRIFT_COMP:
                counts += 1
        return counts

    neutral_count = count_drift({"drift": 0.1, "street": 0.5, "circuit": 0.5, "offroad": 0.1, "endurance": 0.1})
    drift_lover_count = count_drift({"drift": 1.0, "street": 0.1, "circuit": 0.1, "offroad": 0.1, "endurance": 0.1})
    assert drift_lover_count > neutral_count


def test_difficulty_scales_with_discipline_reputation():
    gen = EventGenerator(seed=4)
    zone = WORLD_ZONES["meridian_city"]
    low = gen.generate(zone, WeatherKind.CLEAR, {"street": 0.0})
    high = gen.generate(zone, WeatherKind.CLEAR, {"street": 50.0, "circuit": 50.0, "drift": 50.0,
                                                    "offroad": 50.0, "endurance": 50.0})
    assert high.difficulty >= low.difficulty
