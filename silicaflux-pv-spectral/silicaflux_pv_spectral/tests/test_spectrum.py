import numpy as np
import pytest

from silicaflux_pv_spectral.spectrum import (
    AtmosphericConditions,
    SolarSpectrum,
    atmospheric_transmission,
    extraterrestrial_spectrum,
    integrate_band,
    relative_airmass,
    terrestrial_spectrum,
)


def test_solar_spectrum_rejects_mismatched_shapes():
    with pytest.raises(ValueError):
        SolarSpectrum(np.array([1.0, 2.0]), np.array([1.0]))


def test_solar_spectrum_rejects_negative_irradiance():
    with pytest.raises(ValueError):
        SolarSpectrum(np.array([500.0]), np.array([-1.0]))


def test_extraterrestrial_spectrum_normalises_to_solar_constant_order():
    spectrum = extraterrestrial_spectrum()
    # The 280-2500 nm slice necessarily carries less than the full-spectrum
    # solar constant (some power lies outside this window), but should be
    # the dominant fraction of it.
    assert 1000.0 < spectrum.total_irradiance_w_m2 < 1361.0


def test_extraterrestrial_spectrum_peaks_near_wien_prediction():
    spectrum = extraterrestrial_spectrum()
    peak_wavelength = spectrum.wavelength_nm[np.argmax(spectrum.spectral_irradiance_w_m2_nm)]
    # Wien's law for a 5778 K blackbody predicts ~501 nm.
    assert 450.0 < peak_wavelength < 550.0


def test_relative_airmass_near_unity_at_zenith():
    assert relative_airmass(0.0) == pytest.approx(1.0, abs=1e-3)


def test_relative_airmass_default_is_approximately_am1p5():
    conditions = AtmosphericConditions()
    assert relative_airmass(conditions.solar_zenith_deg) == pytest.approx(1.5, abs=0.05)


def test_atmospheric_transmission_bounded_and_attenuates_uv_more_than_nir():
    from silicaflux_pv_spectral.constants import wavelength_grid_nm

    grid = wavelength_grid_nm()
    transmission = atmospheric_transmission(grid)
    assert np.all(transmission >= 0.0)
    assert np.all(transmission <= 1.0)

    uv_mask = (grid >= 300.0) & (grid <= 310.0)
    nir_mask = (grid >= 900.0) & (grid <= 910.0)
    assert transmission[uv_mask].mean() < transmission[nir_mask].mean()


def test_deep_uvc_below_290nm_is_almost_fully_absorbed_by_ozone():
    grid = np.array([282.0, 285.0, 288.0])
    transmission = atmospheric_transmission(grid)
    assert np.all(transmission < 0.15)
    assert np.all(np.diff(transmission) > 0)  # monotonically opens up approaching the Huggins band


def test_terrestrial_spectrum_is_never_brighter_than_extraterrestrial():
    et = extraterrestrial_spectrum()
    terr = terrestrial_spectrum()
    assert np.all(terr.spectral_irradiance_w_m2_nm <= et.spectral_irradiance_w_m2_nm + 1e-9)


def test_terrestrial_total_irradiance_is_plausible():
    terr = terrestrial_spectrum()
    # Should land in the same ballpark as the ~1000 W/m^2 AM1.5G reference
    # convention without being forced to match it exactly.
    assert 600.0 < terr.total_irradiance_w_m2 < 1400.0


def test_uv_available_uses_atmospheric_transmission():
    from silicaflux_pv_spectral.spectrum import uv_available

    et = extraterrestrial_spectrum()
    available = uv_available(et)
    transmission = atmospheric_transmission(et.wavelength_nm)
    assert np.allclose(available, et.spectral_irradiance_w_m2_nm * transmission)


def test_band_irradiance_sums_to_total():
    spectrum = terrestrial_spectrum()
    band_sum = sum(spectrum.in_band(name) for name in ["UVB", "UVA", "VISIBLE", "NIR"])
    assert band_sum == pytest.approx(spectrum.total_irradiance_w_m2, rel=1e-6)


def test_integrate_band_matches_full_trapezoid():
    x = np.linspace(0, 10, 1001)
    y = np.sin(x) + 2.0
    full = integrate_band(y, x)
    assert full == pytest.approx(float(np.trapezoid(y, x)))
