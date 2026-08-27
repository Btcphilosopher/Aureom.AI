from icecream_x.core.engine import ProcessProfile, run_production_line
from icecream_x.optimisation.process_optimizer import ParameterSpec, optimise_process
from icecream_x.scenarios.recipes import vanilla


def test_optimise_process_improves_or_matches_objective():
    recipe = vanilla()
    params = [ParameterSpec("overrun_pct", 20.0, 130.0)]

    def objective(result) -> float:
        return -abs(result.final_state.overrun_pct - 100.0)  # maximise -> target 100% overrun

    base_profile = ProcessProfile(overrun_pct=20.0)  # start far from the optimum
    result = optimise_process(recipe, base_profile, params, objective, maximise=True, max_iterations=25)

    baseline_objective = objective(run_production_line(recipe, base_profile))
    assert result.optimal_objective_value >= baseline_objective
    assert result.n_evaluations > 0
