import pytest

from icecream_x.formulation.fats import CREAM_40
from icecream_x.formulation.recipe import Recipe
from icecream_x.formulation.solids import SKIM_MILK, WHOLE_MILK
from icecream_x.formulation.stabilisers import STABILISER_EMULSIFIER_BLEND
from icecream_x.formulation.sugars import GLUCOSE_SYRUP_42DE, SUCROSE
from icecream_x.rheology.shear import fit_power_law
from icecream_x.rheology.viscosity import mixture_viscosity
from icecream_x.thermodynamics.ice_fraction import phase_state_at_temperature


@pytest.fixture
def composition():
    r = Recipe(name="vanilla")
    r.add(WHOLE_MILK, 40).add(CREAM_40, 25).add(SKIM_MILK, 15)
    r.add(SUCROSE, 12).add(GLUCOSE_SYRUP_42DE, 5).add(STABILISER_EMULSIFIER_BLEND, 0.4)
    return r.composition()


def test_viscosity_increases_as_mix_freezes(composition):
    warm = phase_state_at_temperature(composition, 277.15)  # 4 degC
    cold = phase_state_at_temperature(composition, 268.15)  # -5 degC
    fractions = composition.as_fractions()
    eta_warm = mixture_viscosity(warm, fractions["sugar"] + fractions["lactose"], fractions["stabiliser"])
    eta_cold = mixture_viscosity(cold, fractions["sugar"] + fractions["lactose"], fractions["stabiliser"])
    assert eta_cold.apparent_viscosity_pa_s > eta_warm.apparent_viscosity_pa_s


def test_power_law_fluid_is_shear_thinning():
    fluid = fit_power_law(newtonian_reference_viscosity_pa_s=0.05, total_solids_mass_fraction=0.35)
    assert fluid.flow_behaviour_index < 1.0
    eta_low_shear = fluid.apparent_viscosity_pa_s(1.0)
    eta_high_shear = fluid.apparent_viscosity_pa_s(100.0)
    assert eta_high_shear < eta_low_shear


def test_power_law_rejects_nonpositive_shear_rate():
    fluid = fit_power_law(0.05, 0.35)
    with pytest.raises(ValueError):
        fluid.apparent_viscosity_pa_s(0.0)
