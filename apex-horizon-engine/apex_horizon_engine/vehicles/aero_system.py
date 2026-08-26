"""
Aerodynamics: drag and downforce, both scaling with v^2 as in reality.

Downforce is split front/rear per ``AeroSpec.downforce_balance_front`` and
handed to ``vehicles.suspension`` as extra normal load -- this is the only
place downforce is allowed to matter, so a car with a bigger wing doesn't
mysteriously corner better through any other back channel.
"""

from __future__ import annotations

from dataclasses import dataclass

from apex_horizon_engine.utils.config import AeroSpec

AIR_DENSITY_KG_M3 = 1.225


@dataclass
class AeroForces:
    drag_n: float
    downforce_front_n: float
    downforce_rear_n: float

    @property
    def downforce_total_n(self) -> float:
        return self.downforce_front_n + self.downforce_rear_n


def compute_aero_forces(spec: AeroSpec, speed_mps: float, damage_drag_mult: float = 1.0) -> AeroForces:
    speed = max(0.0, speed_mps)
    q = 0.5 * AIR_DENSITY_KG_M3 * speed * speed  # dynamic pressure

    drag = q * spec.drag_coefficient * spec.frontal_area_m2 * damage_drag_mult
    total_downforce = q * spec.downforce_coefficient * spec.frontal_area_m2

    return AeroForces(
        drag_n=drag,
        downforce_front_n=total_downforce * spec.downforce_balance_front,
        downforce_rear_n=total_downforce * (1.0 - spec.downforce_balance_front),
    )
