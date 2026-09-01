"""
Production scheduler and changeover optimiser (spec items 21-22).

Sequences production orders to minimise total changeover time and
tardiness against due dates -- a nearest-neighbour heuristic over a
recipe-to-recipe changeover matrix (exact sequencing is a TSP variant,
NP-hard at real order-book sizes).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class SchedulableOrder:
    order_id: str
    recipe: str            # e.g. "LFP-prismatic-100Ah"
    quantity: int
    due_date: datetime
    priority: int = 1


@dataclass
class ChangeoverMatrix:
    """Setup/cleaning/tooling/quality-check time (hours) between recipes."""

    times_hours: dict[tuple[str, str], float]
    default_hours: float = 2.0

    def time_between(self, a: str, b: str) -> float:
        if a == b:
            return 0.0
        return self.times_hours.get((a, b), self.times_hours.get((b, a), self.default_hours))


@dataclass
class ScheduleResult:
    sequence: list[SchedulableOrder]
    total_changeover_hours: float
    total_processing_hours: float
    tardiness_hours: float
    makespan_hours: float


class ChangeoverOptimiser:
    def optimise_sequence(self, orders: list[SchedulableOrder], matrix: ChangeoverMatrix) -> list[SchedulableOrder]:
        if not orders:
            return []
        remaining = list(orders)
        # Start from the order with the earliest due date to keep tardiness in check.
        remaining.sort(key=lambda o: o.due_date)
        sequence = [remaining.pop(0)]
        while remaining:
            current_recipe = sequence[-1].recipe
            # Nearest-neighbour on changeover cost, tie-broken by due date urgency.
            next_order = min(remaining, key=lambda o: (matrix.time_between(current_recipe, o.recipe), o.due_date))
            remaining.remove(next_order)
            sequence.append(next_order)
        return sequence


class ProductionScheduler:
    def __init__(self, changeover_matrix: ChangeoverMatrix, throughput_units_per_hour: float) -> None:
        self.matrix = changeover_matrix
        self.throughput_units_per_hour = throughput_units_per_hour
        self.optimiser = ChangeoverOptimiser()

    def schedule(self, orders: list[SchedulableOrder], start_time: datetime) -> ScheduleResult:
        sequence = self.optimiser.optimise_sequence(orders, self.matrix)

        total_changeover = 0.0
        total_processing = 0.0
        total_tardiness = 0.0
        clock_hours = 0.0
        prev_recipe: str | None = None

        for order in sequence:
            if prev_recipe is not None:
                changeover = self.matrix.time_between(prev_recipe, order.recipe)
                total_changeover += changeover
                clock_hours += changeover
            processing = order.quantity / self.throughput_units_per_hour
            total_processing += processing
            clock_hours += processing

            due_hours = (order.due_date - start_time).total_seconds() / 3600.0
            total_tardiness += max(0.0, clock_hours - due_hours)
            prev_recipe = order.recipe

        return ScheduleResult(
            sequence=sequence,
            total_changeover_hours=total_changeover,
            total_processing_hours=total_processing,
            tardiness_hours=total_tardiness,
            makespan_hours=clock_hours,
        )
