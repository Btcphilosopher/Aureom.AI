"""
SilicaFlux PV Spectral Optimisation Engine.

A machine-readable simulation, optimisation and digital-twin system for
photovoltaic UV/visible/NIR spectral response. See ``README.md`` for the
full pipeline description; this module re-exports the most commonly used
public entry points.
"""

from .constants import LAMBDA_MAX_NM, LAMBDA_MIN_NM, SPECTRAL_BANDS_NM, wavelength_grid_nm
from .degradation import DegradationParameters, evaluate_degradation, evaluate_uv_tradeoff
from .digital_twin import PVCellDigitalTwin
from .engine import SILICAFLUX, SilicaFluxResult, SimulationOutput, generate_simulation_output, optimise
from .materials import MATERIAL_LIBRARY, PVMaterial
from .optics import OpticalStack, default_optical_stack, optimise_front_surface
from .parameter_sweep import SweepConfiguration, parameter_sweep
from .pipeline import PipelineResult, run_pipeline
from .spectral_converter import SpectralConverter, uv_conversion_gain
from .spectrum import AtmosphericConditions, SolarSpectrum, extraterrestrial_spectrum, terrestrial_spectrum
from .tandem import DEFAULT_TANDEM, TandemMaterial, tandem_optimiser

__version__ = "0.1.0"

__all__ = [
    "LAMBDA_MIN_NM", "LAMBDA_MAX_NM", "SPECTRAL_BANDS_NM", "wavelength_grid_nm",
    "SolarSpectrum", "AtmosphericConditions", "extraterrestrial_spectrum", "terrestrial_spectrum",
    "PVMaterial", "MATERIAL_LIBRARY",
    "OpticalStack", "default_optical_stack", "optimise_front_surface",
    "SpectralConverter", "uv_conversion_gain",
    "TandemMaterial", "DEFAULT_TANDEM", "tandem_optimiser",
    "DegradationParameters", "evaluate_degradation", "evaluate_uv_tradeoff",
    "PipelineResult", "run_pipeline",
    "SweepConfiguration", "parameter_sweep",
    "PVCellDigitalTwin",
    "SILICAFLUX", "optimise", "SilicaFluxResult", "SimulationOutput", "generate_simulation_output",
    "__version__",
]
