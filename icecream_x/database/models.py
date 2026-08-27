"""SQLAlchemy ORM models for persistent experiment storage.

Entirely optional: the simulation engine (:mod:`icecream_x.core`,
:mod:`icecream_x.processing`, ...) never imports this module and runs
identically with or without a database configured. Use
:mod:`icecream_x.database.repository` to persist recipes, simulation
runs, and results when you want a durable experiment log (e.g. behind
the :mod:`icecream_x.api` server).

Works against SQLite (the zero-config default) or PostgreSQL (set
``ICECREAM_X_DATABASE_URL``); see :mod:`icecream_x.database.migrations`
for schema creation.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class IngredientRecord(Base):
    __tablename__ = "ingredients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    category: Mapped[str] = mapped_column(String(50))
    properties: Mapped[dict] = mapped_column(JSON)  # full Ingredient.model_dump()


class RecipeRecord(Base):
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(1000), default="")
    lines: Mapped[list] = mapped_column(JSON)  # [{"ingredient_name": ..., "mass_kg": ...}, ...]
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)

    simulations: Mapped[list["SimulationRecord"]] = relationship(back_populates="recipe")


class EquipmentRecord(Base):
    __tablename__ = "equipment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    equipment_type: Mapped[str] = mapped_column(String(100))
    parameters: Mapped[dict] = mapped_column(JSON)


class SimulationRecord(Base):
    __tablename__ = "simulations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"))
    process_profile: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)

    recipe: Mapped[RecipeRecord] = relationship(back_populates="simulations")
    states: Mapped[list["SimulationStateRecord"]] = relationship(back_populates="simulation")
    process_runs: Mapped[list["ProcessRunRecord"]] = relationship(back_populates="simulation")
    quality_results: Mapped[list["QualityResultRecord"]] = relationship(back_populates="simulation")
    energy_results: Mapped[list["EnergyResultRecord"]] = relationship(back_populates="simulation")


class SimulationStateRecord(Base):
    __tablename__ = "simulation_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    simulation_id: Mapped[int] = mapped_column(ForeignKey("simulations.id"))
    timestamp_s: Mapped[float] = mapped_column(Float)
    stage: Mapped[str] = mapped_column(String(50))
    summary: Mapped[dict] = mapped_column(JSON)

    simulation: Mapped[SimulationRecord] = relationship(back_populates="states")


class ProcessRunRecord(Base):
    __tablename__ = "process_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    simulation_id: Mapped[int] = mapped_column(ForeignKey("simulations.id"))
    stage: Mapped[str] = mapped_column(String(50))
    duration_s: Mapped[float] = mapped_column(Float)
    energy_j: Mapped[float] = mapped_column(Float)
    details: Mapped[dict] = mapped_column(JSON)

    simulation: Mapped[SimulationRecord] = relationship(back_populates="process_runs")


class SensorDataRecord(Base):
    __tablename__ = "sensor_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    simulation_id: Mapped[int] = mapped_column(ForeignKey("simulations.id"), nullable=True)
    timestamp_s: Mapped[float] = mapped_column(Float)
    sensor_name: Mapped[str] = mapped_column(String(100))
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(30), default="")


class ExperimentRecord(Base):
    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(1000), default="")
    baseline_metrics: Mapped[dict] = mapped_column(JSON)
    experimental_metrics: Mapped[dict] = mapped_column(JSON)
    differences: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)


class OptimisationRunRecord(Base):
    __tablename__ = "optimisation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    objective_name: Mapped[str] = mapped_column(String(200))
    parameters: Mapped[dict] = mapped_column(JSON)
    optimal_parameters: Mapped[dict] = mapped_column(JSON)
    optimal_value: Mapped[float] = mapped_column(Float)
    converged: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)


class QualityResultRecord(Base):
    __tablename__ = "quality_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    simulation_id: Mapped[int] = mapped_column(ForeignKey("simulations.id"))
    overall_score: Mapped[float] = mapped_column(Float)
    subscores: Mapped[dict] = mapped_column(JSON)

    simulation: Mapped[SimulationRecord] = relationship(back_populates="quality_results")


class EnergyResultRecord(Base):
    __tablename__ = "energy_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    simulation_id: Mapped[int] = mapped_column(ForeignKey("simulations.id"))
    total_kwh: Mapped[float] = mapped_column(Float)
    kwh_per_kg: Mapped[float] = mapped_column(Float)
    kwh_per_litre: Mapped[float] = mapped_column(Float)
    breakdown: Mapped[dict] = mapped_column(JSON)

    simulation: Mapped[SimulationRecord] = relationship(back_populates="energy_results")
