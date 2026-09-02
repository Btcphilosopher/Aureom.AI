from dataclasses import replace

import pytest

from silicaflux_pv_spectral.materials import GALLIUM_ARSENIDE, PEROVSKITE, SILICON
from silicaflux_pv_spectral.recombination import carrier_lifetime


@pytest.mark.parametrize("material", [SILICON, PEROVSKITE, GALLIUM_ARSENIDE])
def test_effective_lifetime_is_shorter_than_every_individual_channel(material):
    state = carrier_lifetime(material)
    assert state.tau_effective_ns <= state.tau_srh_ns
    assert state.tau_effective_ns <= state.tau_radiative_ns
    assert state.tau_effective_ns <= state.tau_auger_ns
    assert state.tau_effective_ns <= state.tau_surface_ns


@pytest.mark.parametrize("material", [SILICON, PEROVSKITE, GALLIUM_ARSENIDE])
def test_bulk_collection_efficiency_in_unit_interval(material):
    state = carrier_lifetime(material)
    assert 0.0 <= state.bulk_collection_efficiency <= 1.0


def test_higher_injection_shortens_radiative_and_auger_lifetime():
    low = carrier_lifetime(SILICON, delta_n_cm3=1e14)
    high = carrier_lifetime(SILICON, delta_n_cm3=1e17)
    assert high.tau_radiative_ns < low.tau_radiative_ns
    assert high.tau_auger_ns < low.tau_auger_ns


def test_worse_surface_recombination_velocity_shortens_lifetime_and_hurts_collection():
    good_surface = replace(SILICON, surface_recomb_velocity_cm_s=10.0)
    bad_surface = replace(SILICON, surface_recomb_velocity_cm_s=1.0e6)
    good_state = carrier_lifetime(good_surface)
    bad_state = carrier_lifetime(bad_surface)
    assert bad_state.tau_surface_ns < good_state.tau_surface_ns
    assert bad_state.bulk_collection_efficiency <= good_state.bulk_collection_efficiency


def test_higher_diffusion_coefficient_improves_bulk_collection():
    poor_transport = replace(SILICON, diffusion_coefficient_cm2_s=0.1)
    good_transport = replace(SILICON, diffusion_coefficient_cm2_s=100.0)
    assert (
        carrier_lifetime(good_transport).bulk_collection_efficiency
        >= carrier_lifetime(poor_transport).bulk_collection_efficiency
    )


def test_diffusion_length_matches_sqrt_d_tau():
    import numpy as np

    state = carrier_lifetime(SILICON)
    expected_l = np.sqrt(SILICON.diffusion_coefficient_cm2_s * state.tau_effective_ns * 1e-9)
    assert state.diffusion_length_cm == pytest.approx(expected_l, rel=1e-9)
