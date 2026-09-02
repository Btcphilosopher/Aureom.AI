import pytest

from silicaflux_pv_spectral.degradation import (
    DegradationParameters,
    annualise_power_w_m2,
    degradation_rate_per_year,
    evaluate_degradation,
    evaluate_uv_tradeoff,
)
from silicaflux_pv_spectral.materials import PEROVSKITE, SILICON


def test_degradation_rate_is_nonnegative():
    rate = degradation_rate_per_year(40.0, 298.15, SILICON)
    assert rate >= 0.0


def test_higher_uv_irradiance_increases_degradation_rate():
    low = degradation_rate_per_year(20.0, 298.15, SILICON)
    high = degradation_rate_per_year(80.0, 298.15, SILICON)
    assert high > low


def test_higher_temperature_increases_degradation_rate():
    cold = degradation_rate_per_year(40.0, 280.0, SILICON)
    hot = degradation_rate_per_year(40.0, 340.0, SILICON)
    assert hot > cold


def test_less_stable_material_degrades_faster():
    stable_rate = degradation_rate_per_year(40.0, 298.15, SILICON)
    fragile_rate = degradation_rate_per_year(40.0, 298.15, PEROVSKITE)
    assert fragile_rate > stable_rate  # PEROVSKITE has a lower material_stability_factor


def test_less_stable_encapsulant_increases_degradation_rate():
    stable = degradation_rate_per_year(40.0, 298.15, SILICON, encapsulant_stability_factor=1.0)
    fragile = degradation_rate_per_year(40.0, 298.15, SILICON, encapsulant_stability_factor=0.3)
    assert fragile > stable


def test_evaluate_degradation_monotonically_declining_annual_energy():
    annual = annualise_power_w_m2(140.0)
    result = evaluate_degradation(40.0, 298.15, SILICON, annual, project_lifetime_years=25.0)
    energies = result.annual_energy_w_h_m2_by_year
    assert len(energies) == 25
    assert (energies[:-1] >= energies[1:]).all()
    assert 0.0 <= result.end_of_life_performance_fraction <= 1.0
    assert result.lifetime_energy_loss_w_h_m2 >= 0.0


def test_zero_degradation_rate_means_no_lifetime_loss():
    params = DegradationParameters(rate_prefactor_per_year=0.0)
    annual = annualise_power_w_m2(140.0)
    result = evaluate_degradation(40.0, 298.15, SILICON, annual, params=params)
    assert result.degradation_rate_per_year == 0.0
    assert result.lifetime_energy_loss_w_h_m2 == pytest.approx(0.0, abs=1e-6)
    assert result.lifetime_energy_w_h_m2 == pytest.approx(annual * 25, rel=1e-6)


def test_uv_tradeoff_can_be_net_negative_when_degradation_dominates():
    annual = annualise_power_w_m2(140.0)
    baseline = evaluate_degradation(40.0, 298.15, SILICON, annual, encapsulant_stability_factor=1.0)

    annual_opt = annualise_power_w_m2(150.0)
    optimised = evaluate_degradation(95.0, 298.15, SILICON, annual_opt, encapsulant_stability_factor=0.6)

    tradeoff = evaluate_uv_tradeoff(baseline, optimised)
    assert tradeoff.short_term_gain_w_h_m2_yr > 0.0
    assert tradeoff.net_lifetime_value_w_h_m2 < 0.0
    assert not tradeoff.worth_it


def test_uv_tradeoff_can_be_net_positive_for_a_modest_stability_neutral_gain():
    annual = annualise_power_w_m2(140.0)
    baseline = evaluate_degradation(40.0, 298.15, SILICON, annual, encapsulant_stability_factor=1.0)

    annual_opt = annualise_power_w_m2(143.0)
    optimised = evaluate_degradation(45.0, 298.15, SILICON, annual_opt, encapsulant_stability_factor=1.0)

    tradeoff = evaluate_uv_tradeoff(baseline, optimised)
    assert tradeoff.net_lifetime_value_w_h_m2 > 0.0
    assert tradeoff.worth_it
