"""
Abstract thermal model (section 32). THIS IS A MODEL, NOT MEASURED
SILICON BEHAVIOUR -- there is no fabricated chip, no package, and no
cooling solution to actually measure. Every function here takes its
inputs (power, package theta_ja, ambient temperature) as explicit
caller-supplied assumptions and applies a standard, textbook steady-
state junction-temperature formula; it never invents a power or
thermal-resistance figure on its own.

    T_junction = T_ambient + P * theta_ja

theta_ja (junction-to-ambient thermal resistance, degC/W) is a package/
cooling-solution property; typical illustrative ranges for reference
(NOT this design's actual package, which does not exist):
  still air, small QFN-style package : ~30-50 degC/W
  moderate heatsink + airflow          : ~5-15 degC/W
  aggressive heatsink + high airflow    : ~1-3 degC/W
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThermalResult:
    power_watts: float
    theta_ja_c_per_w: float
    ambient_c: float
    junction_c: float
    max_rated_junction_c: float
    headroom_c: float
    within_budget: bool


def estimate(power_watts: float, theta_ja_c_per_w: float, ambient_c: float = 25.0,
             max_rated_junction_c: float = 105.0) -> ThermalResult:
    if power_watts < 0:
        raise ValueError("power_watts must be >= 0")
    if theta_ja_c_per_w <= 0:
        raise ValueError("theta_ja_c_per_w must be > 0")

    junction_c = ambient_c + power_watts * theta_ja_c_per_w
    headroom_c = max_rated_junction_c - junction_c
    return ThermalResult(
        power_watts=power_watts, theta_ja_c_per_w=theta_ja_c_per_w, ambient_c=ambient_c,
        junction_c=junction_c, max_rated_junction_c=max_rated_junction_c,
        headroom_c=headroom_c, within_budget=(headroom_c >= 0),
    )


def cooling_sweep(power_watts: float, theta_ja_options: dict[str, float],
                   ambient_c: float = 25.0, max_rated_junction_c: float = 105.0) -> list[ThermalResult]:
    """Evaluate the same power figure under several named cooling assumptions."""
    return [estimate(power_watts, theta, ambient_c, max_rated_junction_c)
            for theta in theta_ja_options.values()]
