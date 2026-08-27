import pytest

from icecream_x.core.engine import ProcessProfile, run_production_line
from icecream_x.core.state import ProcessStage
from icecream_x.equipment import HTST_DEFAULT, TWO_STAGE_DEFAULT
from icecream_x.processing import homogenise, mix, pasteurise
from icecream_x.scenarios.recipes import vanilla
from icecream_x.utils.validation import check_mass_balance


@pytest.fixture
def recipe():
    return vanilla()


def test_mixing_preserves_mass(recipe):
    state = mix(recipe)
    check_mass_balance(recipe.batch_mass_kg, state.composition.total_mass_kg)


def test_pasteurisation_preserves_mass(recipe):
    state = mix(recipe)
    result = pasteurise(state, HTST_DEFAULT)
    check_mass_balance(state.composition.total_mass_kg, result.final_state.composition.total_mass_kg)


def test_pasteurisation_reaches_target_and_returns(recipe):
    state = mix(recipe, mix_temperature_c=4.0)
    result = pasteurise(state, HTST_DEFAULT, post_cooling_temperature_c=4.0)
    assert result.final_state.temperature_c == pytest.approx(4.0, abs=0.5)
    assert result.heating_time_s > 0
    assert result.holding_time_s == HTST_DEFAULT.holding_time_s


def test_homogenisation_preserves_mass_and_sets_globule_size(recipe):
    state = mix(recipe)
    homogenised = homogenise(state, TWO_STAGE_DEFAULT, mass_flow_kg_s=0.5)
    check_mass_balance(state.composition.total_mass_kg, homogenised.composition.total_mass_kg)
    assert homogenised.microstructure.fat_network is not None
    assert homogenised.microstructure.fat_network.globule_diameter_um > 0


def test_full_pipeline_mass_conservation(recipe):
    pipeline = run_production_line(recipe, ProcessProfile())
    check_mass_balance(recipe.batch_mass_kg, pipeline.final_state.composition.total_mass_kg)
    assert pipeline.final_state.stage == ProcessStage.HARDENED


def test_full_pipeline_is_deterministic(recipe):
    result_a = run_production_line(recipe, ProcessProfile())
    result_b = run_production_line(recipe, ProcessProfile())
    assert result_a.final_state.temperature_k == pytest.approx(result_b.final_state.temperature_k)
    assert result_a.final_state.cumulative_energy_j == pytest.approx(result_b.final_state.cumulative_energy_j)


def test_full_pipeline_produces_frozen_aerated_product(recipe):
    pipeline = run_production_line(recipe, ProcessProfile())
    final = pipeline.final_state
    assert final.temperature_c < 0
    assert final.thermal_state().phase.ice_mass_fraction > 0
    assert final.air_volume_fraction > 0
    assert final.microstructure.ice_crystals is not None
    assert final.microstructure.air_cells is not None
    assert final.microstructure.fat_network is not None


def test_higher_overrun_gives_lower_density(recipe):
    low = run_production_line(recipe, ProcessProfile(overrun_pct=25.0))
    high = run_production_line(recipe, ProcessProfile(overrun_pct=120.0))
    assert high.final_state.product_density_kg_m3() < low.final_state.product_density_kg_m3()
