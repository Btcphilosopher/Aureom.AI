"""
HydroFlux -- a research-grade Python engine for optimising hydroelectric and
tidal power generation.

The public surface is deliberately small: :func:`hydroflux.simulate`,
:func:`hydroflux.optimize` and :func:`hydroflux.compare`.  Everything else
lives in dedicated sub-packages (``hydraulics``, ``turbines``, ``reservoirs``,
``tidal``, ``pumped_storage``, ``grid``, ``environment``, ``economics``,
``optimisation``, ``scenarios``, ``forecasting``, ``calibration``, ``data``,
``validation``, ``reporting``) that can be used independently for research
and engineering analysis.
"""

from hydroflux._version import __version__
from hydroflux.api import compare, optimize, simulate
from hydroflux.core.config import (
    EconomicConfig,
    EnvironmentalConfig,
    HydroSystemConfig,
    PumpedStorageConfig,
    ReservoirConfig,
    SimulationConfig,
    TidalConfig,
    TurbineConfig,
)

__all__ = [
    "__version__",
    "simulate",
    "optimize",
    "compare",
    "HydroSystemConfig",
    "SimulationConfig",
    "TurbineConfig",
    "ReservoirConfig",
    "TidalConfig",
    "PumpedStorageConfig",
    "EconomicConfig",
    "EnvironmentalConfig",
]
