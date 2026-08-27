"""Shear-rate-dependent (power-law / pseudoplastic) flow behaviour.

Unfrozen ice cream mix, and especially partially-frozen product inside a
scraped-surface freezer barrel, is pseudoplastic (shear-thinning): its
apparent viscosity drops as shear rate increases. This is modelled with
the standard power-law (Ostwald-de Waele) fluid model:

    tau = K * gamma_dot ** n
    eta_apparent(gamma_dot) = K * gamma_dot ** (n - 1)

``K`` (consistency index, Pa s^n) is taken from
:mod:`icecream_x.rheology.viscosity`'s Newtonian-reference estimate,
evaluated at a representative reference shear rate so that the power-law
curve passes through that estimate. ``n`` (flow behaviour index, n=1 is
Newtonian, n<1 is shear-thinning) is modelled as an empirical function of
total solids content -- more concentrated mixes are more shear-thinning
-- clamped to a plausible range for ice cream mixes (typically 0.6-1.0 in
the literature).
"""

from __future__ import annotations

from dataclasses import dataclass

#: Reference shear rate (1/s) at which the Newtonian-reference viscosity
#: estimate from :mod:`icecream_x.rheology.viscosity` is assumed to apply.
#: Representative of a low-shear viscometer measurement.
REFERENCE_SHEAR_RATE_1_PER_S = 10.0

FLOW_BEHAVIOUR_INDEX_MIN = 0.55
FLOW_BEHAVIOUR_INDEX_MAX = 1.0


@dataclass(frozen=True, slots=True)
class PowerLawFluid:
    consistency_index_pa_sn: float
    flow_behaviour_index: float

    def apparent_viscosity_pa_s(self, shear_rate_1_per_s: float) -> float:
        if shear_rate_1_per_s <= 0:
            raise ValueError("shear_rate_1_per_s must be > 0")
        return self.consistency_index_pa_sn * shear_rate_1_per_s ** (
            self.flow_behaviour_index - 1.0
        )

    def shear_stress_pa(self, shear_rate_1_per_s: float) -> float:
        return self.consistency_index_pa_sn * shear_rate_1_per_s**self.flow_behaviour_index


def flow_behaviour_index(total_solids_mass_fraction: float) -> float:
    """Empirical n(total solids): more concentrated mixes shear-thin more."""
    n = 1.0 - 0.9 * total_solids_mass_fraction
    return min(max(n, FLOW_BEHAVIOUR_INDEX_MIN), FLOW_BEHAVIOUR_INDEX_MAX)


def fit_power_law(
    newtonian_reference_viscosity_pa_s: float,
    total_solids_mass_fraction: float,
    reference_shear_rate_1_per_s: float = REFERENCE_SHEAR_RATE_1_PER_S,
) -> PowerLawFluid:
    """Fit a power-law fluid so it reproduces a known viscosity at a reference shear rate."""
    n = flow_behaviour_index(total_solids_mass_fraction)
    k = newtonian_reference_viscosity_pa_s * reference_shear_rate_1_per_s ** (1.0 - n)
    return PowerLawFluid(consistency_index_pa_sn=k, flow_behaviour_index=n)
