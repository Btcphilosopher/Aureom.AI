"""Optional FastAPI interface.

An in-memory prototype server exposing the core simulation engine over
HTTP with strongly-typed (Pydantic) request/response models. State
(recipes, simulation results) lives in a process-local dict, not a
database -- wire in :mod:`icecream_x.database.repository` for durable
storage if/when this is deployed for real.

Run with:

    uvicorn icecream_x.api.server:app --reload
"""

from __future__ import annotations

import dataclasses
import itertools
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from icecream_x.analytics.energy import energy_breakdown
from icecream_x.analytics.quality import quality_score
from icecream_x.core.engine import PipelineResult, ProcessProfile, run_production_line
from icecream_x.formulation import INGREDIENT_LIBRARY
from icecream_x.formulation.composition import WeighedIngredient
from icecream_x.formulation.recipe import Recipe
from icecream_x.optimisation.energy_optimizer import minimise_energy
from icecream_x.optimisation.process_optimizer import ParameterSpec
from icecream_x.optimisation.quality_optimizer import maximise_quality
from icecream_x.scenarios.experiments import EXPERIMENT_LIBRARY, run_experiment

app = FastAPI(title="ICECREAM-X API", version="0.1.0")

_recipes: dict[int, Recipe] = {}
_simulations: dict[int, PipelineResult] = {}
_recipe_ids = itertools.count(1)
_simulation_ids = itertools.count(1)


# --- request/response models ---------------------------------------------


class IngredientLine(BaseModel):
    ingredient_name: str
    mass_kg: float = Field(gt=0)


class CreateRecipeRequest(BaseModel):
    name: str
    description: str = ""
    lines: list[IngredientLine]


class CreateRecipeResponse(BaseModel):
    recipe_id: int
    name: str
    batch_mass_kg: float
    composition_pct: dict[str, float]


class RunSimulationRequest(BaseModel):
    recipe_id: int
    overrun_pct: float = 90.0
    freezer_outlet_temperature_c: float = -5.5
    hardening_target_temperature_c: float = -20.0
    ageing_time_s: float = 4.0 * 3600.0


class RunSimulationResponse(BaseModel):
    simulation_id: int
    final_state: dict[str, Any]
    stage_summaries: list[dict[str, Any]]


class StateResponse(BaseModel):
    simulation_id: int
    state: dict[str, Any]


class RunExperimentRequest(BaseModel):
    recipe_id: int
    experiment_name: str


class ExperimentResponse(BaseModel):
    name: str
    baseline: dict[str, float]
    experimental: dict[str, float]
    differences: dict[str, float]


class OptimiseRequest(BaseModel):
    recipe_id: int
    objective: str  # "quality" | "energy"
    parameter_path: str
    lower_bound: float
    upper_bound: float
    minimum_quality_score: float = 0.0


class OptimiseResponse(BaseModel):
    optimal_parameters: dict[str, float]
    optimal_objective_value: float
    converged: bool


class CompareRequest(BaseModel):
    recipe_ids: list[int]


class CompareResponse(BaseModel):
    results: list[dict[str, Any]]


class EnergyResponse(BaseModel):
    heating_kwh: float
    homogenisation_kwh: float
    freezing_kwh: float
    hardening_kwh: float
    total_kwh: float
    kwh_per_kg: float
    kwh_per_litre: float


class QualityResponse(BaseModel):
    overall_score: float
    subscores: dict[str, float]


class MicrostructureResponse(BaseModel):
    microstructure: dict[str, float | None]


# --- helpers ---------------------------------------------------------------


def _get_recipe(recipe_id: int) -> Recipe:
    recipe = _recipes.get(recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail=f"Recipe {recipe_id} not found")
    return recipe


