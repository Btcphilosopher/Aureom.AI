"""Pipe/process flow relations for a power-law fluid.

Provides the generalised (Metzner-Reed) Reynolds number and laminar
pressure-drop relation for a power-law fluid in a circular pipe --
standard chemical/food-process-engineering relations (see e.g. Chhabra &
Richardson, *Non-Newtonian Flow and Applied Rheology*), used by
:mod:`icecream_x.equipment.heat_exchanger` and
:mod:`icecream_x.equipment.freezer` to estimate pumping requirements and
residence-time-consistent flow.
"""

from __future__ import annotations

import math

from icecream_x.rheology.shear import PowerLawFluid


def metzner_reed_reynolds_number(
    fluid: PowerLawFluid, density_kg_m3: float, velocity_m_s: float, diameter_m: float
) -> float:
    """Generalised Reynolds number for power-law-fluid pipe flow."""
    n = fluid.flow_behaviour_index
    k = fluid.consistency_index_pa_sn
    numerator = density_kg_m3 * velocity_m_s ** (2.0 - n) * diameter_m**n
    denominator = k * ((3.0 * n + 1.0) / (4.0 * n)) ** n * 8.0 ** (n - 1.0)
    return numerator / denominator


def laminar_pressure_drop_pa(
    fluid: PowerLawFluid,
    velocity_m_s: float,
    diameter_m: float,
    length_m: float,
) -> float:
    """Laminar-flow pressure drop of a power-law fluid through a straight pipe."""
    n = fluid.flow_behaviour_index
    k = fluid.consistency_index_pa_sn
    shear_rate_wall = ((3.0 * n + 1.0) / (4.0 * n)) * (8.0 * velocity_m_s / diameter_m)
    wall_shear_stress = k * shear_rate_wall**n
    return 4.0 * wall_shear_stress * length_m / diameter_m


def volumetric_flow_rate_m3_s(mass_flow_kg_s: float, density_kg_m3: float) -> float:
    if density_kg_m3 <= 0:
        raise ValueError("density_kg_m3 must be > 0")
    return mass_flow_kg_s / density_kg_m3


def mean_velocity_m_s(volumetric_flow_m3_s: float, diameter_m: float) -> float:
    area = math.pi * (diameter_m / 2.0) ** 2
    if area <= 0:
        raise ValueError("diameter_m must be > 0")
    return volumetric_flow_m3_s / area


def residence_time_s(volume_m3: float, volumetric_flow_m3_s: float) -> float:
    if volumetric_flow_m3_s <= 0:
        raise ValueError("volumetric_flow_m3_s must be > 0")
    return volume_m3 / volumetric_flow_m3_s
