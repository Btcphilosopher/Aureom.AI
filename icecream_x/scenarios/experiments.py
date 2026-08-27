"""The experiment engine.

An :class:`Experiment` is a named transformation applied to a baseline
recipe and/or process profile. :func:`run_experiment` runs the production
pipeline (and, optionally, a cold-chain storage simulation) for both the
untouched baseline and the modified case, and reports a baseline vs.
experimental vs. difference comparison for the metrics that matter most
(temperature, ice fraction, crystal size, energy, quality, cost).

Six worked examples matching the spec are provided as factory functions
(A-F): sucrose increase, fat reduction, overrun increase, freezer outlet
temperature reduction, hardening-rate increase, and storage-temperature
cycling.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass, field

from icecream_x.analytics.quality import quality_score
from icecream_x.core.engine import PipelineResult, ProcessProfile, run_production_line
from icecream_x.formulation.composition import WeighedIngredient
from icecream_x.formulation.recipe import Recipe
from icecream_x.formulation.sugars import SUCROSE

RecipeModifier = Callable[[Recipe], Recipe]
ProfileModifier = Callable[[ProcessProfile], ProcessProfile]


@dataclass(slots=True)
class Experiment:
    name: str
    description: str
    modify_recipe: RecipeModifier | None = None
    modify_profile: ProfileModifier | None = None


@dataclass(frozen=True, slots=True)
class ExperimentComparison:
    name: str
    baseline: dict[str, float]
    experimental: dict[str, float]
    differences: dict[str, float] = field(default_factory=dict)


_METRIC_KEYS = (
    "final_temperature_c",
    "ice_fraction_pct",
    "overrun_pct",
    "mean_ice_crystal_diameter_um",
    "fat_destabilisation_degree",
    "total_energy_kwh",
    "quality_score",
)


def _metrics(result: PipelineResult) -> dict[str, float]:
    state = result.final_state
    micro = state.microstructure.summary()
    q = quality_score(state)
    values = {
        "final_temperature_c": state.temperature_c,
        "ice_fraction_pct": state.thermal_state().phase.ice_mass_fraction * 100.0,
        "overrun_pct": state.overrun_pct if state.air_volume_fraction > 0 else 0.0,
        "mean_ice_crystal_diameter_um": micro.get("mean_ice_crystal_diameter_um") or 0.0,
        "fat_destabilisation_degree": micro.get("fat_destabilisation_degree") or 0.0,
        "total_energy_kwh": state.cumulative_energy_j / 3_600_000.0,
        "quality_score": q.overall_score,
    }
    return {k: values[k] for k in _METRIC_KEYS}


def run_experiment(
    experiment: Experiment, base_recipe: Recipe, base_profile: ProcessProfile = ProcessProfile()
) -> ExperimentComparison:
    baseline_result = run_production_line(base_recipe, base_profile)

    exp_recipe = experiment.modify_recipe(base_recipe) if experiment.modify_recipe else base_recipe
    exp_profile = experiment.modify_profile(base_profile) if experiment.modify_profile else base_profile
    experimental_result = run_production_line(exp_recipe, exp_profile)

    baseline_metrics = _metrics(baseline_result)
    experimental_metrics = _metrics(experimental_result)
    differences = {k: experimental_metrics[k] - baseline_metrics[k] for k in _METRIC_KEYS}

    return ExperimentComparison(
        name=experiment.name,
        baseline=baseline_metrics,
        experimental=experimental_metrics,
        differences=differences,
    )


# --- worked examples matching the spec (A-F) -----------------------------


def _scale_ingredient(recipe: Recipe, ingredient_name: str, factor: float) -> Recipe:
    new_lines = [
        dataclasses.replace(line, mass_kg=line.mass_kg * factor)
        if line.ingredient.name == ingredient_name
        else line
        for line in recipe.lines
    ]
    return Recipe(name=f"{recipe.name} (modified)", lines=new_lines, description=recipe.description)


def _add_ingredient_mass(recipe: Recipe, ingredient_name: str, extra_mass_kg: float, ingredient) -> Recipe:
    new_lines = list(recipe.lines)
    found = False
    for i, line in enumerate(new_lines):
        if line.ingredient.name == ingredient_name:
            new_lines[i] = dataclasses.replace(line, mass_kg=line.mass_kg + extra_mass_kg)
            found = True
    if not found:
        new_lines.append(WeighedIngredient(ingredient=ingredient, mass_kg=extra_mass_kg))
    return Recipe(name=f"{recipe.name} (modified)", lines=new_lines, description=recipe.description)


def experiment_a_increase_sucrose(extra_pct_points: float = 2.0) -> Experiment:
    def modify(recipe: Recipe) -> Recipe:
        extra_mass = recipe.batch_mass_kg * (extra_pct_points / 100.0)
        return _add_ingredient_mass(recipe, SUCROSE.name, extra_mass, SUCROSE)

    return Experiment(
        name="A: Increase sucrose by 2 percentage points",
        description="Adds sucrose mass equal to 2% of the batch mass.",
        modify_recipe=modify,
    )


def experiment_b_reduce_fat(reduction_fraction: float = 0.15) -> Experiment:
    def modify(recipe: Recipe) -> Recipe:
        new_recipe = recipe
        for line in recipe.lines:
            if line.ingredient.fat_fraction > 0.3:  # cream/fat-dominant ingredients
                new_recipe = _scale_ingredient(new_recipe, line.ingredient.name, 1.0 - reduction_fraction)
        return new_recipe

    return Experiment(
        name="B: Reduce fat-dominant ingredients by 15%",
        description="Scales down cream/butterfat-type ingredient lines by 15%.",
        modify_recipe=modify,
    )


def experiment_c_increase_overrun(new_overrun_pct: float = 120.0) -> Experiment:
    return Experiment(
        name="C: Increase overrun",
        description=f"Sets target overrun to {new_overrun_pct:.0f}%.",
        modify_profile=lambda p: dataclasses.replace(p, overrun_pct=new_overrun_pct),
    )


def experiment_d_reduce_freezer_outlet_temperature(delta_c: float = -2.0) -> Experiment:
    return Experiment(
        name="D: Reduce freezer outlet temperature",
        description=f"Lowers freezer outlet setpoint by {abs(delta_c):.1f} degC.",
        modify_profile=lambda p: dataclasses.replace(
            p, freezer_outlet_temperature_c=p.freezer_outlet_temperature_c + delta_c
        ),
    )


def experiment_e_increase_hardening_rate() -> Experiment:
    import dataclasses as dc

    def modify(profile: ProcessProfile) -> ProcessProfile:
        faster_tunnel = dc.replace(
            profile.hardening_tunnel,
            air_velocity_m_s=profile.hardening_tunnel.air_velocity_m_s * 1.5,
            heat_transfer_coefficient_w_m2_k=profile.hardening_tunnel.heat_transfer_coefficient_w_m2_k * 1.4,
        )
        return dc.replace(profile, hardening_tunnel=faster_tunnel)

    return Experiment(
        name="E: Increase hardening rate",
        description="Increases tunnel air velocity and heat-transfer coefficient.",
        modify_profile=modify,
    )


def experiment_f_storage_temperature_cycling(
    final_state,
    facility,
    duration_s: float,
    *,
    cycle_period_s: float = 24 * 3600.0,
    cycle_amplitude_c: float = 6.0,
    dt_s: float = 1800.0,
) -> ExperimentComparison:
    """F: compare uninterrupted storage vs. daily temperature cycling.

    Unlike experiments A-E, this compares two *storage* histories rather
    than two production runs (overrun/quality metrics are frozen at
    hardening and don't change further in storage) -- so it reports
    ice-crystal growth and final temperature directly rather than
    reusing :func:`_metrics`.
    """
    from icecream_x.storage.cold_chain import ColdChainStage, simulate_cold_chain
    from icecream_x.storage.temperature_history import TemperatureProfile, uninterrupted

    baseline_stage = ColdChainStage(
        "Uninterrupted", facility, duration_s, temperature_profile=uninterrupted(facility.setpoint_temperature_c)
    )
    baseline_result = simulate_cold_chain(final_state, [baseline_stage], dt_s=dt_s)

    cycling_profile = TemperatureProfile(baseline_temperature_c=facility.setpoint_temperature_c)
    t = 0.0
    while t < duration_s:
        cycling_profile.add_excursion(
            start_time_s=t,
            duration_s=cycle_period_s / 2.0,
            peak_temperature_c=facility.setpoint_temperature_c + cycle_amplitude_c,
        )
        t += cycle_period_s
    cycling_stage = ColdChainStage("Cycling", facility, duration_s, temperature_profile=cycling_profile)
    cycling_result = simulate_cold_chain(final_state, [cycling_stage], dt_s=dt_s)

    def crystal_um(state) -> float:
        c = state.microstructure.ice_crystals
        return c.mean_diameter_um if c else 0.0

    baseline_metrics = {
        "final_crystal_diameter_um": crystal_um(baseline_result.final_state),
        "final_temperature_c": baseline_result.final_state.temperature_c,
    }
    experimental_metrics = {
        "final_crystal_diameter_um": crystal_um(cycling_result.final_state),
        "final_temperature_c": cycling_result.final_state.temperature_c,
    }
    differences = {k: experimental_metrics[k] - baseline_metrics[k] for k in baseline_metrics}

    return ExperimentComparison(
        name="F: Introduce storage temperature cycling",
        baseline=baseline_metrics,
        experimental=experimental_metrics,
        differences=differences,
    )


EXPERIMENT_LIBRARY: dict[str, Callable[[], Experiment]] = {
    "increase_sucrose": experiment_a_increase_sucrose,
    "reduce_fat": experiment_b_reduce_fat,
    "increase_overrun": experiment_c_increase_overrun,
    "reduce_freezer_outlet_temperature": experiment_d_reduce_freezer_outlet_temperature,
    "increase_hardening_rate": experiment_e_increase_hardening_rate,
}
