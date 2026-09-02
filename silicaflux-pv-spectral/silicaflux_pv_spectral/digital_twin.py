"""
Digital cell twin (SilicaFlux spec item 22).

A mutable, stateful wrapper around ``pipeline.run_pipeline``: change a
material, optical-stack or environmental parameter and the spectral
response, degradation and efficiency are recomputed on next access (lazy,
so a burst of ``set_parameter`` calls only triggers one recompute).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

from .constants import STC_TEMPERATURE_K
from .materials import PVMaterial
from .optics import OpticalStack, ar_coating_layer, default_optical_stack, encapsulant_layer
from .pipeline import PipelineResult, run_pipeline
from .spectrum import SolarSpectrum

_MATERIAL_FIELD_NAMES = {f.name for f in dataclasses.fields(PVMaterial)}
_TWIN_ENVIRONMENT_FIELDS = {"ambient_temperature_k", "wind_speed_m_s", "texture_enabled"}
_AR_FIELDS = {"ar_index", "ar_thickness_nm"}


def _replace_ar_layer(stack: OpticalStack, ar_index: float | None = None, ar_thickness_nm: float | None = None) -> OpticalStack:
    """Rebuild layer 0 (the AR coating, by ``default_optical_stack``'s construction order) with new parameters."""
    if not stack.layers:
        raise ValueError("optical stack has no AR coating layer to modify")
    current = stack.layers[0]
    # Recover the current AR index by sampling n_func once (constant across wavelength for our AR layers).
    import numpy as np

    current_index = float(current.n_func(np.array([550.0]))[0])
    new_layer = ar_coating_layer(
        refractive_index_val=ar_index if ar_index is not None else current_index,
        thickness_nm=ar_thickness_nm if ar_thickness_nm is not None else current.thickness_nm,
        name=current.name,
    )
    return OpticalStack(layers=[new_layer, *stack.layers[1:]], incident_index=stack.incident_index)


def _replace_encapsulant_layer(stack: OpticalStack, uv_blocking: bool) -> OpticalStack:
    """Rebuild layer 1 (the encapsulant, by ``default_optical_stack``'s construction order)."""
    if len(stack.layers) < 2:
        raise ValueError("optical stack has no encapsulant layer to modify")
    current = stack.layers[1]
    new_layer = encapsulant_layer(uv_blocking=uv_blocking, thickness_nm=current.thickness_nm)
    return OpticalStack(layers=[stack.layers[0], new_layer, *stack.layers[2:]], incident_index=stack.incident_index)


@dataclass
class PVCellDigitalTwin:
    material: PVMaterial
    spectrum: SolarSpectrum
    optical_stack: OpticalStack = field(default_factory=default_optical_stack)
    ambient_temperature_k: float = STC_TEMPERATURE_K
    wind_speed_m_s: float = 1.0
    texture_enabled: bool = True

    _result: PipelineResult | None = field(default=None, init=False, repr=False)
    _dirty: bool = field(default=True, init=False, repr=False)

    def recompute(self) -> PipelineResult:
        self._result = run_pipeline(
            self.spectrum, self.material, optical_stack=self.optical_stack,
            ambient_temperature_k=self.ambient_temperature_k, wind_speed_m_s=self.wind_speed_m_s,
            texture_enabled=self.texture_enabled,
        )
        self._dirty = False
        return self._result

    @property
    def result(self) -> PipelineResult:
        if self._dirty or self._result is None:
            self.recompute()
        return self._result

    def set_parameter(self, name: str, value) -> None:
        """
        Change any material property (``bandgap_eV``, ``thickness_nm``,
        ``surface_recomb_velocity_cm_s``, ...), AR-coating property
        (``ar_index``, ``ar_thickness_nm``), encapsulant choice
        (``encapsulant_uv_blocking``), or environment property
        (``ambient_temperature_k``, ``wind_speed_m_s``, ``texture_enabled``).
        Marks the twin dirty; the next access to ``.result`` (or any of the
        summary properties below) triggers exactly one recompute.
        """
        if name in _MATERIAL_FIELD_NAMES:
            self.material = dataclasses.replace(self.material, **{name: value})
        elif name in _AR_FIELDS:
            self.optical_stack = _replace_ar_layer(self.optical_stack, **{name: value})
        elif name == "encapsulant_uv_blocking":
            self.optical_stack = _replace_encapsulant_layer(self.optical_stack, uv_blocking=bool(value))
        elif name in _TWIN_ENVIRONMENT_FIELDS:
            setattr(self, name, value)
        else:
            raise KeyError(
                f"Unknown digital-twin parameter {name!r}; expected a PVMaterial field, "
                f"one of {_AR_FIELDS | {'encapsulant_uv_blocking'}}, or one of {_TWIN_ENVIRONMENT_FIELDS}"
            )
        self._dirty = True

    # --- convenience read accessors, matching item 22's requested fields ---
    @property
    def bandgap_eV(self) -> float:
        return self.material.bandgap_eV

    @property
    def thickness_nm(self) -> float:
        return self.material.thickness_nm

    @property
    def layer_structure(self) -> list[dict]:
        return [{"name": layer.name, "thickness_nm": layer.thickness_nm} for layer in self.optical_stack.layers] + [
            {"name": self.material.material_name, "thickness_nm": self.material.thickness_nm}
        ]

    @property
    def spectral_response(self):
        return self.result.spectral_response

    @property
    def degradation(self):
        return self.result.degradation

    @property
    def efficiency(self) -> float:
        return self.result.efficiency

    @property
    def cell_temperature_k(self) -> float:
        return self.result.thermal_state.cell_temperature_k

    def summary(self) -> dict:
        result = self.result
        return {
            "material": self.material.material_name,
            "bandgap_eV": self.bandgap_eV,
            "layer_structure": self.layer_structure,
            "thickness_nm": self.thickness_nm,
            "temperature_k": self.cell_temperature_k,
            "efficiency": result.efficiency,
            "uv_power_fraction": result.spectral_response.uv_power_fraction,
            "degradation_rate_per_year": result.degradation.degradation_rate_per_year if result.degradation else None,
            "net_energy_output_w_m2": result.net_energy_output_w_m2,
        }
