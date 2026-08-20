import numpy as np
import pandas as pd
import pytest

from hydroflux.core.config import HydroSystemConfig, ReservoirConfig, TurbineConfig
from hydroflux.core.timeseries import ResourceTimeSeries, make_time_index
from hydroflux.validation.validation import (
    ValidationError,
    validate_reservoir_config,
    validate_resource_data,
    validate_system_config,
    validate_turbine_config,
)


def test_valid_resource_data_has_no_issues():
    idx = make_time_index("2025-01-01", periods=100, freq="1h")
    flow = pd.Series(np.linspace(50, 100, 100), index=idx)
    resource = ResourceTimeSeries(index=idx, flow=flow)
    assert validate_resource_data(resource) == []


def test_negative_flow_is_flagged():
    idx = make_time_index("2025-01-01", periods=10, freq="1h")
    flow = pd.Series([-5.0] * 10, index=idx)
    resource = ResourceTimeSeries(index=idx, flow=flow)
    issues = validate_resource_data(resource)
    assert any("negative" in issue for issue in issues)


def test_nan_flow_is_flagged():
    idx = make_time_index("2025-01-01", periods=10, freq="1h")
    flow = pd.Series([10.0] * 9 + [np.nan], index=idx)
    resource = ResourceTimeSeries(index=idx, flow=flow)
    issues = validate_resource_data(resource)
    assert any("NaN" in issue for issue in issues)


def test_strict_mode_raises():
    idx = make_time_index("2025-01-01", periods=10, freq="1h")
    flow = pd.Series([-1.0] * 10, index=idx)
    resource = ResourceTimeSeries(index=idx, flow=flow)
    with pytest.raises(ValidationError):
        validate_resource_data(resource, strict=True)


def test_turbine_config_flags_inverted_flow_bounds():
    config = TurbineConfig(id="T1", rated_power_mw=100, rated_flow_m3s=100, minimum_flow_m3s=50, maximum_flow_m3s=20)
    issues = validate_turbine_config(config)
    assert any("maximum_flow_m3s" in issue for issue in issues)


def test_turbine_config_flags_nonpositive_power():
    config = TurbineConfig(id="T1", rated_power_mw=-10, rated_flow_m3s=100, minimum_flow_m3s=10)
    issues = validate_turbine_config(config)
    assert any("rated_power_mw" in issue for issue in issues)


def test_reservoir_config_flags_inverted_levels():
    config = ReservoirConfig(minimum_level_m=250, maximum_level_m=200, initial_level_m=225)
    issues = validate_reservoir_config(config)
    assert any("maximum_level_m" in issue for issue in issues)


def test_reservoir_config_flags_initial_level_out_of_range():
    config = ReservoirConfig(minimum_level_m=200, maximum_level_m=260, initial_level_m=300)
    issues = validate_reservoir_config(config)
    assert any("initial_level_m" in issue for issue in issues)


def test_system_config_valid_case_has_no_issues():
    config = HydroSystemConfig(
        name="valid-system",
        system_type="reservoir",
        turbines=[TurbineConfig(id="T1", rated_power_mw=100, rated_flow_m3s=100, minimum_flow_m3s=10)],
        reservoir=ReservoirConfig(minimum_level_m=200, maximum_level_m=260, initial_level_m=230),
    )
    assert validate_system_config(config) == []
