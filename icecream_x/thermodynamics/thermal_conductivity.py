"""Component and mixture thermal conductivity and density.

Uses the Choi & Okos (1986) polynomial correlations, as in
:mod:`icecream_x.thermodynamics.heat_capacity`. Thermal conductivity is
combined across components with the classic Krischer/Choi-Okos
*volume-fraction-weighted parallel* model, which requires each
component's density in order to convert mass fractions to volume
fractions.
"""

from __future__ import annotations

from dataclasses import dataclass

from icecream_x.formulation.composition import Composition


def k_water_liquid_w_m_k(temp_c: float) -> float:
    return 0.57109 + 1.7625e-3 * temp_c - 6.7036e-6 * temp_c**2


def k_ice_w_m_k(temp_c: float) -> float:
    return 2.2196 - 6.2489e-3 * temp_c + 1.0154e-4 * temp_c**2


def k_protein_w_m_k(temp_c: float) -> float:
    return 1.7881e-1 + 1.1958e-3 * temp_c - 2.7178e-6 * temp_c**2


def k_fat_w_m_k(temp_c: float) -> float:
    return 1.8071e-1 - 2.7604e-4 * temp_c - 1.7749e-7 * temp_c**2


def k_carbohydrate_w_m_k(temp_c: float) -> float:
    return 2.0141e-1 + 1.3874e-3 * temp_c - 4.3312e-6 * temp_c**2


def k_fibre_w_m_k(temp_c: float) -> float:
    return 1.8331e-1 + 1.2497e-3 * temp_c - 3.1683e-6 * temp_c**2


def k_ash_w_m_k(temp_c: float) -> float:
    return 3.2962e-1 + 1.4011e-3 * temp_c - 2.9069e-6 * temp_c**2


def rho_water_liquid_kg_m3(temp_c: float) -> float:
    return 997.18 + 3.1439e-3 * temp_c - 3.7574e-3 * temp_c**2


def rho_ice_kg_m3(temp_c: float) -> float:
    return 916.89 - 0.13071 * temp_c


def rho_protein_kg_m3(temp_c: float) -> float:
    return 1329.9 - 5.1840e-1 * temp_c


def rho_fat_kg_m3(temp_c: float) -> float:
    return 925.59 - 4.1757e-1 * temp_c


def rho_carbohydrate_kg_m3(temp_c: float) -> float:
    return 1599.1 - 3.1046e-1 * temp_c


def rho_fibre_kg_m3(temp_c: float) -> float:
    return 1311.5 - 3.6589e-1 * temp_c


def rho_ash_kg_m3(temp_c: float) -> float:
    return 2423.8 - 2.8063e-1 * temp_c


@dataclass(frozen=True, slots=True)
class _Component:
    mass_kg: float
    density_fn: callable
    conductivity_fn: callable


def _components(
    composition: Composition, unfrozen_water_kg: float, ice_kg: float
) -> list[_Component]:
    non_fibre_other = (
        composition.other_solids_kg + composition.stabiliser_kg + composition.emulsifier_kg
    )
    return [
        _Component(unfrozen_water_kg, rho_water_liquid_kg_m3, k_water_liquid_w_m_k),
        _Component(ice_kg, rho_ice_kg_m3, k_ice_w_m_k),
        _Component(composition.fat_kg, rho_fat_kg_m3, k_fat_w_m_k),
        _Component(composition.protein_kg, rho_protein_kg_m3, k_protein_w_m_k),
        _Component(
            composition.sugar_kg + composition.lactose_kg,
            rho_carbohydrate_kg_m3,
            k_carbohydrate_w_m_k,
        ),
        _Component(composition.mineral_kg, rho_ash_kg_m3, k_ash_w_m_k),
        _Component(non_fibre_other, rho_fibre_kg_m3, k_fibre_w_m_k),
    ]


def mixture_density_kg_m3(
    composition: Composition, temp_c: float, unfrozen_water_kg: float, ice_kg: float
) -> float:
    """Additive-volume mixture density (excludes any incorporated air)."""
    total_mass = composition.total_mass_kg
    if total_mass <= 0:
        return rho_water_liquid_kg_m3(temp_c)
    inverse_rho = 0.0
    for comp in _components(composition, unfrozen_water_kg, ice_kg):
        if comp.mass_kg <= 0:
            continue
        inverse_rho += comp.mass_kg / comp.density_fn(temp_c)
    if inverse_rho <= 0:
        return rho_water_liquid_kg_m3(temp_c)
    return total_mass / inverse_rho


def mixture_thermal_conductivity_w_m_k(
    composition: Composition, temp_c: float, unfrozen_water_kg: float, ice_kg: float
) -> float:
    """Volume-fraction-weighted (parallel/Krischer) mixture thermal conductivity."""
    comps = _components(composition, unfrozen_water_kg, ice_kg)
    volumes = [(c.mass_kg / c.density_fn(temp_c), c.conductivity_fn(temp_c)) for c in comps if c.mass_kg > 0]
    total_volume = sum(v for v, _ in volumes)
    if total_volume <= 0:
        return k_water_liquid_w_m_k(temp_c)
    return sum(v * k for v, k in volumes) / total_volume
