"""
Parameter sweep and ranked optimisation table (SilicaFlux spec item 23).

Automatically tests combinations of bandgap, layer thickness, anti-
reflection coating index, carrier lifetime, temperature and UV spectral-
conversion efficiency, running the full pipeline (``pipeline.run_pipeline``)
for every combination and ranking the results.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, replace

import numpy as np

from .degradation import annualise_power_w_m2
from .materials import PVMaterial
from .optics import default_optical_stack
from .pipeline import run_pipeline
from .spectral_converter import SpectralConverter, uv_conversion_gain
from .spectrum import SolarSpectrum


@dataclass(frozen=True)
class SweepConfiguration:
    bandgap_eV: float
    thickness_nm: float
    ar_index: float
    lifetime_multiplier: float
    temperature_k: float
    uv_conversion_efficiency: float  # 0 = no converter; combined quantum_yield*escape_efficiency otherwise


@dataclass
class SweepResult:
    rank: int
    configuration: SweepConfiguration
    uv_response: float          # UV power fraction
    total_efficiency: float
    degradation_rate_per_year: float
    annual_energy_w_h_m2: float
    net_energy_output_w_m2: float


def _default_values(base_material: PVMaterial) -> dict[str, list[float]]:
    return {
        "bandgap_eV": [round(base_material.bandgap_eV * f, 4) for f in (0.85, 1.0, 1.15)],
        "thickness_nm": [round(base_material.thickness_nm * f, 1) for f in (0.5, 1.0, 2.0)],
        "ar_index": [1.3, 1.6, 1.9],
        "lifetime_multiplier": [0.5, 1.0, 2.0],
        "temperature_k": [283.15, 298.15, 320.15],
        "uv_conversion_efficiency": [0.0, 0.7],
    }


def evaluate_configuration(
    base_material: PVMaterial,
    spectrum: SolarSpectrum,
    configuration: SweepConfiguration,
    texture_enabled: bool = True,
    encapsulant_uv_blocking: bool = False,
) -> SweepResult:
    material = replace(
        base_material,
        bandgap_eV=configuration.bandgap_eV,
        thickness_nm=configuration.thickness_nm,
        srh_lifetime_ns=base_material.srh_lifetime_ns * configuration.lifetime_multiplier,
    )
    stack = default_optical_stack(ar_index=configuration.ar_index, encapsulant_uv_blocking=encapsulant_uv_blocking)

    result = run_pipeline(
        spectrum, material, optical_stack=stack, ambient_temperature_k=configuration.temperature_k,
        texture_enabled=texture_enabled,
    )

    net_energy = result.net_energy_output_w_m2
    if configuration.uv_conversion_efficiency > 0.0:
        converter = SpectralConverter(
            quantum_yield=configuration.uv_conversion_efficiency, escape_efficiency=1.0, reabsorption=0.0
        )
        gain = uv_conversion_gain(
            converter, material, spectrum.wavelength_nm, result.photon_flux, result.optical_transmission,
            result.spectral_response.recombination_state, result.spectral_response.operating_point.v_mp_v,
        )
        net_energy = net_energy + gain.uv_conversion_gain_w_m2

    annual_energy = annualise_power_w_m2(net_energy)

    return SweepResult(
        rank=0,
        configuration=configuration,
        uv_response=result.spectral_response.uv_power_fraction,
        total_efficiency=result.efficiency,
        degradation_rate_per_year=result.degradation.degradation_rate_per_year if result.degradation else 0.0,
        annual_energy_w_h_m2=annual_energy,
        net_energy_output_w_m2=net_energy,
    )


def parameter_sweep(
    base_material: PVMaterial,
    spectrum: SolarSpectrum,
    bandgap_values: list[float] | None = None,
    thickness_values: list[float] | None = None,
    ar_index_values: list[float] | None = None,
    lifetime_multiplier_values: list[float] | None = None,
    temperature_values: list[float] | None = None,
    uv_conversion_efficiency_values: list[float] | None = None,
    max_configs: int = 5000,
    texture_enabled: bool = True,
    encapsulant_uv_blocking: bool = False,
) -> list[SweepResult]:
    """
    Deterministic grid sweep, ranked descending by ``net_energy_output_w_m2``.

    Default option lists are kept small per dimension (the full default
    grid is a few hundred configurations) so this runs in a few seconds;
    pass explicit value lists for a finer or coarser search. If the
    requested grid exceeds ``max_configs``, it is deterministically
    down-sampled (evenly spaced indices) rather than silently truncated.
    """
    defaults = _default_values(base_material)
    values = {
        "bandgap_eV": bandgap_values or defaults["bandgap_eV"],
        "thickness_nm": thickness_values or defaults["thickness_nm"],
        "ar_index": ar_index_values or defaults["ar_index"],
        "lifetime_multiplier": lifetime_multiplier_values or defaults["lifetime_multiplier"],
        "temperature_k": temperature_values or defaults["temperature_k"],
        "uv_conversion_efficiency": uv_conversion_efficiency_values or defaults["uv_conversion_efficiency"],
    }

    all_configs = [
        SweepConfiguration(*combo)
        for combo in itertools.product(
            values["bandgap_eV"], values["thickness_nm"], values["ar_index"],
            values["lifetime_multiplier"], values["temperature_k"], values["uv_conversion_efficiency"],
        )
    ]

    if len(all_configs) > max_configs:
        indices = np.linspace(0, len(all_configs) - 1, max_configs).round().astype(int)
        all_configs = [all_configs[i] for i in sorted(set(indices.tolist()))]

    results = [
        evaluate_configuration(base_material, spectrum, config, texture_enabled, encapsulant_uv_blocking)
        for config in all_configs
    ]
    results.sort(key=lambda r: r.net_energy_output_w_m2, reverse=True)
    for i, result in enumerate(results, start=1):
        result.rank = i

    return results
