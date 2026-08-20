import numpy as np
import pytest

from hydroflux.core.config import EconomicConfig
from hydroflux.economics.economics import EconomicEngine, irr, lcoe, npv, payback_period


def test_npv_at_zero_discount_rate_is_sum_of_cashflows():
    flows = [-100, 30, 30, 30, 30]
    assert npv(flows, 0.0) == pytest.approx(sum(flows))


def test_npv_decreases_with_discount_rate():
    flows = [-100, 50, 50, 50]
    low = npv(flows, 0.02)
    high = npv(flows, 0.20)
    assert high < low


def test_irr_recovers_known_rate():
    rate = 0.10
    flows = [-1000, 1000 * rate, 1000 * rate, 1000 * (1 + rate)]
    result = irr(flows)
    assert result == pytest.approx(rate, abs=1e-3)


def test_irr_none_when_all_cashflows_positive():
    assert irr([100, 100, 100]) is None


def test_payback_period_zero_when_immediately_positive():
    assert payback_period([10, 20]) == 0.0


def test_payback_period_interpolates_within_year():
    # -100 then +40/year: cumulative is -100,-60,-20,+20 -> crosses zero
    # partway through year 3 (index 2 -> 3).
    flows = [-100, 40, 40, 40]
    payback = payback_period(flows)
    assert 2.0 < payback < 3.0


def test_lcoe_positive_and_finite_for_normal_project():
    value = lcoe(capex=1e8, opex_by_year=[1e6] * 20, generation_mwh_by_year=[200_000] * 20, discount_rate=0.07)
    assert value > 0
    assert np.isfinite(value)


def test_lcoe_infinite_with_zero_generation():
    value = lcoe(capex=1e8, opex_by_year=[1e6] * 10, generation_mwh_by_year=[0] * 10, discount_rate=0.07)
    assert value == float("inf")


def test_lcoe_decreases_with_more_generation():
    low_gen = lcoe(1e8, [1e6] * 20, [100_000] * 20, 0.07)
    high_gen = lcoe(1e8, [1e6] * 20, [300_000] * 20, 0.07)
    assert high_gen < low_gen


def test_economic_engine_higher_price_improves_npv():
    assumptions = EconomicConfig(capex_total=2e8, opex_fixed_annual=2e6, opex_variable_per_mwh=1.0, discount_rate=0.07, project_lifetime_years=30)
    engine = EconomicEngine(assumptions)
    low_price = engine.evaluate(annual_generation_mwh=300_000, annual_price=20)
    high_price = engine.evaluate(annual_generation_mwh=300_000, annual_price=80)
    assert high_price.npv_value > low_price.npv_value
    assert high_price.lcoe_value == pytest.approx(low_price.lcoe_value)  # LCOE is price-independent


def test_economic_engine_degradation_reduces_late_year_generation():
    assumptions = EconomicConfig(capex_total=1e8, degradation_rate_annual=0.01, project_lifetime_years=20)
    engine = EconomicEngine(assumptions)
    result = engine.evaluate(annual_generation_mwh=100_000, annual_price=40)
    assert result.generation_by_year_mwh[-1] < result.generation_by_year_mwh[0]
