"""
Digital-twin scenario mode and what-if simulator (spec items 50-51).

A ``Scenario`` is a set of overrides applied to a base factory config/run
before re-simulating -- the whole factory model recalculates from those
overrides rather than the outcome being interpolated or hard-coded.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np


@dataclass
class Scenario:
    name: str
    description: str
    overrides: dict[str, float]  # e.g. {"demand_multiplier": 1.3, "energy_price_multiplier": 2.0}


@dataclass
class ScenarioResult:
    scenario: Scenario
    metrics: dict[str, float]


PREDEFINED_SCENARIOS: dict[str, Scenario] = {
    "BASE_CASE": Scenario("BASE_CASE", "Current configuration, no shocks.", {}),
    "HIGH_DEMAND": Scenario("HIGH_DEMAND", "Demand up 30%.", {"demand_multiplier": 1.3}),
    "LOW_DEMAND": Scenario("LOW_DEMAND", "Demand down 30%.", {"demand_multiplier": 0.7}),
    "ENERGY_SHOCK": Scenario("ENERGY_SHOCK", "Electricity price doubles.", {"energy_price_multiplier": 2.0}),
    "MATERIAL_SHORTAGE": Scenario("MATERIAL_SHORTAGE", "Key material availability drops 40%.", {"material_availability_multiplier": 0.6}),
    "MACHINE_FAILURE": Scenario("MACHINE_FAILURE", "One production line offline.", {"lines_offline": 1}),
    "SUPPLY_DISRUPTION": Scenario("SUPPLY_DISRUPTION", "Supplier disruption probability doubles.", {"disruption_probability_multiplier": 2.0}),
    "CAPACITY_EXPANSION": Scenario("CAPACITY_EXPANSION", "One additional production line.", {"additional_lines": 1}),
}


class ScenarioEngine:
    def __init__(self, run_fn: Callable[[dict[str, float]], dict[str, float]]) -> None:
        """`run_fn(overrides) -> metrics dict` should build/re-run the factory
        model under the given overrides and return the KPIs to compare."""
        self.run_fn = run_fn

    def run_scenario(self, scenario: Scenario) -> ScenarioResult:
        metrics = self.run_fn(scenario.overrides)
        return ScenarioResult(scenario=scenario, metrics=metrics)

    def compare(self, scenarios: list[Scenario]) -> list[ScenarioResult]:
        return [self.run_scenario(s) for s in scenarios]


class WhatIfSimulator:
    """Maps a small set of natural-language-shaped questions onto scenario
    overrides the ScenarioEngine can execute."""

    def __init__(self, engine: ScenarioEngine) -> None:
        self.engine = engine

    def line_speed_change(self, pct_change: float) -> ScenarioResult:
        return self.engine.run_scenario(Scenario("LINE_SPEED_CHANGE", f"Line speed {pct_change:+.0f}%.",
                                                   {"line_speed_multiplier": 1.0 + pct_change / 100.0}))

    def electricity_price_multiplier(self, multiplier: float) -> ScenarioResult:
        return self.engine.run_scenario(Scenario("ENERGY_PRICE_CHANGE", f"Electricity price x{multiplier:.2f}.",
                                                   {"energy_price_multiplier": multiplier}))

    def yield_change(self, from_pct: float, to_pct: float) -> ScenarioResult:
        return self.engine.run_scenario(Scenario("YIELD_CHANGE", f"Yield {from_pct:.0f}% -> {to_pct:.0f}%.",
                                                   {"yield_override_pct": to_pct}))

    def line_offline(self, num_lines: int = 1) -> ScenarioResult:
        return self.engine.run_scenario(Scenario("LINE_OFFLINE", f"{num_lines} production line(s) offline.",
                                                   {"lines_offline": num_lines}))

    def material_price_change(self, material: str, pct_change: float) -> ScenarioResult:
        return self.engine.run_scenario(Scenario("MATERIAL_PRICE_CHANGE", f"{material} price {pct_change:+.0f}%.",
                                                   {f"material_price_multiplier::{material}": 1.0 + pct_change / 100.0}))
