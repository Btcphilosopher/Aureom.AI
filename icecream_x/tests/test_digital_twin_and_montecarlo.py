import numpy as np
import pytest

from icecream_x.analytics.statistics import run_monte_carlo
from icecream_x.core.engine import ProcessProfile, run_production_line
from icecream_x.digital_twin.twin import DigitalTwin
from icecream_x.scenarios.recipes import vanilla
from icecream_x.storage.freezer import COLD_STORE


@pytest.fixture
def hardened_state():
    return run_production_line(vanilla(), ProcessProfile()).final_state


def test_digital_twin_ingests_temperature_telemetry(hardened_state):
    twin = DigitalTwin.from_state(hardened_state)
    twin.ingest_telemetry("temperature_c", -19.0, "degC", at_time_s=0.0)
    assert twin.physical_state.temperature_c == pytest.approx(-19.0)
    assert twin.estimated_state.temperature_c == pytest.approx(-19.0)


def test_digital_twin_predicts_storage(hardened_state):
    twin = DigitalTwin.from_state(hardened_state)
    predicted = twin.predict_storage(COLD_STORE, duration_s=5 * 24 * 3600, dt_s=3600)
    assert twin.predicted_state is predicted
    assert predicted.microstructure.ice_crystals.mean_diameter_um >= (
        hardened_state.microstructure.ice_crystals.mean_diameter_um
    )


def test_monte_carlo_reproducible_with_fixed_seed():
    def run_once(rng: np.random.Generator) -> dict[str, float]:
        return {"x": float(rng.normal(10.0, 1.0))}

    result_a = run_monte_carlo(run_once, n_samples=50, random_seed=7)
    result_b = run_monte_carlo(run_once, n_samples=50, random_seed=7)
    assert result_a.summary["x"].mean == pytest.approx(result_b.summary["x"].mean)
    assert result_a.summary["x"].p50 == pytest.approx(result_b.summary["x"].p50)


def test_monte_carlo_percentiles_are_ordered():
    def run_once(rng: np.random.Generator) -> dict[str, float]:
        return {"y": float(rng.uniform(0.0, 100.0))}

    result = run_monte_carlo(run_once, n_samples=500, random_seed=1)
    s = result.summary["y"]
    assert s.p10 <= s.p50 <= s.p90
