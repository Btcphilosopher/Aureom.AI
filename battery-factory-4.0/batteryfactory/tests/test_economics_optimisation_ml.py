import numpy as np

from batteryfactory.economics.capex_opex import CapexInputs, OpexInputs
from batteryfactory.economics.cost_engine import CostEngine, CostInputs
from batteryfactory.economics.profitability import FactoryFinancials
from batteryfactory.ml.ml_engine import QualityPredictionModel, synthesize_quality_training_data
from batteryfactory.optimisation.capacity_optimiser import CapacityConstraints, CapacityDecision, FactoryCapacityOptimiser
from batteryfactory.optimisation.global_optimiser import DecisionVariable, MultiObjectiveOptimiser, ObjectiveWeights
from batteryfactory.optimisation.monte_carlo import MonteCarloEngine, UncertainParam
from batteryfactory.security.rbac import PermissionDenied, RBAC, Role, User


def test_capex_opex_depreciation_excludes_land():
    capex = CapexInputs(land=10, buildings=90, machinery=0, automation=0, utilities=0, dry_rooms=0,
                         formation_equipment=0, warehouses=0, laboratories=0, useful_life_years=10)
    assert capex.total_capex == 100
    assert capex.annual_depreciation == 9.0  # (100-10)/10, land not depreciated


def test_cost_engine_unit_costs_sum_to_total():
    inputs = CostInputs(100, 50, 30, 10, 20, 5, 8, 12)
    result = CostEngine().compute_unit_costs(inputs, cells_produced=1000, kwh_produced=500, modules_produced=10, packs_produced=2)
    assert abs(sum(result.breakdown_pct.values()) - 100.0) < 1e-6
    assert result.cost_per_cell == inputs.total_cost / 1000


def test_financials_higher_price_improves_margin():
    opex = OpexInputs(materials=1_000_000, electricity=200_000, labour=500_000, maintenance=100_000,
                       logistics=50_000, consumables=20_000, waste=30_000)
    capex = CapexInputs(0, 0, 0, 0, 0, 0, 0, 0, 0)
    fin = FactoryFinancials()
    low_price = fin.compute(80.0, 20_000, opex, capex)
    high_price = fin.compute(150.0, 20_000, opex, capex)
    assert high_price.gross_margin_pct > low_price.gross_margin_pct


def test_global_optimiser_finds_better_than_midpoint():
    def evaluate(point):
        # peak at line_speed=1.2
        production = 1000 * (1 - (point["line_speed"] - 1.2) ** 2)
        return {"production": production, "cost": 100 - production * 0.01}

    optimiser = MultiObjectiveOptimiser(ObjectiveWeights(maximise={"production": 1.0}, minimise={"cost": 0.2}))
    result = optimiser.optimise(
        [DecisionVariable("line_speed", 0.8, 1.6, 0.05)],
        evaluate, normalisers={"production": 1000, "cost": 100}, iterations=3,
    )
    assert abs(result.best_point["line_speed"] - 1.2) < 0.1


def test_monte_carlo_percentiles_are_ordered():
    def model(draw):
        return {"cost": draw["price"] * 100}
    result = MonteCarloEngine().run(model, [UncertainParam("price", "uniform", {"low": 1.0, "high": 2.0})],
                                     n_trials=200, rng=np.random.default_rng(0))
    p = result.percentiles["cost"]
    assert p["p5"] <= p["p50"] <= p["p95"]


def test_capacity_optimiser_rejects_infeasible_and_picks_best_feasible():
    def evaluate(decision: CapacityDecision) -> dict:
        capital = decision.num_lines * 50_000_000 * (1 + decision.automation_level)
        profit = decision.num_lines * decision.line_speed_multiplier * 1_000_000 - capital * 0.05
        return {"capital_required": capital, "labour_hours": decision.num_lines * 10000,
                "energy_kwh": decision.num_lines * 1e6, "floor_area_m2": decision.num_lines * 5000, "profit": profit}

    constraints = CapacityConstraints(max_capital=150_000_000, max_labour_hours_per_year=1e6,
                                       max_energy_kwh_per_year=1e9, max_floor_area_m2=1e6)
    result = FactoryCapacityOptimiser().search([1, 2, 3, 4], [1.0, 1.2], [2, 3], [0.2, 0.5], constraints, evaluate)
    assert result.feasible
    assert result.decision.num_lines <= 3  # 4 lines exceeds capital constraint at any automation level


def test_ml_engine_quality_model_learns_signal():
    rng = np.random.default_rng(0)
    X, y, names = synthesize_quality_training_data(600, rng)
    model = QualityPredictionModel()
    summary = model.train(X, y, names)
    assert summary.train_accuracy > 0.6  # better than a coin flip on a structured synthetic signal
    assert "simulated" in summary.data_provenance


def test_rbac_denies_unauthorized_role():
    rbac = RBAC()
    finance_user = User("alice", Role.FINANCE)
    ops_user = User("bob", Role.OPERATIONS_MANAGER)
    assert rbac.is_allowed(finance_user, "economics")
    assert not rbac.is_allowed(finance_user, "machines")
    try:
        rbac.check(finance_user, "machines")
        assert False, "expected PermissionDenied"
    except PermissionDenied:
        pass
    assert rbac.is_allowed(ops_user, "machines")
