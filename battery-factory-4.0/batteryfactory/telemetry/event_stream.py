"""
Factory event stream (spec item 55) and telemetry architecture (spec item
53): a simple in-process publish/subscribe bus with realistic timestamps
and sensor schemas, designed so the same interface can later be backed by a
real message bus (Kafka/MQTT/etc.) without changing callers.

    MACHINE SENSOR -> EDGE GATEWAY -> TELEMETRY BUS -> DIGITAL TWIN -> ANALYTICS -> DASHBOARD

``EventBus`` plays the "TELEMETRY BUS" role for both discrete factory
events (``EventType``) and continuous sensor readings.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable

from batteryfactory.datamodel.models import EventType, FactoryEvent


@dataclass
class SensorReading:
    """The wire schema an edge gateway would emit for one sensor sample."""

    sensor_id: str
    machine_id: str | None
    metric: str
    value: float
    unit: str
    timestamp: datetime


class EventBus:
    """Publish/subscribe telemetry bus with a bounded in-memory ring buffer."""

    def __init__(self, sim_epoch: datetime | None = None, max_buffer: int = 200_000) -> None:
        self.sim_epoch = sim_epoch or datetime.utcnow()
        self.max_buffer = max_buffer
        self.events: list[FactoryEvent] = []
        self.readings: list[SensorReading] = []
        self._event_subscribers: list[Callable[[FactoryEvent], None]] = []
        self._reading_subscribers: list[Callable[[SensorReading], None]] = []

    def _sim_time_to_datetime(self, sim_hours: float) -> datetime:
        return self.sim_epoch + timedelta(hours=sim_hours)

    def subscribe_events(self, callback: Callable[[FactoryEvent], None]) -> None:
        self._event_subscribers.append(callback)

    def subscribe_readings(self, callback: Callable[[SensorReading], None]) -> None:
        self._reading_subscribers.append(callback)

    def emit(self, event_type: EventType, payload: dict, sim_hours: float, source: str = "simulation") -> FactoryEvent:
        evt = FactoryEvent(event_type=event_type, timestamp=self._sim_time_to_datetime(sim_hours), payload=payload, source=source)
        self.events.append(evt)
        if len(self.events) > self.max_buffer:
            self.events.pop(0)
        for cb in self._event_subscribers:
            cb(evt)
        return evt

    def record_reading(self, sensor_id: str, machine_id: str | None, metric: str, value: float, unit: str, sim_hours: float) -> SensorReading:
        reading = SensorReading(sensor_id, machine_id, metric, value, unit, self._sim_time_to_datetime(sim_hours))
        self.readings.append(reading)
        if len(self.readings) > self.max_buffer:
            self.readings.pop(0)
        for cb in self._reading_subscribers:
            cb(reading)
        return reading

    def events_of_type(self, event_type: EventType) -> list[FactoryEvent]:
        return [e for e in self.events if e.event_type == event_type]

    def count_by_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for e in self.events:
            counts[e.event_type.value] = counts.get(e.event_type.value, 0) + 1
        return counts
