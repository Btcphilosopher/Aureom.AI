"""Continuous (scraped-surface) freezer equipment definition.

This is the barrel freezer that performs simultaneous freezing and air
incorporation -- the central unit operation of the process. See
:mod:`icecream_x.processing.freezing` for the transient simulation that
uses this equipment definition, and
:mod:`icecream_x.storage.freezer` for the *separate* concept of a
cold-storage freezer/cabinet.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from icecream_x.utils.validation import require_positive

#: Reference scraper speed used to non-dimensionalise the empirical
#: scraped-surface heat-transfer-coefficient correlation below.
REFERENCE_SCRAPER_SPEED_RPM = 200.0
REFERENCE_HEAT_TRANSFER_COEFFICIENT_W_M2_K = 1500.0


@dataclass(frozen=True, slots=True)
class ScrapedSurfaceFreezer:
    name: str
    barrel_diameter_m: float
    barrel_length_m: float
    scraper_speed_rpm: float
    refrigerant_temperature_c: float
    motor_power_kw: float
    design_throughput_kg_s: float

    def __post_init__(self) -> None:
        require_positive(self.barrel_diameter_m, "barrel_diameter_m")
        require_positive(self.barrel_length_m, "barrel_length_m")
        require_positive(self.scraper_speed_rpm, "scraper_speed_rpm")
        require_positive(self.motor_power_kw, "motor_power_kw")
        require_positive(self.design_throughput_kg_s, "design_throughput_kg_s")

    @property
    def barrel_volume_m3(self) -> float:
        radius = self.barrel_diameter_m / 2.0
        return math.pi * radius**2 * self.barrel_length_m

    @property
    def heat_transfer_area_m2(self) -> float:
        return math.pi * self.barrel_diameter_m * self.barrel_length_m

    def heat_transfer_coefficient_w_m2_k(self) -> float:
        """Scraped-surface wall heat-transfer coefficient.

        Empirical power-law scaling with scraper speed (higher agitation
        -> thinner boundary layer -> higher h), anchored to a reference
        (speed, h) pair. This is a simplified stand-in for a full
        scraped-surface-heat-exchanger correlation (e.g. a
        Skelland-type Nusselt correlation using blade count, product
        rheology, and rotational Reynolds number); the exponent and
        reference value are tunable defaults, not a fitted result for any
        specific machine.
        """
        ratio = self.scraper_speed_rpm / REFERENCE_SCRAPER_SPEED_RPM
        return REFERENCE_HEAT_TRANSFER_COEFFICIENT_W_M2_K * ratio**0.5

    def residence_time_s(self, mass_flow_kg_s: float, mix_density_kg_m3: float) -> float:
        require_positive(mass_flow_kg_s, "mass_flow_kg_s")
        require_positive(mix_density_kg_m3, "mix_density_kg_m3")
        volumetric_flow = mass_flow_kg_s / mix_density_kg_m3
        return self.barrel_volume_m3 / volumetric_flow


CONTINUOUS_FREEZER_DEFAULT = ScrapedSurfaceFreezer(
    name="Continuous SSHE Freezer",
    barrel_diameter_m=0.15,
    barrel_length_m=1.2,
    scraper_speed_rpm=250.0,
    refrigerant_temperature_c=-30.0,
    motor_power_kw=22.0,
    design_throughput_kg_s=0.5,
)
