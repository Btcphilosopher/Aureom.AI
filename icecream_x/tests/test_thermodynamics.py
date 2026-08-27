import numpy as np
import pytest

from icecream_x.formulation.fats import CREAM_40
from icecream_x.formulation.recipe import Recipe
from icecream_x.formulation.solids import SKIM_MILK, WHOLE_MILK
from icecream_x.formulation.stabilisers import STABILISER_EMULSIFIER_BLEND
from icecream_x.formulation.sugars import GLUCOSE_SYRUP_42DE, SUCROSE
from icecream_x.thermodynamics.enthalpy import apparent_specific_heat_j_kg_k, specific_enthalpy_j_kg
from icecream_x.thermodynamics.freezing_point import freezing_point_analysis
from icecream_x.thermodynamics.ice_fraction import phase_state_at_temperature


@pytest.fixture
def composition():
    r = Recipe(name="vanilla")
    r.add(WHOLE_MILK, 40).add(CREAM_40, 25).add(SKIM_MILK, 15)
    r.add(SUCROSE, 12).add(GLUCOSE_SYRUP_42DE, 5).add(STABILISER_EMULSIFIER_BLEND, 0.4)
    return r.composition()


def test_initial_freezing_point_is_below_zero_and_plausible(composition):
    fp = freezing_point_analysis(composition)
    # Typical ice cream mixes freeze in the range of about -1 to -3 degC.
    assert -4.0 < fp.initial_freezing_point_c < -0.3


def test_no_ice_above_freezing_point(composition):
    fp = freezing_point_analysis(composition)
    above_freezing_k = fp.initial_freezing_point_k + 1.0
    state = phase_state_at_temperature(composition, above_freezing_k)
    assert state.ice_mass_fraction == pytest.approx(0.0, abs=1e-9)


def test_ice_fraction_is_monotonic_and_bounded(composition):
    temps_c = np.linspace(5.0, -35.0, 60)
    fractions = [
        phase_state_at_temperature(composition, t + 273.15).ice_mass_fraction for t in temps_c
    ]
    for f in fractions:
        assert -1e-9 <= f <= 1.0 + 1e-9
    # Monotonic non-decreasing as temperature falls (temps_c is descending).
    for a, b in zip(fractions, fractions[1:]):
        assert b >= a - 1e-9


def test_ice_fraction_approaches_realistic_hardening_value(composition):
    state = phase_state_at_temperature(composition, 255.15)  # -18 degC
    # A typical mix is roughly 70-85% frozen at -18 degC.
    assert 0.55 < state.ice_mass_fraction < 0.95


def test_mass_balance_of_phase_state(composition):
    state = phase_state_at_temperature(composition, 250.0)
    total = state.ice_kg + state.unfrozen_water_kg + state.fat_kg + state.solids_non_fat_kg
    assert total == pytest.approx(state.total_mass_kg, rel=1e-9)


def test_specific_enthalpy_is_monotonically_increasing(composition):
    reference_k = 213.15
    temps_c = [-40, -25, -15, -8, -3, -1, 0, 4, 10]
    values = [
        specific_enthalpy_j_kg(composition, t + 273.15, reference_k) for t in temps_c
    ]
    for a, b in zip(values, values[1:]):
        assert b > a


def test_apparent_specific_heat_is_always_positive(composition):
    for t_c in [-40, -20, -10, -5, -2, -1, 0, 5, 20]:
        cp = apparent_specific_heat_j_kg_k(composition, t_c + 273.15)
        assert cp > 0


def test_apparent_specific_heat_spikes_near_freezing_point(composition):
    fp = freezing_point_analysis(composition)
    near_freezing = apparent_specific_heat_j_kg_k(composition, fp.initial_freezing_point_k - 1.0)
    far_below = apparent_specific_heat_j_kg_k(composition, fp.initial_freezing_point_k - 20.0)
    assert near_freezing > far_below
