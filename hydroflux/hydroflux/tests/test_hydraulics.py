import numpy as np
import pytest

from hydroflux.hydraulics.hydraulics import (
    G,
    RHO_WATER,
    HeadModel,
    electrical_power,
    hydraulic_power,
    intake_loss,
    net_head,
    penstock_loss,
    theoretical_power,
)


def test_theoretical_power_matches_rho_g_q_h():
    q, h = 100.0, 50.0
    expected = RHO_WATER * G * q * h
    assert theoretical_power(q, h) == pytest.approx(expected)


def test_theoretical_power_zero_at_zero_flow_or_head():
    assert theoretical_power(0.0, 50.0) == 0.0
    assert theoretical_power(100.0, 0.0) == 0.0


def test_theoretical_power_never_negative_for_negative_head_input():
    # A negative head should not produce negative power -- physically the
    # turbine simply cannot operate, not generate "negative" power.
    assert theoretical_power(100.0, -5.0) == 0.0


def test_hydraulic_power_scales_with_efficiency():
    q, h = 100.0, 50.0
    full = hydraulic_power(q, h, efficiency=1.0)
    half = hydraulic_power(q, h, efficiency=0.5)
    assert half == pytest.approx(full / 2)


def test_electrical_power_is_never_greater_than_theoretical():
    q, h = 120.0, 40.0
    theoretical = theoretical_power(q, h)
    electrical = electrical_power(q, h, turbine_efficiency=0.9, generator_efficiency=0.98, transmission_efficiency=0.99)
    assert electrical < theoretical


def test_penstock_loss_increases_with_flow():
    low = penstock_loss(50.0, length_m=500, diameter_m=5.0)
    high = penstock_loss(150.0, length_m=500, diameter_m=5.0)
    assert high > low


def test_penstock_loss_increases_with_length():
    short = penstock_loss(100.0, length_m=200, diameter_m=5.0)
    long_ = penstock_loss(100.0, length_m=800, diameter_m=5.0)
    assert long_ > short


def test_intake_loss_positive_and_scales_with_flow_squared():
    low = intake_loss(50.0, area_m2=20.0)
    high = intake_loss(100.0, area_m2=20.0)
    assert high == pytest.approx(low * 4, rel=1e-6)  # quadratic in velocity


def test_net_head_never_negative():
    h = net_head(gross_head_m=10.0, penstock_losses_m=8.0, intake_losses_m=5.0, tailwater_effect_m=0.0)
    assert h == 0.0


def test_net_head_subtracts_all_losses():
    h = net_head(gross_head_m=100.0, penstock_losses_m=3.0, intake_losses_m=2.0, tailwater_effect_m=1.0)
    assert h == pytest.approx(94.0)


def test_head_model_net_head_decreases_with_flow():
    model = HeadModel(penstock_length_m=500, penstock_diameter_m=6.0, penstock_friction_factor=0.015)
    low_flow_head = model.net_head(50.0, reservoir_elevation_m=250.0, tailwater_elevation_m=150.0)
    high_flow_head = model.net_head(200.0, reservoir_elevation_m=250.0, tailwater_elevation_m=150.0)
    assert high_flow_head < low_flow_head
    assert high_flow_head < 100.0  # less than the raw gross head


def test_vectorised_operation_over_array():
    flows = np.array([10.0, 50.0, 100.0])
    powers = theoretical_power(flows, 40.0)
    assert powers.shape == flows.shape
    assert np.all(np.diff(powers) > 0)
