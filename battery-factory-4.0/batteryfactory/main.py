"""
BATTERYFACTORY 4.0 command-line entry point.

    python -m batteryfactory.main --hours 48 --report
    python -m batteryfactory.main --hours 24 --monte-carlo 200
    python -m batteryfactory.main --hours 24 --scenario ENERGY_SHOCK
"""
from __future__ import annotations

import argparse

import numpy as np

from batteryfactory.core.factory_twin import FactoryDigitalTwin
from batteryfactory.economics.capex_opex import CapexInputs
from batteryfactory.optimisation.monte_carlo import MonteCarloEngine, UncertainParam
from batteryfactory.scenario.scenario_engine import PREDEFINED_SCENARIOS, ScenarioEngine
from batteryfactory.ui.dashboard import render_all


def _default_capex() -> CapexInputs:
    return CapexInputs(
        land=20_000_000, buildings=80_000_000, machinery=250_000_000, automation=60_000_000,
        utilities=25_000_000, dry_rooms=15_000_000, formation_equipment=90_000_000,
        warehouses=10_000_000, laboratories=5_000_000,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BatteryFactory 4.0 digital twin / simulator / optimiser")
    parser.add_argument("--hours", type=float, default=24.0, help="Simulated hours to run")
    parser.add_argument("--seed", type=int, default=None, help="RNG seed")
    parser.add_argument("--report", action="store_true", help="Print the four dashboards")
    parser.add_argument("--monte-carlo", type=int, default=0, help="Run N Monte Carlo trials of the economics model")
    parser.add_argument("--scenario", choices=sorted(PREDEFINED_SCENARIOS), default=None, help="Run a predefined what-if scenario and compare to base case")
    return parser


def run_once(hours: float, seed: int | None, demand_multiplier: float = 1.0, energy_price_multiplier: float = 1.0):
    twin = FactoryDigitalTwin.build_default(seed=seed)
    result = twin.run_simulation(hours=hours, capex=_default_capex(), electricity_price_per_kwh=0.12 * energy_price_multiplier)
    return twin, result


def main() -> None:
    args = build_arg_parser().parse_args()
    twin, result = run_once(args.hours, args.seed)

    if args.report or not (args.monte_carlo or args.scenario):
        print(render_all(twin, result))

    if args.monte_carlo:
        mc = MonteCarloEngine()
        params = [
            UncertainParam("yield_shift", "normal", {"mean": 0.0, "std": 0.03}),
            UncertainParam("material_price_multiplier", "triangular", {"left": 0.8, "mode": 1.0, "right": 1.4}),
            UncertainParam("energy_price_multiplier", "triangular", {"left": 0.8, "mode": 1.0, "right": 2.0}),
        ]

        def model(draw: dict[str, float]) -> dict[str, float]:
            # Each trial re-simulates with a fresh seed so machine faults, yield
            # variation etc. vary trial-to-trial, not just the priced-in shocks.
            trial_seed = None if args.seed is None else args.seed + int(abs(draw["yield_shift"]) * 1e6) % 10_000 + 1
            t, r = run_once(args.hours, trial_seed, energy_price_multiplier=draw["energy_price_multiplier"])
            return {
                "cost_per_kwh": r.unit_cost.cost_per_kwh * draw["material_price_multiplier"],
                "ebitda": r.financials.ebitda,
                "cells_completed": float(r.simulation.cells_completed),
            }

        mc_result = mc.run(model, params, n_trials=args.monte_carlo, rng=np.random.default_rng(args.seed))
        print("\n" + "=" * 70)
        print(f"MONTE CARLO ({args.monte_carlo} trials)")
        print("=" * 70)
        for metric, pct in mc_result.percentiles.items():
            print(f"{metric:18s} p5={pct['p5']:10.2f}  p50={pct['p50']:10.2f}  p95={pct['p95']:10.2f}  mean={pct['mean']:10.2f}")

    if args.scenario:
        scenario = PREDEFINED_SCENARIOS[args.scenario]

        def run_fn(overrides: dict[str, float]) -> dict[str, float]:
            energy_mult = overrides.get("energy_price_multiplier", 1.0)
            t, r = run_once(args.hours, args.seed, energy_price_multiplier=energy_mult)
            return {"cells_completed": r.simulation.cells_completed, "ebitda": r.financials.ebitda, "cost_per_kwh": r.unit_cost.cost_per_kwh}

        engine = ScenarioEngine(run_fn)
        base = engine.run_scenario(PREDEFINED_SCENARIOS["BASE_CASE"])
        scenario_result = engine.run_scenario(scenario)
        print("\n" + "=" * 70)
        print(f"SCENARIO: {scenario.name} -- {scenario.description}")
        print("=" * 70)
        print(f"{'metric':18s} {'base':>14s} {'scenario':>14s}")
        for key in base.metrics:
            print(f"{key:18s} {base.metrics[key]:14,.2f} {scenario_result.metrics[key]:14,.2f}")


if __name__ == "__main__":
    main()
