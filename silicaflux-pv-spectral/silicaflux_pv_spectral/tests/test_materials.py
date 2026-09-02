import numpy as np
import pytest

from silicaflux_pv_spectral.materials import (
    CADMIUM_TELLURIDE,
    CIGS,
    GALLIUM_ARSENIDE,
    MATERIAL_LIBRARY,
    PEROVSKITE,
    SILICON,
    absorption_coefficient_cm,
    bandgap_at_temperature_eV,
    lambda_cutoff_nm,
    photon_can_generate_carrier,
    refractive_index,
)


def test_material_library_has_the_six_named_entries_plus_tandem_top():
    for name in ["SILICON", "PEROVSKITE", "GALLIUM_ARSENIDE", "CADMIUM_TELLURIDE", "CIGS"]:
        assert name in MATERIAL_LIBRARY
    assert "PEROVSKITE_WIDEGAP" in MATERIAL_LIBRARY  # tandem top-cell default


def test_materials_are_not_interchangeable():
    names = {m.material_name for m in MATERIAL_LIBRARY.values()}
    bandgaps = {m.bandgap_eV for m in MATERIAL_LIBRARY.values()}
    assert len(names) == len(MATERIAL_LIBRARY)
    assert len(bandgaps) > 1  # distinct bandgaps -> genuinely different devices


@pytest.mark.parametrize("material", [SILICON, PEROVSKITE, GALLIUM_ARSENIDE, CADMIUM_TELLURIDE, CIGS])
def test_absorption_coefficient_is_nonnegative_and_finite(material):
    wl = np.linspace(280.0, 2500.0, 500)
    alpha = absorption_coefficient_cm(material, wl)
    assert np.all(np.isfinite(alpha))
    assert np.all(alpha >= 0.0)


@pytest.mark.parametrize("material", [SILICON, PEROVSKITE, GALLIUM_ARSENIDE, CADMIUM_TELLURIDE, CIGS])
def test_absorption_coefficient_is_high_in_deep_uv(material):
    alpha_deep_uv = absorption_coefficient_cm(material, np.array([285.0]))[0]
    assert alpha_deep_uv > 1e4  # deep-UV interband transitions dominate for every material family


@pytest.mark.parametrize("material", [SILICON, PEROVSKITE, GALLIUM_ARSENIDE, CADMIUM_TELLURIDE, CIGS])
def test_absorption_coefficient_drops_sharply_below_bandgap(material):
    cutoff = lambda_cutoff_nm(material.bandgap_eV)
    alpha_above = absorption_coefficient_cm(material, np.array([cutoff - 5.0]))[0]
    alpha_below = absorption_coefficient_cm(material, np.array([cutoff + 100.0]))[0]
    assert alpha_below < alpha_above


def test_bandgap_filter_matches_cutoff_wavelength():
    material = SILICON
    cutoff = lambda_cutoff_nm(material.bandgap_eV)
    from silicaflux_pv_spectral.photon import photon_energy_ev

    just_above_gap_wavelength = cutoff - 1.0
    just_below_gap_wavelength = cutoff + 1.0
    e_above = photon_energy_ev(np.array([just_above_gap_wavelength]))[0]
    e_below = photon_energy_ev(np.array([just_below_gap_wavelength]))[0]
    assert photon_can_generate_carrier(e_above, material.bandgap_eV)
    assert not photon_can_generate_carrier(e_below, material.bandgap_eV)


def test_refractive_index_within_physical_bounds():
    wl = np.linspace(280.0, 2500.0, 200)
    for material in MATERIAL_LIBRARY.values():
        n = refractive_index(material, wl)
        assert np.all(n >= 1.0)
        assert np.all(n <= 6.0)


def test_varshni_bandgap_narrows_with_increasing_temperature():
    eg_cold = bandgap_at_temperature_eV(SILICON, 250.0)
    eg_stc = bandgap_at_temperature_eV(SILICON, 298.15)
    eg_hot = bandgap_at_temperature_eV(SILICON, 350.0)
    assert eg_cold > eg_stc > eg_hot
    assert eg_stc == pytest.approx(SILICON.bandgap_eV, abs=1e-9)


def test_silicon_known_temperature_coefficient_is_negative_and_realistic():
    assert -0.006 < SILICON.temperature_coefficient < -0.003
