import math

from apex_horizon_engine.core.engine import ApexHorizonEngine
from apex_horizon_engine.core.simulation_loop import run_simulation
from apex_horizon_engine.utils.config import EngineConfig


def test_engine_ticks_without_crashing_and_stays_finite():
    engine = ApexHorizonEngine(EngineConfig(seed=1))
    frames = run_simulation(engine, ticks=600, log_interval=0)
    assert len(frames) == 600
    last = frames[-1]
    assert math.isfinite(last.telemetry.speed_kph)
    assert last.telemetry.speed_kph < 400  # sane upper bound, not a physical max


def test_engine_eventually_starts_an_event():
    engine = ApexHorizonEngine(EngineConfig(seed=2))
    frames = run_simulation(engine, ticks=900, log_interval=0)
    assert any(f.active_event is not None for f in frames)


def test_weather_and_streaming_report_a_real_zone():
    engine = ApexHorizonEngine(EngineConfig(seed=3))
    frame = engine.tick(1 / 60)
    assert frame.zone_name
    assert frame.weather in {"clear", "rain", "storm", "fog", "sandstorm", "snow"}


def test_style_model_updates_over_a_run():
    engine = ApexHorizonEngine(EngineConfig(seed=4))
    run_simulation(engine, ticks=300, log_interval=0)
    assert engine.style_model.sample_count > 0


def test_traffic_population_stays_bounded():
    engine = ApexHorizonEngine(EngineConfig(seed=5))
    run_simulation(engine, ticks=300, log_interval=0)
    assert len(engine.traffic.active) <= 24


def test_police_heat_rises_with_registered_infractions():
    engine = ApexHorizonEngine(EngineConfig(seed=6))
    assert engine.police.heat == 0.0
    engine.police.register_infraction("collision", severity=1.0)
    assert engine.police.heat > 0.0


def test_credits_never_go_negative_over_a_run():
    engine = ApexHorizonEngine(EngineConfig(seed=7))
    run_simulation(engine, ticks=1200, log_interval=0)
    assert engine.credits.balance >= 0
