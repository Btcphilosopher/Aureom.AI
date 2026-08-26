"""
Garage screen data assembly: owned vehicle collection, tuning comparisons
(stock vs. with a candidate upgrade part applied), and simple derived
performance analytics (estimated 0-100 km/h time, top speed) computed by
actually running the vehicle model rather than hand-authored numbers --
so a tuning change visibly moves these figures for the right reasons.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from apex_horizon_engine.physics.traction_model import SurfaceCondition
from apex_horizon_engine.progression.unlock_tree import STOCK_UPGRADE_PARTS, apply_upgrade
from apex_horizon_engine.utils.config import UpgradePart, VehicleSpec
from apex_horizon_engine.vehicles.vehicle_model import Vehicle, VehicleControls


@dataclass
class PerformanceEstimate:
    zero_to_100_s: Optional[float]
    top_speed_kph: float
    peak_hp: float


@dataclass
class GarageEntry:
    spec: VehicleSpec
    owned_upgrade_ids: List[str]

    def effective_spec(self) -> VehicleSpec:
        spec = self.spec
        for part_id in self.owned_upgrade_ids:
            part = next((p for p in STOCK_UPGRADE_PARTS if p.part_id == part_id), None)
            if part:
                spec = apply_upgrade(spec, part)
        return spec


def estimate_performance(spec: VehicleSpec, sim_seconds: float = 20.0, dt: float = 1 / 60) -> PerformanceEstimate:
    """Runs a straight-line full-throttle simulation on dry pavement to
    derive 0-100 and top speed -- real numbers out of the real physics
    stack, not hand-tuned display values."""
    vehicle = Vehicle(spec)
    condition = SurfaceCondition(base_grip=1.0, wetness=0.0)
    controls = VehicleControls(throttle=1.0)
    zero_to_100_s = None
    ticks = int(sim_seconds / dt)
    top_speed = 0.0
    for i in range(ticks):
        telemetry = vehicle.step(dt, controls, condition)
        top_speed = max(top_speed, telemetry.speed_kph)
        if zero_to_100_s is None and telemetry.speed_kph >= 100.0:
            zero_to_100_s = round(i * dt, 2)
    return PerformanceEstimate(
        zero_to_100_s=zero_to_100_s, top_speed_kph=round(top_speed, 1),
        peak_hp=round(spec.engine.peak_power_kw() * 1.34102, 1),
    )


def compare_with_upgrade(spec: VehicleSpec, part: UpgradePart) -> tuple[PerformanceEstimate, PerformanceEstimate]:
    stock = estimate_performance(spec, sim_seconds=12.0)
    upgraded = estimate_performance(apply_upgrade(spec, part), sim_seconds=12.0)
    return stock, upgraded


def build_collection_view(entries: List[GarageEntry]) -> List[dict]:
    return [
        {
            "vehicle_id": e.spec.vehicle_id,
            "display_name": e.spec.display_name,
            "class": e.spec.vehicle_class.value,
            "upgrades_installed": len(e.owned_upgrade_ids),
        }
        for e in entries
    ]