def _get_simulation(simulation_id: int) -> PipelineResult:
    result = _simulations.get(simulation_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Simulation {simulation_id} not found")
    return result


# --- endpoints ---------------------------------------------------------------


@app.post("/create_recipe", response_model=CreateRecipeResponse)
def create_recipe(request: CreateRecipeRequest) -> CreateRecipeResponse:
    recipe = Recipe(name=request.name, description=request.description)
    for line in request.lines:
        ingredient = INGREDIENT_LIBRARY.get(line.ingredient_name)
        if ingredient is None:
            raise HTTPException(status_code=400, detail=f"Unknown ingredient '{line.ingredient_name}'")
        recipe.lines.append(WeighedIngredient(ingredient=ingredient, mass_kg=line.mass_kg))

    recipe_id = next(_recipe_ids)
    _recipes[recipe_id] = recipe
    composition = recipe.composition()
    return CreateRecipeResponse(
        recipe_id=recipe_id,
        name=recipe.name,
        batch_mass_kg=recipe.batch_mass_kg,
        composition_pct={k: 100 * v for k, v in composition.as_fractions().items()},
    )


@app.post("/run_simulation", response_model=RunSimulationResponse)
def run_simulation(request: RunSimulationRequest) -> RunSimulationResponse:
    recipe = _get_recipe(request.recipe_id)
    profile = ProcessProfile(
        overrun_pct=request.overrun_pct,
        freezer_outlet_temperature_c=request.freezer_outlet_temperature_c,
        hardening_target_temperature_c=request.hardening_target_temperature_c,
        ageing_time_s=request.ageing_time_s,
    )
    result = run_production_line(recipe, profile)
    simulation_id = next(_simulation_ids)
    _simulations[simulation_id] = result
    return RunSimulationResponse(
        simulation_id=simulation_id,
        final_state=result.final_state.summary(),
        stage_summaries=result.stage_summaries(),
    )


@app.get("/get_state/{simulation_id}", response_model=StateResponse)
def get_state(simulation_id: int) -> StateResponse:
    result = _get_simulation(simulation_id)
    return StateResponse(simulation_id=simulation_id, state=result.final_state.summary())


@app.post("/run_experiment", response_model=ExperimentResponse)
def run_experiment_endpoint(request: RunExperimentRequest) -> ExperimentResponse:
    recipe = _get_recipe(request.recipe_id)
    factory = EXPERIMENT_LIBRARY.get(request.experiment_name)
    if factory is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown experiment '{request.experiment_name}'. Available: {list(EXPERIMENT_LIBRARY)}",
        )
    comparison = run_experiment(factory(), recipe)
    return ExperimentResponse(
        name=comparison.name,
        baseline=comparison.baseline,
        experimental=comparison.experimental,
        differences=comparison.differences,
    )


@app.post("/optimise", response_model=OptimiseResponse)
def optimise(request: OptimiseRequest) -> OptimiseResponse:
    recipe = _get_recipe(request.recipe_id)
    param = ParameterSpec(request.parameter_path, request.lower_bound, request.upper_bound)
    if request.objective == "quality":
        result = maximise_quality(recipe, ProcessProfile(), [param], max_iterations=40)
    elif request.objective == "energy":
        result = minimise_energy(
            recipe,
            ProcessProfile(),
            [param],
            minimum_quality_score=request.minimum_quality_score,
            max_iterations=40,
        )
    else:
        raise HTTPException(status_code=400, detail="objective must be 'quality' or 'energy'")

    return OptimiseResponse(
        optimal_parameters=result.optimal_parameters,
        optimal_objective_value=result.optimal_objective_value,
        converged=result.converged,
    )


@app.post("/compare", response_model=CompareResponse)
def compare(request: CompareRequest) -> CompareResponse:
    rows = []
    for recipe_id in request.recipe_ids:
        recipe = _get_recipe(recipe_id)
        result = run_production_line(recipe, ProcessProfile())
        q = quality_score(result.final_state)
        rows.append(
            {
                "recipe_id": recipe_id,
                "name": recipe.name,
                "quality_score": q.overall_score,
                **result.final_state.summary(),
            }
        )
    return CompareResponse(results=rows)


@app.get("/get_energy/{simulation_id}", response_model=EnergyResponse)
def get_energy(simulation_id: int) -> EnergyResponse:
    result = _get_simulation(simulation_id)
    density = result.final_state.product_density_kg_m3()
    breakdown = energy_breakdown(result, density)
    return EnergyResponse(**dataclasses.asdict(breakdown))


@app.get("/get_quality/{simulation_id}", response_model=QualityResponse)
def get_quality(simulation_id: int) -> QualityResponse:
    result = _get_simulation(simulation_id)
    q = quality_score(result.final_state)
    return QualityResponse(overall_score=q.overall_score, subscores=q.subscores)


@app.get("/get_microstructure/{simulation_id}", response_model=MicrostructureResponse)
def get_microstructure(simulation_id: int) -> MicrostructureResponse:
    result = _get_simulation(simulation_id)
    return MicrostructureResponse(microstructure=result.final_state.microstructure.summary())
