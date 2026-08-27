"""State estimation: fuse a simulated state with real telemetry.

The simplest possible sensor-fusion strategy is implemented here: where a
telemetry reading exists for a quantity the simulation also predicts
(currently: product temperature), the measured value overrides the
simulated one, since a direct thermocouple/RTD reading is normally more
trustworthy than a model prediction. Everything the simulation predicts
that has *no* corresponding sensor (ice fraction, viscosity,
microstructure...) is left as the model's estimate, recomputed
consistently at the corrected temperature.

This is intentionally simple (a "measurement override", not a Kalman
filter/Bayesian fusion with uncertainty propagation) -- documented here as
the extension point: a more sophisticated estimator would weight the
model prediction and measurement by their relative uncertainties instead
of fully trusting the sensor.
"""

from __future__ import annotations

from icecream_x.core.state import ProductState
from icecream_x.digital_twin.telemetry import TelemetryStream
from icecream_x.utils.units import celsius_to_kelvin


def estimate_state(
    predicted_state: ProductState, telemetry: TelemetryStream, at_time_s: float
) -> ProductState:
    """Correct ``predicted_state`` using the latest telemetry at or before ``at_time_s``."""
    temperature_reading = telemetry.latest("temperature_c", before_or_at_s=at_time_s)
    if temperature_reading is None:
        return predicted_state
    return predicted_state.evolve(temperature_k=celsius_to_kelvin(temperature_reading.value))
