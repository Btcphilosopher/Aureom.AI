"""End-to-end integration test: the full digital-twin loop described in the
platform's design goal -- design, simulate, measure, optimise -- actually
runs together without error and produces internally-consistent numbers."""
import numpy as np

from batteryfactory.core.factory_twin import FactoryDigitalTwin
from batteryfactory.economics.capex_opex import CapexInputs
from batteryfactory.ui.dashboard import render_all


def test_full_twin_run_end_to_end():
    twin = FactoryDigitalTwin.build_default(seed=123)
    capex = CapexInputs(20_000_000, 80_000_000, 250_000_000, 60_000_000, 25_000_000,
                         15_000_000, 90_000_000, 10_000_000, 5_000_000)
    result = twin.run_simulation(hours=48, capex=capex)

    sim = result.simulation
    assert sim.cells_completed > 0
    assert sim.packs_completed >= 0
    assert result.energy.total_factory_kwh > 0
    assert result.unit_cost.cost_per_cell > 0
    assert result.financials.revenue >= 0
    assert len(result.bottlenecks) == len(sim.stage_stats)
    assert len(result.maintenance_predictions) == len(twin.simulation_engine.machines)

    # Consistency: total completed+scrapped at the testing stage should not
    # exceed cells fed in from assembly (conservation of units through the line).
    assert sim.pass_count + sim.rework_count + sim.fail_count + sim.reject_count <= sim.cells_completed + sim.cells_scrapped_or_rejected + 1

    report = render_all(twin, result)
    assert "MANAGEMENT DASHBOARD" in report
    assert "FINANCE DASHBOARD" in report


def test_twin_is_deterministic_given_seed():
    twin_a = FactoryDigitalTwin.build_default(seed=99)
    twin_b = FactoryDigitalTwin.build_default(seed=99)
    result_a = twin_a.run_simulation(hours=12)
    result_b = twin_b.run_simulation(hours=12)
    assert result_a.simulation.cells_completed == result_b.simulation.cells_completed
    assert result_a.simulation.pass_count == result_b.simulation.pass_count
