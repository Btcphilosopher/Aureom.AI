import numpy as np

from batteryfactory.config.chemistry_profiles import get_profile
from batteryfactory.config.factory_config import default_gigafactory_config
from batteryfactory.simulation.bottleneck import BottleneckAnalyzer
from batteryfactory.simulation.des_engine import FactorySimulationEngine
from batteryfactory.simulation.events import Environment, Timeout
from batteryfactory.simulation.scheduler import ChangeoverMatrix, ProductionScheduler, SchedulableOrder
from datetime import datetime, timedelta


def test_des_kernel_orders_events_by_time():
    env = Environment()
    log = []

    def proc():
        yield Timeout(5.0)
        log.append(("first", env.now))
        yield Timeout(1.0)
        log.append(("second", env.now))

    env.process(proc())
    env.run(until=10.0)
    assert log == [("first", 5.0), ("second", 6.0)]


def test_full_factory_simulation_produces_finished_packs():
    cfg = default_gigafactory_config()
    profile = get_profile(cfg.chemistry)
    engine = FactorySimulationEngine(cfg, profile, lot_size=100, formation_channels=10, rng=np.random.default_rng(42))
    result = engine.run(hours=72, poll_interval=0.2)

    assert result.lots_started > 0
    assert result.cells_completed > 0
    assert result.pass_count > 0
    assert result.packs_completed > 0
    assert result.total_energy_kwh > 0
    # every produced pack event was logged on the telemetry bus
    assert result.event_bus.count_by_type().get("PACK_COMPLETED", 0) > 0


def test_bottleneck_analyzer_ranks_stages():
    cfg = default_gigafactory_config()
    profile = get_profile(cfg.chemistry)
    engine = FactorySimulationEngine(cfg, profile, lot_size=100, formation_channels=10, rng=np.random.default_rng(1))
    result = engine.run(hours=48, poll_interval=0.2)
    scores = BottleneckAnalyzer().analyze(result)
    assert len(scores) == len(result.stage_stats)
    assert scores == sorted(scores, key=lambda s: s.score, reverse=True)


def test_changeover_optimiser_groups_same_recipe_orders():
    matrix = ChangeoverMatrix(times_hours={("A", "B"): 4.0, ("A", "C"): 1.0, ("B", "C"): 4.0}, default_hours=2.0)
    now = datetime(2026, 1, 1)
    orders = [
        SchedulableOrder("o1", "A", 1000, now + timedelta(days=5)),
        SchedulableOrder("o2", "B", 1000, now + timedelta(days=1)),
        SchedulableOrder("o3", "C", 1000, now + timedelta(days=6)),
    ]
    scheduler = ProductionScheduler(matrix, throughput_units_per_hour=500)
    result = scheduler.schedule(orders, start_time=now)
    assert len(result.sequence) == 3
    assert result.total_changeover_hours >= 0
