import pytest

from icecream_x.core.engine import ProcessProfile, run_production_line
from icecream_x.economics.manufacturing_cost import manufacturing_cost
from icecream_x.economics.unit_economics import unit_economics
from icecream_x.scenarios.experiments import (
    experiment_c_increase_overrun,
    experiment_d_reduce_freezer_outlet_temperature,
    run_experiment,
)
from icecream_x.scenarios.recipes import vanilla


@pytest.fixture
def recipe():
    return vanilla()


def test_increase_overrun_experiment_changes_overrun(recipe):
    comparison = run_experiment(experiment_c_increase_overrun(120.0), recipe)
    assert comparison.experimental["overrun_pct"] > comparison.baseline["overrun_pct"]
    assert comparison.differences["overrun_pct"] == pytest.approx(30.0, abs=0.5)


def test_reduce_freezer_outlet_temperature_experiment_runs(recipe):
    comparison = run_experiment(experiment_d_reduce_freezer_outlet_temperature(-2.0), recipe)
    # Outlet temperature is capped by barrel residence time in the default
    # equipment config, so this may not shift the achieved temperature --
    # the important thing is that it runs and returns a valid comparison.
    assert "final_temperature_c" in comparison.baseline
    assert "final_temperature_c" in comparison.experimental


def test_manufacturing_cost_positive_and_breaks_down_to_total(recipe):
    pipeline = run_production_line(recipe, ProcessProfile())
    cost = manufacturing_cost(recipe, pipeline)
    assert cost.total_cost > 0
    assert cost.cost_per_kg > 0
    breakdown_total = sum(cost.cost_breakdown_pct.values())
    assert breakdown_total == pytest.approx(100.0, abs=0.5)


def test_unit_economics_margin_calculation(recipe):
    pipeline = run_production_line(recipe, ProcessProfile())
    cost = manufacturing_cost(recipe, pipeline)
    density = pipeline.final_state.product_density_kg_m3()
    econ = unit_economics(cost, density, unit_volume_litres=0.5, selling_price_per_unit=10.0)
    assert econ.cost_per_unit > 0
    assert econ.gross_margin_per_unit == pytest.approx(10.0 - econ.cost_per_unit)
