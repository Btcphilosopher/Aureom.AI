"""Repository: persistence facade over the SQLAlchemy models.

Defaults to a local SQLite file so the whole system remains runnable
with zero external setup; pass any SQLAlchemy URL (e.g. a PostgreSQL
DSN) to use a real database server.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from icecream_x.core.engine import PipelineResult
from icecream_x.database.migrations import create_schema
from icecream_x.database.models import (
    EnergyResultRecord,
    ExperimentRecord,
    OptimisationRunRecord,
    ProcessRunRecord,
    QualityResultRecord,
    RecipeRecord,
    SimulationRecord,
    SimulationStateRecord,
)
from icecream_x.formulation.recipe import Recipe

DEFAULT_SQLITE_URL = "sqlite:///icecream_x.db"


class Repository:
    def __init__(self, database_url: str = DEFAULT_SQLITE_URL, *, echo: bool = False) -> None:
        self.engine = create_engine(database_url, echo=echo)
        create_schema(self.engine)
        self._session_factory = sessionmaker(bind=self.engine)

    def session(self) -> Session:
        return self._session_factory()

    def save_recipe(self, recipe: Recipe) -> int:
        with self.session() as session:
            record = RecipeRecord(
                name=recipe.name,
                description=recipe.description,
                lines=[
                    {"ingredient_name": line.ingredient.name, "mass_kg": line.mass_kg}
                    for line in recipe.lines
                ],
            )
            session.add(record)
            session.commit()
            return record.id

    def save_pipeline_result(self, recipe_id: int, pipeline_result: PipelineResult) -> int:
        with self.session() as session:
            sim = SimulationRecord(recipe_id=recipe_id, process_profile={})
            session.add(sim)
            session.flush()

            for summary in pipeline_result.stage_summaries():
                session.add(
                    SimulationStateRecord(
                        simulation_id=sim.id,
                        timestamp_s=summary.get("elapsed_time_s", 0.0),
                        stage=summary["stage"],
                        summary=summary,
                    )
                )

            for stage, result in [
                ("pasteurised", pipeline_result.pasteurisation),
                ("frozen", pipeline_result.freezing),
                ("hardened", pipeline_result.hardening),
            ]:
                session.add(
                    ProcessRunRecord(
                        simulation_id=sim.id,
                        stage=stage,
                        duration_s=getattr(result, "duration_s", getattr(result, "total_time_s", 0.0)),
                        energy_j=getattr(
                            result,
                            "refrigeration_energy_j",
                            getattr(result, "heating_energy_j", 0.0),
                        ),
                        details={},
                    )
                )
            session.commit()
            return sim.id

    def save_experiment(self, comparison) -> int:
        with self.session() as session:
            record = ExperimentRecord(
                name=comparison.name,
                baseline_metrics=comparison.baseline,
                experimental_metrics=comparison.experimental,
                differences=comparison.differences,
            )
            session.add(record)
            session.commit()
            return record.id

    def save_optimisation_run(self, objective_name: str, result) -> int:
        with self.session() as session:
            record = OptimisationRunRecord(
                objective_name=objective_name,
                parameters=list(result.optimal_parameters.keys()),
                optimal_parameters=result.optimal_parameters,
                optimal_value=result.optimal_objective_value,
                converged=result.converged,
            )
            session.add(record)
            session.commit()
            return record.id

    def save_quality_result(self, simulation_id: int, quality_result) -> int:
        with self.session() as session:
            record = QualityResultRecord(
                simulation_id=simulation_id,
                overall_score=quality_result.overall_score,
                subscores=quality_result.subscores,
            )
            session.add(record)
            session.commit()
            return record.id

    def save_energy_result(self, simulation_id: int, energy_breakdown) -> int:
        with self.session() as session:
            record = EnergyResultRecord(
                simulation_id=simulation_id,
                total_kwh=energy_breakdown.total_kwh,
                kwh_per_kg=energy_breakdown.kwh_per_kg,
                kwh_per_litre=energy_breakdown.kwh_per_litre,
                breakdown={
                    "heating_kwh": energy_breakdown.heating_kwh,
                    "homogenisation_kwh": energy_breakdown.homogenisation_kwh,
                    "freezing_kwh": energy_breakdown.freezing_kwh,
                    "hardening_kwh": energy_breakdown.hardening_kwh,
                },
            )
            session.add(record)
            session.commit()
            return record.id
