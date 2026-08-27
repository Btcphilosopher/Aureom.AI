"""Example process-condition profiles.

Complements :mod:`icecream_x.scenarios.recipes`: these are illustrative
:class:`~icecream_x.core.engine.ProcessProfile` presets covering
different overrun targets and freezing regimes, not the only valid
settings -- any field can be overridden via ``dataclasses.replace``.
"""

from __future__ import annotations

import dataclasses

from icecream_x.core.engine import ProcessProfile
from icecream_x.equipment.freezer import ScrapedSurfaceFreezer
from icecream_x.equipment.homogeniser import Homogeniser
from icecream_x.equipment.pasteuriser import LTLT_DEFAULT

STANDARD = ProcessProfile()

HIGH_OVERRUN = dataclasses.replace(STANDARD, overrun_pct=120.0)

LOW_OVERRUN = dataclasses.replace(STANDARD, overrun_pct=25.0)

#: Artisan/gelato-style: slower freezer residence (lower throughput barrel),
#: lower homogenisation pressure, batch (LTLT) pasteurisation, low overrun.
ARTISAN_SLOW_FREEZE = dataclasses.replace(
    STANDARD,
    pasteuriser=LTLT_DEFAULT,
    homogeniser=Homogeniser.from_bar("Artisan single-stage", first_stage_bar=100.0),
    freezer=ScrapedSurfaceFreezer(
        name="Batch Freezer (slow)",
        barrel_diameter_m=0.15,
        barrel_length_m=1.2,
        scraper_speed_rpm=120.0,
        refrigerant_temperature_c=-25.0,
        motor_power_kw=11.0,
        design_throughput_kg_s=0.15,
    ),
    overrun_pct=25.0,
    freezer_outlet_temperature_c=-6.0,
)

#: High-throughput industrial line: faster barrel throughput, higher overrun.
INDUSTRIAL_FAST_FREEZE = dataclasses.replace(
    STANDARD,
    freezer=ScrapedSurfaceFreezer(
        name="Industrial Freezer (fast)",
        barrel_diameter_m=0.2,
        barrel_length_m=1.8,
        scraper_speed_rpm=350.0,
        refrigerant_temperature_c=-35.0,
        motor_power_kw=37.0,
        design_throughput_kg_s=1.2,
    ),
    overrun_pct=100.0,
)

PROCESSING_PROFILE_LIBRARY: dict[str, ProcessProfile] = {
    "standard": STANDARD,
    "high_overrun": HIGH_OVERRUN,
    "low_overrun": LOW_OVERRUN,
    "artisan_slow_freeze": ARTISAN_SLOW_FREEZE,
    "industrial_fast_freeze": INDUSTRIAL_FAST_FREEZE,
}
