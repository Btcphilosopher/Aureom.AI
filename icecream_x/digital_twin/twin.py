"""The digital twin.

Implements the architecture described in the spec:

    PHYSICAL PLANT <-> TELEMETRY <-> ICECREAM-X <-> DIGITAL STATE
        <-> PREDICTION <-> OPTIMISATION

:class:`DigitalTwin` keeps three states distinct, as required:

- ``physical_state``: the best available direct read of reality -- in
  this simplified implementation, the most recent telemetry-derived
  state (see :mod:`icecream_x.digital_twin.state_estimator`); in a full
  deployment this would be closer to raw sensor data.
- ``estimated_state``: the model's best current estimate, fusing
  ``physical_state`` with the simulation (currently a direct estimator
  override; see :mod:`icecream_x.digital_twin.state_estimator` for the
  documented simplification).
- ``predicted_state``: a forward simulation from ``estimated_state``
  under a given process/storage plan -- "if we keep running this way,
  where do we end up".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from icecream_x.core.state import ProductState
from icecream_x.digital_twin.state_estimator import estimate_state
from icecream_x.digital_twin.telemetry import TelemetryStream
from icecream_x.storage.freezer import StorageFacility
from icecream_x.storage.temperature_history import TemperatureProfile


@dataclass(slots=True)
class DigitalTwin:
    physical_state: ProductState
    estimated_state: ProductState
    predicted_state: ProductState | None = None
    telemetry: TelemetryStream = field(default_factory=TelemetryStream)
    current_time_s: float = 0.0

    @classmethod
    def from_state(cls, state: ProductState) -> "DigitalTwin":
        return cls(physical_state=state, estimated_state=state, predicted_state=None)

    def ingest_telemetry(self, sensor_name: str, value: float, unit: str = "", *, at_time_s: float | None = None) -> None:
        t = at_time_s if at_time_s is not None else self.current_time_s
        self.telemetry.record(t, sensor_name, value, unit)
        self.current_time_s = max(self.current_time_s, t)
        self.physical_state = estimate_state(self.physical_state, self.telemetry, self.current_time_s)
        self.estimated_state = self.physical_state

    def predict_storage(
        self, facility: StorageFacility, duration_s: float, *, temperature_profile: TemperatureProfile | None = None, dt_s: float = 900.0
    ) -> ProductState:
        from icecream_x.core.simulation import run_storage_simulation

        result = run_storage_simulation(
            self.estimated_state, facility, duration_s, temperature_profile=temperature_profile, dt_s=dt_s
        )
        self.predicted_state = result.final_state
        return self.predicted_state
