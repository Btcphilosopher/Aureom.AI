"""
Input validation: catches malformed resource data or physically
inconsistent configuration before it reaches the hydraulic/economic models,
per the INPUT DATA -> VALIDATION stage of the pipeline.
"""

from __future__ import annotations

from hydroflux.core.config import HydroSystemConfig, ReservoirConfig, TurbineConfig
from hydroflux.core.timeseries import ResourceTimeSeries


class ValidationError(Exception):
    pass


def validate_resource_data(resource: ResourceTimeSeries, strict: bool = False) -> list[str]:
    """Check a :class:`ResourceTimeSeries` for common data problems.
    Returns a list of human-readable issues; raises :class:`ValidationError`
    if ``strict`` and any issues were found."""

    issues: list[str] = []

    if resource.n_steps == 0:
        issues.append("Resource data is empty (no timesteps).")

    if not resource.index.is_monotonic_increasing:
        issues.append("Time index is not monotonically increasing.")

    if resource.index.has_duplicates:
        issues.append("Time index contains duplicate timestamps.")

    for name in ("flow", "inflow"):
        series = getattr(resource, name)
        if series is not None:
            if series.isna().any():
                issues.append(f"'{name}' contains NaN values.")
            if (series.dropna() < 0).any():
                issues.append(f"'{name}' contains negative values (flow cannot be negative).")

    if resource.head is not None and (resource.head.dropna() < 0).any():
        issues.append("'head' contains negative values.")

    if resource.price is not None and resource.price.isna().any():
        issues.append("'price' contains NaN values.")

    if strict and issues:
        raise ValidationError("; ".join(issues))
    return issues


def validate_turbine_config(config: TurbineConfig) -> list[str]:
    issues: list[str] = []
    if config.rated_power_mw <= 0:
        issues.append(f"Turbine {config.id}: rated_power_mw must be positive.")
    if config.minimum_flow_m3s < 0:
        issues.append(f"Turbine {config.id}: minimum_flow_m3s cannot be negative.")
    if config.maximum_flow_m3s is not None and config.maximum_flow_m3s < config.minimum_flow_m3s:
        issues.append(f"Turbine {config.id}: maximum_flow_m3s is below minimum_flow_m3s.")
    if config.rated_flow_m3s <= 0:
        issues.append(f"Turbine {config.id}: rated_flow_m3s must be positive.")
    if not (0 < config.generator_efficiency <= 1):
        issues.append(f"Turbine {config.id}: generator_efficiency must be in (0, 1].")
    if not (0 <= config.availability <= 1):
        issues.append(f"Turbine {config.id}: availability must be in [0, 1].")
    return issues


def validate_reservoir_config(config: ReservoirConfig) -> list[str]:
    issues: list[str] = []
    if config.maximum_level_m <= config.minimum_level_m:
        issues.append(f"Reservoir {config.name}: maximum_level_m must exceed minimum_level_m.")
    if not (config.minimum_level_m <= config.initial_level_m <= config.maximum_level_m):
        issues.append(f"Reservoir {config.name}: initial_level_m must lie within [minimum_level_m, maximum_level_m].")
    if config.capacity_mcm <= config.dead_storage_mcm:
        issues.append(f"Reservoir {config.name}: capacity_mcm must exceed dead_storage_mcm.")
    if config.surface_area_km2 <= 0:
        issues.append(f"Reservoir {config.name}: surface_area_km2 must be positive.")
    return issues


def validate_system_config(config: HydroSystemConfig, strict: bool = False) -> list[str]:
    issues: list[str] = []
    for turbine in config.turbines:
        issues.extend(validate_turbine_config(turbine))
    if config.reservoir is not None:
        issues.extend(validate_reservoir_config(config.reservoir))
    if config.pumped_storage is not None:
        issues.extend(validate_reservoir_config(config.pumped_storage.upper_reservoir))
        issues.extend(validate_reservoir_config(config.pumped_storage.lower_reservoir))
    if config.economics.discount_rate < 0 or config.economics.discount_rate > 1:
        issues.append("economics.discount_rate should be a fraction in [0, 1].")
    if config.economics.project_lifetime_years <= 0:
        issues.append("economics.project_lifetime_years must be positive.")

    if strict and issues:
        raise ValidationError("; ".join(issues))
    return issues
