"""
Digital-twin mode (section 40 of the HydroFlux specification).

A lightweight state container that can ingest live/periodic telemetry and
produce a recommended operating state via the same optimisation machinery
used for offline studies. The digital twin never actuates equipment -- it
only recommends, and every recommendation still passes through
:class:`hydroflux.core.safety.SafetyGovernor` before being reported as
"permitted".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from hydroflux.core.config import HydroSystemConfig
from hydroflux.core.safety import HardConstraints, PermittedAction, SafetyGovernor


@dataclass
class TelemetrySnapshot:
    timestamp: datetime
    flow_m3s: Optional[float] = None
    head_m: Optional[float] = None
    reservoir_level_m: Optional[float] = None
    turbine_speed_rpm: Optional[float] = None
    turbine_power_mw: Optional[float] = None
    temperature_c: Optional[float] = None
    vibration_mm_s: Optional[float] = None
    gate_position_pct: Optional[float] = None


class DigitalTwin:
    """Tracks the latest known physical state of a HydroFlux system and
    turns it into a recommended (not executed) operating state."""

    def __init__(self, config: HydroSystemConfig, hard_constraints: Optional[HardConstraints] = None):
        self.config = config
        self.history: list[TelemetrySnapshot] = []
        self.governor = SafetyGovernor(hard_constraints or HardConstraints())

    def update_state(self, telemetry: TelemetrySnapshot) -> None:
        self.history.append(telemetry)

    @property
    def latest(self) -> Optional[TelemetrySnapshot]:
        return self.history[-1] if self.history else None

    def recommend_operating_state(self, price: Optional[float] = None) -> PermittedAction:
        """Recommend a flow/power set-point from the latest telemetry.

        This is intentionally simple (a single-step best-response using the
        turbine efficiency envelope) -- the point of the digital twin layer
        is the telemetry -> state -> recommendation -> safety-check loop,
        which higher-fidelity turbine/reservoir models can plug into
        without changing this contract.
        """

        snap = self.latest
        if snap is None or snap.flow_m3s is None or snap.head_m is None:
            return self.governor.enforce({})

        from hydroflux.turbines.turbines import Turbine, make_turbine_from_config

        best_power = 0.0
        best_flow = 0.0
        rated_total = 0.0
        for turbine_config in self.config.turbines:
            turbine: Turbine = make_turbine_from_config(turbine_config)
            rated_total += turbine.rated_power_mw
            flow_share = snap.flow_m3s / max(len(self.config.turbines), 1)
            power = turbine.output_power_mw(flow_share, snap.head_m)
            best_power += power
            best_flow += min(flow_share, turbine.maximum_flow_m3s)

        request = {
            "flow_m3s": best_flow,
            "power_mw": best_power,
            "rated_power_mw": rated_total,
            "reservoir_level_m": snap.reservoir_level_m,
        }
        return self.governor.enforce(request)
