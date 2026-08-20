import numpy as np
import pytest

from hydroflux.optimisation.algorithms import (
    DifferentialEvolutionAlgorithm,
    GeneticAlgorithm,
    MonteCarloSearchAlgorithm,
    ScipyMinimizeAlgorithm,
)
from hydroflux.optimisation.objectives import ObjectiveWeights, composite_objective
from hydroflux.optimisation.optimiser import optimise_policy


def quadratic_peak(x):
    return -((x[0] - 2.0) ** 2) + 5.0


@pytest.mark.parametrize(
    "algorithm",
    [
        ScipyMinimizeAlgorithm(),
        DifferentialEvolutionAlgorithm(maxiter=15, popsize=10),
        MonteCarloSearchAlgorithm(n_samples=200),
        GeneticAlgorithm(population_size=20, generations=20),
    ],
)
def test_algorithms_find_known_maximum(algorithm):
    result = algorithm.optimise(quadratic_peak, [(-10.0, 10.0)], seed=1, maximize=True)
    assert result.best_x[0] == pytest.approx(2.0, abs=0.3)
    assert result.best_value == pytest.approx(5.0, abs=0.3)


def test_composite_objective_weights_energy_and_penalises_lcoe():
    weights = ObjectiveWeights(energy=1.0, lcoe=2.0)
    metrics = {"energy": 100.0, "lcoe": 30.0}
    assert composite_objective(metrics, weights) == pytest.approx(100.0 - 60.0)


def test_composite_objective_missing_metric_treated_as_zero():
    weights = ObjectiveWeights(revenue=1.0, npv=1.0)
    metrics = {"revenue": 50.0}
    assert composite_objective(metrics, weights) == pytest.approx(50.0)


def test_objective_weights_preset_lookup():
    weights = ObjectiveWeights.preset("max_revenue")
    assert weights.revenue == 1.0
    assert weights.energy == 0.0
    with pytest.raises(ValueError):
        ObjectiveWeights.preset("not_a_real_preset")


def test_optimise_policy_respects_bounds():
    def evaluate(params):
        return {"energy": -((params["x"] - 7.0) ** 2)}

    weights = ObjectiveWeights(energy=1.0)
    result = optimise_policy(
        ["x"],
        [(0.0, 5.0)],  # optimum (7.0) lies outside these bounds
        evaluate,
        weights,
        algorithm="differential_evolution",
        seed=1,
        maxiter=15,
        popsize=10,
    )
    assert 0.0 <= result.best_parameters["x"] <= 5.0


def test_optimise_policy_converges_near_optimum_inside_bounds():
    def evaluate(params):
        return {"revenue": -((params["x"] - 3.0) ** 2) - ((params["y"] + 1.0) ** 2)}

    weights = ObjectiveWeights(revenue=1.0)
    result = optimise_policy(
        ["x", "y"],
        [(-10.0, 10.0), (-10.0, 10.0)],
        evaluate,
        weights,
        algorithm="differential_evolution",
        seed=42,
        maxiter=25,
        popsize=12,
    )
    assert result.best_parameters["x"] == pytest.approx(3.0, abs=0.3)
    assert result.best_parameters["y"] == pytest.approx(-1.0, abs=0.3)
