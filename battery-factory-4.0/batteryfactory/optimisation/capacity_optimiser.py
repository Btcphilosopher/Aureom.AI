"""Factory capacity optimiser (spec item 44): constrained grid search over
machine count, line speed, shift pattern and automation level."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Callable


@dataclass
class CapacityDecision:
    num_lines: int
    line_speed_multiplier: float
    shifts_per_day: int
    automation_level: float  # 0..1, higher = more capex, less labour opex


@dataclass
class CapacityConstraints:
    max_capital: float
    max_labour_hours_per_year: float
    max_energy_kwh_per_year: float
    max_floor_area_m2: float


@dataclass
class CapacityOptimumResult:
    decision: CapacityDecision
    profit: float
    feasible: bool
    evaluated_count: int


class FactoryCapacityOptimiser:
    def search(
        self,
        candidate_lines: list[int],
        candidate_speeds: list[float],
        candidate_shifts: list[int],
        candidate_automation: list[float],
        constraints: CapacityConstraints,
        evaluate: Callable[[CapacityDecision], dict[str, float]],
    ) -> CapacityOptimumResult:
        """
        `evaluate` must return a dict with keys: capital_required, labour_hours,
        energy_kwh, floor_area_m2, profit. Every combination violating a
        constraint is discarded before comparing profit.
        """
        best: CapacityOptimumResult | None = None
        evaluated = 0
        for lines, speed, shifts, automation in product(candidate_lines, candidate_speeds, candidate_shifts, candidate_automation):
            decision = CapacityDecision(lines, speed, shifts, automation)
            metrics = evaluate(decision)
            evaluated += 1
            feasible = (
                metrics["capital_required"] <= constraints.max_capital
                and metrics["labour_hours"] <= constraints.max_labour_hours_per_year
                and metrics["energy_kwh"] <= constraints.max_energy_kwh_per_year
                and metrics["floor_area_m2"] <= constraints.max_floor_area_m2
            )
            if not feasible:
                continue
            if best is None or metrics["profit"] > best.profit:
                best = CapacityOptimumResult(decision, metrics["profit"], True, evaluated)

        if best is None:
            return CapacityOptimumResult(CapacityDecision(0, 0, 0, 0), 0.0, False, evaluated)
        best.evaluated_count = evaluated
        return best
