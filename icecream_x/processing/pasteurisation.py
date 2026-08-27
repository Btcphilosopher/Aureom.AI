"""Pasteurisation: heating ramp, hold, cooling ramp.

Modelled as a *prescribed* thermal trajectory (the equipment's
heating/cooling rates are treated as controlled process specifications,
as they are on a real HTST/LTLT pasteuriser -- the PLC modulates flow and
duty to track a rate, rather than the product simply responding
passively to a fixed heat-transfer coefficient). The three phases are
tracked explicitly and separately, as required:

    TARGET TEMPERATURE, TIME AT TEMPERATURE, COOLING PROFILE

Energy input/removal for the ramp phases is computed as the specific
enthalpy difference between phase endpoints (enthalpy is a state
function, so this is exact regardless of the exact heat-rate profile used
to achieve the ramp). The hold phase additionally accounts for a small
parasitic heat loss to ambient through the holding-tube/vat wall, using
the pasteuriser's heating-exchanger UA as a representative loss
coefficient.
"""

from __future__ import annotations

from dataclasses import dataclass

from icecream_x.core.events import EventLog
from icecream_x.core.state import ProcessStage, ProductState
from icecream_x.equipment.pasteuriser import Pasteuriser
from icecream_x.thermodynamics.enthalpy import specific_enthalpy_j_kg
from icecream_x.utils.units import celsius_to_kelvin


@dataclass(frozen=True, slots=True)
class PasteurisationResult:
    final_state: ProductState
    heating_time_s: float
    holding_time_s: float
    cooling_time_s: float
    heating_energy_j: float
    holding_loss_j: float
    cooling_energy_j: float
    trajectory: list[ProductState]

    @property
    def total_time_s(self) -> float:
        return self.heating_time_s + self.holding_time_s + self.cooling_time_s

    @property
    def total_energy_input_j(self) -> float:
        """Net energy delivered by the utility systems (heating + hold-loss make-up)."""
        return max(self.heating_energy_j, 0.0) + self.holding_loss_j


def pasteurise(
    state: ProductState,
    pasteuriser: Pasteuriser,
    *,
    post_cooling_temperature_c: float = 4.0,
    ambient_temperature_k: float = 295.15,
    reference_temperature_k: float = 213.15,
    n_trajectory_samples: int = 10,
    event_log: EventLog | None = None,
) -> PasteurisationResult:
    comp = state.composition
    mass = comp.total_mass_kg
    t_start_k = state.temperature_k
    t_target_k = celsius_to_kelvin(pasteuriser.target_temperature_c)
    t_post_k = celsius_to_kelvin(post_cooling_temperature_c)

    heating_time_s = abs(t_target_k - t_start_k) / pasteuriser.heating_rate_c_per_s
    cooling_time_s = abs(t_target_k - t_post_k) / pasteuriser.cooling_rate_c_per_s
    holding_time_s = pasteuriser.holding_time_s

    h_start = specific_enthalpy_j_kg(comp, t_start_k, reference_temperature_k)
    h_target = specific_enthalpy_j_kg(comp, t_target_k, reference_temperature_k)
    h_post = specific_enthalpy_j_kg(comp, t_post_k, reference_temperature_k)

    heating_energy_j = mass * (h_target - h_start)
    cooling_energy_j = mass * (h_post - h_target)  # negative: heat removed

    # Parasitic holding-loss make-up energy: UA * (T_target - T_ambient) * time,
    # supplied by the utility system to keep the hold temperature constant.
    ua = pasteuriser.heating_exchanger.ua_w_per_k
    holding_loss_j = max(ua * (t_target_k - ambient_temperature_k), 0.0) * holding_time_s * 0.02

    trajectory: list[ProductState] = []

    def sample_ramp(t0_k: float, t1_k: float, duration_s: float, elapsed0_s: float, n: int) -> None:
        for i in range(n + 1):
            frac = i / n
            t_k = t0_k + (t1_k - t0_k) * frac
            trajectory.append(
                state.evolve(
                    temperature_k=t_k,
                    stage=ProcessStage.PASTEURISED,
                    elapsed_time_s=state.elapsed_time_s + elapsed0_s + duration_s * frac,
                )
            )

    n_each = max(n_trajectory_samples // 3, 2)
    sample_ramp(t_start_k, t_target_k, heating_time_s, 0.0, n_each)
    sample_ramp(t_target_k, t_target_k, holding_time_s, heating_time_s, 2)
    sample_ramp(t_target_k, t_post_k, cooling_time_s, heating_time_s + holding_time_s, n_each)

    final_elapsed = state.elapsed_time_s + heating_time_s + holding_time_s + cooling_time_s
    final_energy = state.cumulative_energy_j + max(heating_energy_j, 0.0) + holding_loss_j

    final_state = state.evolve(
        temperature_k=t_post_k,
        stage=ProcessStage.PASTEURISED,
        elapsed_time_s=final_elapsed,
        cumulative_energy_j=final_energy,
    )

    if event_log is not None:
        event_log.record(
            state.elapsed_time_s,
            ProcessStage.PASTEURISED.value,
            f"Pasteurised via {pasteuriser.name}",
            target_temperature_c=pasteuriser.target_temperature_c,
            holding_time_s=holding_time_s,
            heating_time_s=round(heating_time_s, 1),
            cooling_time_s=round(cooling_time_s, 1),
            heating_energy_kwh=round(max(heating_energy_j, 0.0) / 3_600_000.0, 4),
        )

    return PasteurisationResult(
        final_state=final_state,
        heating_time_s=heating_time_s,
        holding_time_s=holding_time_s,
        cooling_time_s=cooling_time_s,
        heating_energy_j=heating_energy_j,
        holding_loss_j=holding_loss_j,
        cooling_energy_j=cooling_energy_j,
        trajectory=trajectory,
    )
