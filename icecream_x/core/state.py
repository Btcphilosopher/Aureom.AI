"""The central product state.

:class:`ProductState` is the single object threaded through the entire
simulation chain (mixing -> ... -> serving). It is an immutable
snapshot: every processing step in :mod:`icecream_x.processing` takes a
``ProductState`` in and returns a *new* ``ProductState`` out (functional
style), which is what lets :mod:`icecream_x.core.simulation` log a full
time series of states without aliasing bugs, and what lets the digital
twin (:mod:`icecream_x.digital_twin.twin`) hold ``physical_state``,
``estimated_state`` and ``predicted_state`` side by side safely.

Mass balance is anchored in :attr:`composition` (see
:mod:`icecream_x.formulation.composition`); every process step is
expected to preserve ``composition.total_mass_kg`` (checked with
:func:`icecream_x.utils.validation.check_mass_balance`) except where a
declared mass loss occurs (e.g. evaporative losses during pasteurisation,
scale-up trims), which must be passed explicitly and logged.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum

from icecream_x.formulation.composition import Composition
from icecream_x.microstructure.structure import MicrostructureState
from icecream_x.rheology.viscosity import RheologyState, mixture_viscosity
from icecream_x.thermodynamics.phase_equilibrium import ThermalState, evaluate as evaluate_thermal
from icecream_x.utils.units import celsius_to_kelvin

#: Approximate density of air at typical process temperatures, kg/m3. Used
#: only for small second-order corrections to overall product density.
AIR_DENSITY_KG_M3 = 1.2


class ProcessStage(str, Enum):
    RAW = "raw"
    MIXED = "mixed"
    PASTEURISED = "pasteurised"
    HOMOGENISED = "homogenised"
    AGED = "aged"
    FROZEN = "frozen"
    AERATED = "aerated"
    HARDENED = "hardened"
    STORED = "stored"
    DISTRIBUTED = "distributed"
    SERVED = "served"


@dataclass(frozen=True, slots=True)
class ProductState:
    composition: Composition
    temperature_k: float
    stage: ProcessStage = ProcessStage.RAW
    microstructure: MicrostructureState = field(default_factory=MicrostructureState.initial)
    air_volume_fraction: float = 0.0
    cumulative_shear_exposure: float = 0.0
    elapsed_time_s: float = 0.0
    cumulative_energy_j: float = 0.0

    @classmethod
    def from_composition(
        cls, composition: Composition, temperature_c: float, stage: ProcessStage = ProcessStage.MIXED
    ) -> "ProductState":
        return cls(composition=composition, temperature_k=celsius_to_kelvin(temperature_c))

    @property
    def temperature_c(self) -> float:
        return self.temperature_k - 273.15

    def thermal_state(self) -> ThermalState:
        return evaluate_thermal(self.composition, self.temperature_k)

    def rheology_state(self) -> RheologyState:
        thermal = self.thermal_state()
        fractions = self.composition.as_fractions()
        return mixture_viscosity(
            thermal.phase,
            sugar_mass_fraction_of_serum=fractions["sugar"] + fractions["lactose"],
            stabiliser_mass_fraction=fractions["stabiliser"],
        )

    @property
    def overrun_pct(self) -> float:
        """Overrun: % volume increase from incorporated air."""
        if self.air_volume_fraction >= 1.0:
            raise ValueError("air_volume_fraction must be < 1")
        return 100.0 * self.air_volume_fraction / (1.0 - self.air_volume_fraction)

    def product_density_kg_m3(self) -> float:
        mix_density = self.thermal_state().density_kg_m3
        return mix_density * (1.0 - self.air_volume_fraction) + AIR_DENSITY_KG_M3 * self.air_volume_fraction

    def evolve(
        self,
        *,
        composition: Composition | None = None,
        temperature_k: float | None = None,
        stage: ProcessStage | None = None,
        microstructure: MicrostructureState | None = None,
        air_volume_fraction: float | None = None,
        cumulative_shear_exposure: float | None = None,
        elapsed_time_s: float | None = None,
        cumulative_energy_j: float | None = None,
    ) -> "ProductState":
        """Return a new ``ProductState`` with the given fields updated.

        The canonical way processing steps advance the simulation: never
        mutate a ``ProductState`` in place.
        """
        return replace(
            self,
            composition=composition if composition is not None else self.composition,
            temperature_k=temperature_k if temperature_k is not None else self.temperature_k,
            stage=stage if stage is not None else self.stage,
            microstructure=microstructure if microstructure is not None else self.microstructure,
            air_volume_fraction=(
                air_volume_fraction if air_volume_fraction is not None else self.air_volume_fraction
            ),
            cumulative_shear_exposure=(
                cumulative_shear_exposure
                if cumulative_shear_exposure is not None
                else self.cumulative_shear_exposure
            ),
            elapsed_time_s=elapsed_time_s if elapsed_time_s is not None else self.elapsed_time_s,
            cumulative_energy_j=(
                cumulative_energy_j if cumulative_energy_j is not None else self.cumulative_energy_j
            ),
        )

    def summary(self) -> dict[str, float | str]:
        thermal = self.thermal_state()
        out: dict[str, float | str] = {
            "stage": self.stage.value,
            "temperature_c": round(self.temperature_c, 2),
            "ice_fraction_pct": round(100 * thermal.phase.ice_mass_fraction, 2),
            "overrun_pct": round(self.overrun_pct, 1) if self.air_volume_fraction > 0 else 0.0,
            "elapsed_time_s": round(self.elapsed_time_s, 1),
            "cumulative_energy_kwh": round(self.cumulative_energy_j / 3_600_000.0, 4),
        }
        out.update({f"microstructure.{k}": v for k, v in self.microstructure.summary().items() if v is not None})
        return out
