"""Adapter protocols for connecting detailed engineering tools later.

Housebuilder.OS Vision produces concept-stage, indicative simulations only.  It does
**not** establish structural adequacy, certified energy performance, regulatory
compliance or verified embodied carbon.  Those need detailed tools operated by
qualified people.  This module defines the seams where such tools can be connected:

* :class:`StructuralAnalysisAdapter` - e.g. an FEA package or an engineer's design
  software, returning checks *performed by that tool / engineer*;
* :class:`EnergyAnalysisAdapter` - e.g. SAP / SBEM / EnergyPlus / PHPP, returning the
  tool's own results (the built-in :func:`~housebuilder_vision.simulation.thermal.heat_loss`
  is a simplified steady-state estimate, not one of these);
* :class:`EmbodiedCarbonDataAdapter` - EPD / ICE-type datasets supplying carbon factors
  per material (the bundled factors are illustrative placeholders).

Each protocol has a ``NotConfigured...`` default whose ``is_available()`` is ``False`` and
whose run method raises :class:`AdapterNotConfigured` with guidance.  Nothing here makes
network calls or imports optional third-party packages; a real adapter must import its
dependencies lazily inside its own methods, validate every input and output (treat tool
output as untrusted data: parse into the Pydantic models below, clamp ranges, never
execute anything), and record its name / version.

Provenance: results from external tools are recorded with ``basis = INFERRED`` (model
output) unless a responsible person confirms them (``USER_CONFIRMED``, with
``responsible_party`` filled in).  Applying dataset factors with
:func:`apply_carbon_factors` returns a *new* library and never mutates the input.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from ..core.models import AssemblyLibrary, BuildingTwin, GeometryMetrics, MaterialSpec
from ..core.provenance import Basis
from ..core.settings import ProjectSettings

__all__ = [
    "AdapterNotConfigured",
    "EngineeringResult",
    "StructuralCheck",
    "StructuralAnalysisReport",
    "EnergyAnalysisReport",
    "CarbonFactor",
    "StructuralAnalysisAdapter",
    "EnergyAnalysisAdapter",
    "EmbodiedCarbonDataAdapter",
    "NotConfiguredStructuralAdapter",
    "NotConfiguredEnergyAdapter",
    "NotConfiguredCarbonDataAdapter",
    "StaticCarbonFactorAdapter",
    "EngineeringAdapters",
    "default_engineering_adapters",
    "apply_carbon_factors",
]


class AdapterNotConfigured(RuntimeError):
    """Raised by the default adapters: no detailed engineering tool is connected."""

    def __init__(self, capability: str, guidance: str):
        self.capability = capability
        self.guidance = guidance
        super().__init__(f"No {capability} adapter is configured. {guidance}")


# =============================================================================
# Result models (validated; external tool output is untrusted)
# =============================================================================
class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EngineeringResult(_M):
    adapter: str
    adapter_version: str = "0"
    tool: str = ""
    tool_version: str = ""
    status: str = "ok"
    #: INFERRED for tool output; USER_CONFIRMED only when a responsible person signs it off.
    basis: Basis = Basis.INFERRED
    responsible_party: str = ""
    notes: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


class StructuralCheck(_M):
    element: str
    check: str
    utilisation: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    passed: Optional[bool] = None
    note: str = ""


class StructuralAnalysisReport(EngineeringResult):
    checks: list[StructuralCheck] = Field(default_factory=list)
    design_codes: list[str] = Field(default_factory=list)


class EnergyAnalysisReport(EngineeringResult):
    method: str = ""
    heat_loss_coefficient_w_k: Optional[float] = Field(default=None, ge=0.0)
    annual_space_heat_kwh: Optional[float] = Field(default=None, ge=0.0)
    peak_heat_load_kw: Optional[float] = Field(default=None, ge=0.0)
    outputs: dict[str, float] = Field(default_factory=dict)


class CarbonFactor(_M):
    material_id: str
    kgco2e_per_kg: float = Field(ge=0.0, le=1000.0)
    stages: str = "A1-A3"
    source: str
    dataset_version: str = ""
    reference: str = ""  # e.g. EPD registration number
    basis: Basis = Basis.INFERRED


# =============================================================================
# Protocols
# =============================================================================
@runtime_checkable
class StructuralAnalysisAdapter(Protocol):
    """Connects a structural analysis / design tool (FEA, engineer's software).

    ``analyse`` receives the conceptual twin and its geometry; a real implementation must make
    clear that member sizes, loads and checks come from that tool and its operator.
    """

    name: str
    version: str
    capability: str

    def is_available(self) -> bool: ...

    def analyse(self, twin: BuildingTwin, metrics: GeometryMetrics, library: AssemblyLibrary, *,
                options: Optional[Mapping[str, Any]] = None) -> StructuralAnalysisReport: ...


@runtime_checkable
class EnergyAnalysisAdapter(Protocol):
    """Connects a detailed energy tool (SAP, SBEM, EnergyPlus, PHPP ...)."""

    name: str
    version: str
    capability: str

    def is_available(self) -> bool: ...

    def calculate(self, twin: BuildingTwin, metrics: GeometryMetrics, library: AssemblyLibrary,
                  settings: ProjectSettings, *, options: Optional[Mapping[str, Any]] = None) -> EnergyAnalysisReport: ...


@runtime_checkable
class EmbodiedCarbonDataAdapter(Protocol):
    """Supplies carbon factors from an EPD / ICE-type dataset (``None`` when no match)."""

    name: str
    version: str
    capability: str

    def is_available(self) -> bool: ...

    def factor_for(self, material: MaterialSpec) -> Optional[CarbonFactor]: ...


# =============================================================================
# Default (not configured) implementations
# =============================================================================
_STRUCT_GUIDANCE = (
    "Housebuilder.OS Vision does not assess structural adequacy, member sizes, foundations or stability. "
    "Implement StructuralAnalysisAdapter for a structural analysis / design tool operated by a qualified "
    "structural engineer and pass it explicitly; results must be reviewed by that engineer.")
_ENERGY_GUIDANCE = (
    "The built-in heat_loss() is a simplified steady-state estimate, not SAP/SBEM/PHPP, and supports no "
    "compliance claim. Implement EnergyAnalysisAdapter for an accredited energy tool (run by an accredited "
    "assessor where required) and pass it explicitly.")
_CARBON_GUIDANCE = (
    "Bundled carbon factors are illustrative placeholders. Implement EmbodiedCarbonDataAdapter for a licensed "
    "EPD / ICE-type dataset (e.g. load a local, validated export) or use StaticCarbonFactorAdapter with factors "
    "you have verified, then apply_carbon_factors(library, adapter).")


class NotConfiguredStructuralAdapter:
    name = "structural-not-configured"
    version = "0"
    capability = "structural_analysis"

    def is_available(self) -> bool:
        return False

    def analyse(self, twin: BuildingTwin, metrics: GeometryMetrics, library: AssemblyLibrary, *,
                options: Optional[Mapping[str, Any]] = None) -> StructuralAnalysisReport:
        raise AdapterNotConfigured(self.capability, _STRUCT_GUIDANCE)


class NotConfiguredEnergyAdapter:
    name = "energy-not-configured"
    version = "0"
    capability = "energy_analysis"

    def is_available(self) -> bool:
        return False

    def calculate(self, twin: BuildingTwin, metrics: GeometryMetrics, library: AssemblyLibrary,
                  settings: ProjectSettings, *, options: Optional[Mapping[str, Any]] = None) -> EnergyAnalysisReport:
        raise AdapterNotConfigured(self.capability, _ENERGY_GUIDANCE)


class NotConfiguredCarbonDataAdapter:
    name = "carbon-data-not-configured"
    version = "0"
    capability = "embodied_carbon_data"

    def is_available(self) -> bool:
        return False

    def factor_for(self, material: MaterialSpec) -> Optional[CarbonFactor]:
        raise AdapterNotConfigured(self.capability, _CARBON_GUIDANCE)


class StaticCarbonFactorAdapter:
    """In-memory factors supplied (and verified) by the user: ``{material_id: kgCO2e/kg}``.

    Values are validated (finite, 0..1000 kgCO2e/kg).  ``basis`` defaults to
    ``USER_CONFIRMED`` because the person supplies the numbers; set ``INFERRED`` when they come
    from an unreviewed dataset export.  No I/O.
    """

    capability = "embodied_carbon_data"

    def __init__(self, factors: Mapping[str, float], *, source: str, dataset_version: str = "",
                 basis: Basis = Basis.USER_CONFIRMED, name: str = "static-carbon-factors", version: str = "1"):
        if not source or not source.strip():
            raise ValueError("a source description is required for carbon factors")
        clean: dict[str, float] = {}
        for mid, v in factors.items():
            f = float(v)
            if not math.isfinite(f) or f < 0 or f > 1000:
                raise ValueError(f"carbon factor for '{mid}' must be within [0, 1000] kgCO2e/kg (got {v!r})")
            clean[str(mid)] = f
        self._factors = clean
        self.source = source.strip()
        self.dataset_version = dataset_version
        self.basis = basis
        self.name = name
        self.version = version

    def is_available(self) -> bool:
        return True

    def factor_for(self, material: MaterialSpec) -> Optional[CarbonFactor]:
        f = self._factors.get(material.material_id)
        if f is None:
            return None
        return CarbonFactor(material_id=material.material_id, kgco2e_per_kg=f, source=self.source,
                            dataset_version=self.dataset_version, basis=self.basis)


class EngineeringAdapters(_M):
    """The set of engineering adapters a pipeline uses (defaults: not configured)."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    structural: Any = Field(default_factory=NotConfiguredStructuralAdapter)
    energy: Any = Field(default_factory=NotConfiguredEnergyAdapter)
    carbon_data: Any = Field(default_factory=NotConfiguredCarbonDataAdapter)

    def status(self) -> dict[str, bool]:
        return {"structural": bool(self.structural.is_available()), "energy": bool(self.energy.is_available()),
                "carbon_data": bool(self.carbon_data.is_available())}


def default_engineering_adapters() -> EngineeringAdapters:
    return EngineeringAdapters()


def apply_carbon_factors(library: AssemblyLibrary, adapter: EmbodiedCarbonDataAdapter
                         ) -> tuple[AssemblyLibrary, dict[str, list[str]]]:
    """Return a copy of ``library`` with carbon factors from ``adapter`` and a report.

    Matched materials get ``carbon_kgco2e_per_kg`` and ``carbon_source`` ("<source> <version>
    [<stages>] (<basis>)"); unmatched materials keep their existing (placeholder) values and are
    listed under ``"unmatched"``.  Raises :class:`AdapterNotConfigured` for a default adapter.
    """
    if not adapter.is_available():
        raise AdapterNotConfigured(getattr(adapter, "capability", "embodied_carbon_data"), _CARBON_GUIDANCE)
    new_mats: list[MaterialSpec] = []
    report: dict[str, list[str]] = {"matched": [], "unmatched": []}
    for m in library.materials:
        cf = adapter.factor_for(m)
        if cf is None:
            new_mats.append(m)
            report["unmatched"].append(m.material_id)
            continue
        cf = CarbonFactor.model_validate(cf.model_dump() if isinstance(cf, BaseModel) else cf)
        if cf.material_id != m.material_id:
            raise ValueError(f"adapter returned a factor for '{cf.material_id}' when asked for '{m.material_id}'")
        src = f"{cf.source} {cf.dataset_version}".strip() + f" [{cf.stages}] ({cf.basis.value})"
        new_mats.append(m.model_copy(update={"carbon_kgco2e_per_kg": cf.kgco2e_per_kg, "carbon_source": src}))
        report["matched"].append(m.material_id)
    return library.model_copy(update={"materials": new_mats}, deep=True), report
