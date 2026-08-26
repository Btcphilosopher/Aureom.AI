from apex_horizon_engine.core.engine import ApexHorizonEngine
from apex_horizon_engine.core.simulation_loop import run_simulation
from apex_horizon_engine.multiplayer.sync_system import lockstep_checksum
from apex_horizon_engine.utils.config import EngineConfig


def _run(seed: int, ticks: int) -> str:
    engine = ApexHorizonEngine(EngineConfig(seed=seed))
    run_simulation(engine, ticks=ticks, log_interval=0)
    return lockstep_checksum(engine.tick_count, {"player": engine.player_vehicle})


def test_same_seed_produces_identical_checksum():
    assert _run(seed=100, ticks=400) == _run(seed=100, ticks=400)


def test_different_seeds_usually_diverge():
    # Not a hard physical guarantee, but with different world RNG streams
    # driving weather/events/traffic, 400 ticks is more than enough for
    # two different seeds to diverge in practice.
    assert _run(seed=1, ticks=400) != _run(seed=2, ticks=400)


def test_state_syncer_diff_only_reports_changed_fields():
    from apex_horizon_engine.multiplayer.sync_system import StateSyncer

    syncer = StateSyncer()
    first = syncer.diff("veh_1", tick=0, current={"x": 1.0, "y": 2.0, "gear": 1})
    assert set(first.changed_fields) == {"x", "y", "gear"}  # nothing seen before -> everything is "changed"

    second = syncer.diff("veh_1", tick=1, current={"x": 1.0, "y": 2.5, "gear": 1})
    assert "x" not in second.changed_fields
    assert "gear" not in second.changed_fields
    assert second.changed_fields["y"] == 2.5
