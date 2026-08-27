import pytest

from icecream_x.core.engine import ProcessProfile, run_production_line
from icecream_x.scenarios.recipes import vanilla
from icecream_x.storage.cold_chain import ColdChainStage, simulate_cold_chain
from icecream_x.storage.freezer import COLD_STORE
from icecream_x.storage.temperature_history import TemperatureProfile, uninterrupted


@pytest.fixture(scope="module")
def hardened_state():
    pipeline = run_production_line(vanilla(), ProcessProfile())
    return pipeline.final_state


def test_uninterrupted_storage_grows_crystals(hardened_state):
    stage = ColdChainStage("stable", COLD_STORE, duration_s=15 * 24 * 3600, temperature_profile=uninterrupted(-25.0))
    result = simulate_cold_chain(hardened_state, [stage], dt_s=3600)
    initial = hardened_state.microstructure.ice_crystals.mean_diameter_um
    final = result.final_state.microstructure.ice_crystals.mean_diameter_um
    assert final > initial


def test_excursion_grows_crystals_more_than_uninterrupted(hardened_state):
    stable_stage = ColdChainStage(
        "stable", COLD_STORE, duration_s=15 * 24 * 3600, temperature_profile=uninterrupted(-25.0)
    )
    stable_result = simulate_cold_chain(hardened_state, [stable_stage], dt_s=1800)

    profile = TemperatureProfile(baseline_temperature_c=-25.0)
    profile.add_excursion(start_time_s=5 * 24 * 3600, duration_s=6 * 3600, peak_temperature_c=-12.0)
    excursion_stage = ColdChainStage("excursion", COLD_STORE, duration_s=15 * 24 * 3600, temperature_profile=profile)
    excursion_result = simulate_cold_chain(hardened_state, [excursion_stage], dt_s=1800)

    stable_final = stable_result.final_state.microstructure.ice_crystals.mean_diameter_um
    excursion_final = excursion_result.final_state.microstructure.ice_crystals.mean_diameter_um
    assert excursion_final > stable_final


def test_temperature_profile_returns_to_baseline_after_excursion():
    profile = TemperatureProfile(baseline_temperature_c=-20.0)
    profile.add_excursion(start_time_s=1000.0, duration_s=200.0, peak_temperature_c=-10.0)
    assert profile.temperature_at(0.0) == pytest.approx(-20.0)
    assert profile.temperature_at(1100.0) == pytest.approx(-10.0)  # midpoint = peak
    assert profile.temperature_at(1200.0) == pytest.approx(-20.0)  # back to baseline
    assert profile.temperature_at(5000.0) == pytest.approx(-20.0)


def test_cold_chain_refrigeration_energy_is_positive(hardened_state):
    stage = ColdChainStage("stable", COLD_STORE, duration_s=5 * 24 * 3600, temperature_profile=uninterrupted(-25.0))
    result = simulate_cold_chain(hardened_state, [stage], dt_s=3600)
    assert result.total_energy_j > 0
