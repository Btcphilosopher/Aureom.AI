"""Structured process-event log.

Every process step and every simulation timestep can emit
:class:`ProcessEvent` records into an :class:`EventLog`. This is separate
from the state time series (:mod:`icecream_x.core.simulation` stores the
full :class:`~icecream_x.core.state.ProductState` history) -- it is
specifically for discrete, human/machine-readable milestones ("entered
freezer", "pasteurisation hold complete", "storage excursion started")
that are awkward to infer purely from a state diff.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ProcessEvent:
    timestamp_s: float
    stage: str
    description: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EventLog:
    events: list[ProcessEvent] = field(default_factory=list)

    def record(self, timestamp_s: float, stage: str, description: str, **data: Any) -> None:
        self.events.append(
            ProcessEvent(timestamp_s=timestamp_s, stage=stage, description=description, data=data)
        )

    def filter_by_stage(self, stage: str) -> list[ProcessEvent]:
        return [e for e in self.events if e.stage == stage]

    def as_records(self) -> list[dict[str, Any]]:
        return [
            {"timestamp_s": e.timestamp_s, "stage": e.stage, "description": e.description, **e.data}
            for e in self.events
        ]
