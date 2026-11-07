"""Project settings and the labelled default-assumption library.

Defaults start with UK practice, GBP and metric units; every item is
configurable.  Default assumptions are *priors*, never facts: each is a
:class:`TrackedValue` with ``basis=ASSUMED`` and a source tag, so the UI can
label it and the simulator can sample it.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .provenance import Distribution, TrackedValue, assumed

ASSUMPTION_SOURCE = "aureom-uk-defaults-v1"


class ProjectSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    country: str = "GB"
    region: str = "England (fictional demo region)"
    site_location: str = "Plot 7, Fictional Lane, Exampleton (fictional)"
    currency: str = "GBP"
    #: Display units only. All internal calculations are SI metric.
    unit_system: Literal["metric", "imperial"] = "metric"
    pricing_date: date = Field(default_factory=lambda: date(2026, 11, 1))
    #: Regional multiplier applied to rates whose location differs (labelled assumption).
    regional_cost_factor: float = 1.0
    #: Annual escalation applied to rates dated before the pricing date (0 = none).
    annual_escalation_rate: float = 0.0
    #: Currency -> multiplier into ``currency`` for rates quoted in other currencies.
    fx_rates: dict[str, float] = Field(default_factory=dict)
    #: VAT is only added as a layer-9 line when this is True (enter the rate that applies).
    include_vat: bool = False
    vat_rate: float = 0.20
    #: Design temperatures for the simplified heat-loss calculation (deg C).
    internal_design_temp_c: float = 21.0
    external_design_temp_c: float = -2.0
    #: Heating degree-days (K.day/yr) for the indicative annual space-heat figure.
    heating_degree_days: float = 2000.0
    measurement_note: str = (
        "Areas follow GEA/GIA concepts (to external / internal face of external walls). "
        "Conceptual reconstruction - not a measured survey."
    )


class AssumptionLibrary(BaseModel):
    """Labelled default priors used when evidence is missing.

    All values are deliberately broad.  They are used to (a) convert pixels to
    metres when no calibration exists and (b) fill hidden geometry with
    explicitly assumed values.
    """

    model_config = ConfigDict(extra="forbid")

    floor_to_floor_m: TrackedValue = Field(default_factory=lambda: assumed(
        2.70, "m", low=2.50, high=3.00, source=ASSUMPTION_SOURCE,
        note="Typical UK dwelling floor-to-floor height."))
    ground_floor_level_m: TrackedValue = Field(default_factory=lambda: assumed(
        0.15, "m", low=0.10, high=0.25, source=ASSUMPTION_SOURCE,
        note="Finished floor above external ground (DPC zone)."))
    door_leaf_height_m: TrackedValue = Field(default_factory=lambda: assumed(
        2.10, "m", low=1.98, high=2.25, source=ASSUMPTION_SOURCE,
        note="External door set height incl. frame; used as a scale cue."))
    garage_door_height_m: TrackedValue = Field(default_factory=lambda: assumed(
        2.13, "m", low=1.98, high=2.40, source=ASSUMPTION_SOURCE,
        note="Domestic garage door height; scale cue."))
    window_head_to_floor_m: TrackedValue = Field(default_factory=lambda: assumed(
        2.10, "m", low=1.95, high=2.30, source=ASSUMPTION_SOURCE))
    roof_pitch_deg: TrackedValue = Field(default_factory=lambda: assumed(
        35.0, "deg", low=22.5, high=45.0, source=ASSUMPTION_SOURCE,
        note="Pitched-roof prior when pitch cannot be observed."))
    eaves_overhang_m: TrackedValue = Field(default_factory=lambda: assumed(
        0.30, "m", low=0.15, high=0.50, source=ASSUMPTION_SOURCE))
    verge_overhang_m: TrackedValue = Field(default_factory=lambda: assumed(
        0.15, "m", low=0.05, high=0.30, source=ASSUMPTION_SOURCE))
    depth_to_width_ratio: TrackedValue = Field(default_factory=lambda: assumed(
        0.85, "ratio", low=0.60, high=1.20, source=ASSUMPTION_SOURCE,
        note="Hidden footprint depth relative to visible frontage (detached house prior)."))
    rear_glazing_ratio: TrackedValue = Field(default_factory=lambda: assumed(
        0.20, "fraction", low=0.12, high=0.35, source=ASSUMPTION_SOURCE,
        note="Glazed fraction of hidden rear facade."))
    side_glazing_ratio: TrackedValue = Field(default_factory=lambda: assumed(
        0.04, "fraction", low=0.0, high=0.10, source=ASSUMPTION_SOURCE,
        note="Glazed fraction of hidden side facades."))
    partition_length_per_m2_gia: TrackedValue = Field(default_factory=lambda: assumed(
        0.45, "m/m2", low=0.35, high=0.60, source=ASSUMPTION_SOURCE,
        note="Internal partition length allowance per m2 GIA (no internal layout is observed)."))
    pixel_measurement_error_px: float = 3.0
    perspective_dimension_error: float = 0.03  # fractional, for near-fronto-parallel views


def default_assumptions() -> AssumptionLibrary:
    return AssumptionLibrary()


def default_settings(**overrides) -> ProjectSettings:
    return ProjectSettings(**overrides)


__all__ = [
    "ProjectSettings",
    "AssumptionLibrary",
    "default_assumptions",
    "default_settings",
    "ASSUMPTION_SOURCE",
    "Distribution",
    "Optional",
]
