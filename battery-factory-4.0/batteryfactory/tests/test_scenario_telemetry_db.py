from datetime import datetime

from batteryfactory.database.db import FactoryDatabase
from batteryfactory.datamodel.models import EventType
from batteryfactory.scenario.scenario_engine import PREDEFINED_SCENARIOS, Scenario, ScenarioEngine, WhatIfSimulator
from batteryfactory.telemetry.event_stream import EventBus


def test_scenario_engine_applies_overrides_to_run_fn():
    seen_overrides = []

    def run_fn(overrides):
        seen_overrides.append(overrides)
        return {"cost": 100.0 * overrides.get("energy_price_multiplier", 1.0)}

    engine = ScenarioEngine(run_fn)
    result = engine.run_scenario(PREDEFINED_SCENARIOS["ENERGY_SHOCK"])
    assert result.metrics["cost"] == 200.0
    assert seen_overrides[-1] == {"energy_price_multiplier": 2.0}


def test_whatif_simulator_electricity_price_doubling():
    def run_fn(overrides):
        return {"cost": 50.0 * overrides.get("energy_price_multiplier", 1.0)}
    sim = WhatIfSimulator(ScenarioEngine(run_fn))
    result = sim.electricity_price_multiplier(2.0)
    assert result.metrics["cost"] == 100.0


def test_scenario_compare_runs_all():
    def run_fn(overrides):
        return {"x": 1.0}
    engine = ScenarioEngine(run_fn)
    results = engine.compare([PREDEFINED_SCENARIOS["BASE_CASE"], PREDEFINED_SCENARIOS["HIGH_DEMAND"]])
    assert len(results) == 2


def test_event_bus_emits_and_counts():
    bus = EventBus()
    bus.emit(EventType.CELL_COMPLETED, {"serial": "C1"}, sim_hours=1.0)
    bus.emit(EventType.CELL_COMPLETED, {"serial": "C2"}, sim_hours=2.0)
    bus.emit(EventType.QUALITY_FAILURE, {"serial": "C3"}, sim_hours=2.5)
    counts = bus.count_by_type()
    assert counts["CELL_COMPLETED"] == 2
    assert counts["QUALITY_FAILURE"] == 1
    events = bus.events_of_type(EventType.CELL_COMPLETED)
    assert events[0].timestamp < events[1].timestamp  # realistic increasing timestamps


def test_database_bulk_telemetry_and_indexed_query():
    db = FactoryDatabase(":memory:")
    rows = [("M1", "temperature_c", 30.0 + i, "C", datetime.utcnow().isoformat()) for i in range(100)]
    db.bulk_insert_telemetry(rows)
    result = db.query_telemetry("M1", "temperature_c", limit=10)
    assert len(result) == 10
    db.log_audit("alice", "finance", "read", "economics", True)
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM audit_log")
        assert cur.fetchone()[0] == 1
    db.close()
