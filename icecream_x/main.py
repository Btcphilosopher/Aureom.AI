"""ICECREAM-X command-line demo.

Runs a recipe from :mod:`icecream_x.scenarios.recipes` through the full
production line and a cold-chain storage simulation, printing the
resulting thermodynamic state, microstructure, energy, cost, and quality
summary at each major stage -- a minimal "virtual factory" walkthrough.

Usage:

    python -m icecream_x.main --recipe vanilla --storage-days 14
    python -m icecream_x.main --list-recipes
"""

from __future__ import annotations

import argparse
import sys

from icecream_x.analytics.energy import energy_breakdown
from icecream_x.analytics.production import production_rate
from icecream_x.analytics.quality import quality_score
from icecream_x.core.engine import ProcessProfile, run_production_line
from icecream_x.core.simulation import run_storage_simulation
from icecream_x.economics.manufacturing_cost import manufacturing_cost
from icecream_x.economics.unit_economics import unit_economics
from icecream_x.scenarios.recipes import RECIPE_LIBRARY
from icecream_x.storage.freezer import COLD_STORE
from icecream_x.utils.logging import configure_logging, get_logger

logger = get_logger("main")


def _print_section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def run_demo(recipe_name: str, storage_days: float) -> int:
    configure_logging()

    recipe = RECIPE_LIBRARY.get(recipe_name)
    if recipe is None:
        print(f"Unknown recipe '{recipe_name}'. Available: {list(RECIPE_LIBRARY)}", file=sys.stderr)
        return 1

    _print_section(f"FORMULATION: {recipe.name}")
    for row in recipe.summary_table():
        print(f"  {row['ingredient']:<40s} {row['mass_kg']:>8.2f} kg  ({row['mass_pct']:>5.1f}%)")
    composition = recipe.composition()
    print(f"\n  Batch mass: {recipe.batch_mass_kg:.2f} kg")
    print(f"  Total solids: {100 * composition.fraction(composition.total_solids_kg):.1f}%")
    print(f"  Fat: {100 * composition.fraction(composition.fat_kg):.1f}%  MSNF: {100 * composition.fraction(composition.msnf_kg):.1f}%")

    _print_section("PRODUCTION LINE")
    pipeline = run_production_line(recipe, ProcessProfile())
    for s in pipeline.stage_summaries():
        print(
            f"  {s['stage']:<12s} T={s['temperature_c']:>7.2f} degC   "
            f"ice={s['ice_fraction_pct']:>5.1f}%   overrun={s.get('overrun_pct', 0):>5.1f}%   "
            f"t={s['elapsed_time_s']:>8.1f} s   E={s['cumulative_energy_kwh']:>6.3f} kWh"
        )

    _print_section("MICROSTRUCTURE (post-hardening)")
    for k, v in pipeline.final_state.microstructure.summary().items():
        print(f"  {k}: {v}")

    _print_section("ENERGY")
    density = pipeline.final_state.product_density_kg_m3()
    energy = energy_breakdown(pipeline, density)
    print(f"  Heating:         {energy.heating_kwh:.3f} kWh")
    print(f"  Homogenisation:  {energy.homogenisation_kwh:.3f} kWh")
    print(f"  Freezing:        {energy.freezing_kwh:.3f} kWh")
    print(f"  Hardening:       {energy.hardening_kwh:.3f} kWh")
    print(f"  Total:           {energy.total_kwh:.3f} kWh ({energy.kwh_per_kg:.4f} kWh/kg, {energy.kwh_per_litre:.4f} kWh/L)")

    rate = production_rate(pipeline, density)
    print(f"\n  Cycle time: {rate.cycle_time_s / 60:.1f} min   Throughput: {rate.throughput_kg_per_hour:.1f} kg/h")

    _print_section("ECONOMICS")
    cost = manufacturing_cost(recipe, pipeline)
    print(f"  Ingredient cost: {cost.ingredient.total_cost:.2f}   Energy cost: {cost.energy.total_cost:.2f}")
    print(f"  Total cost: {cost.total_cost:.2f}   Cost/kg: {cost.cost_per_kg:.3f}")
    econ = unit_economics(cost, density, unit_volume_litres=0.5, selling_price_per_unit=6.0)
    print(f"  Cost/litre: {econ.cost_per_litre:.3f}   Cost/unit (0.5L): {econ.cost_per_unit:.3f}   Margin: {econ.gross_margin_pct:.1f}%")

    _print_section("QUALITY")
    q = quality_score(pipeline.final_state)
    print(f"  Overall quality score: {q.overall_score:.1f} / 100")
    for k, v in q.subscores.items():
        print(f"    {k}: {v:.3f}")

    _print_section(f"COLD STORAGE ({storage_days:.0f} days at {COLD_STORE.setpoint_temperature_c} degC)")
    sim = run_storage_simulation(
        pipeline.final_state, COLD_STORE, duration_s=storage_days * 24 * 3600, dt_s=3600, log_every_n_steps=24
    )
    final_micro = sim.final_state.microstructure
    print(f"  Final crystal diameter: {final_micro.ice_crystals.mean_diameter_um:.1f} um "
          f"(was {pipeline.final_state.microstructure.ice_crystals.mean_diameter_um:.1f} um post-hardening)")
    final_q = quality_score(sim.final_state)
    print(f"  Final quality score: {final_q.overall_score:.1f} / 100 (was {q.overall_score:.1f})")

    print()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="ICECREAM-X production/storage simulation demo")
    parser.add_argument("--recipe", default="vanilla", help="Recipe name from the scenario library")
    parser.add_argument("--storage-days", type=float, default=14.0, help="Cold-storage duration to simulate")
    parser.add_argument("--list-recipes", action="store_true", help="List available recipes and exit")
    args = parser.parse_args()

    if args.list_recipes:
        for name in RECIPE_LIBRARY:
            print(name)
        return 0

    return run_demo(args.recipe, args.storage_days)


if __name__ == "__main__":
    raise SystemExit(main())
