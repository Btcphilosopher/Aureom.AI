"""
Unlock gating: which vehicles and upgrade parts a player can currently
buy, given their overall reputation tier and credit balance. Pure
read-only logic over ``utils.config`` presets + a
``progression.reputation.ReputationBook`` -- ownership/purchasing itself
lives in ``economy.vehicle_market``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from apex_horizon_engine.progression.reputation import ReputationBook
from apex_horizon_engine.utils.config import VEHICLE_PRESETS, UpgradePart, VehicleSpec


@dataclass
class UnlockStatus:
    item_id: str
    display_name: str
    unlocked: bool
    tier_required: int
    tier_current: int
    price_credits: int
    affordable: bool


def evaluate_vehicle_unlocks(reputation: ReputationBook, credits_balance: int) -> List[UnlockStatus]:
    tier = reputation.overall_tier()
    statuses = []
    for spec in VEHICLE_PRESETS.values():
        statuses.append(UnlockStatus(
            item_id=spec.vehicle_id, display_name=spec.display_name,
            unlocked=tier >= spec.tier, tier_required=spec.tier, tier_current=tier,
            price_credits=spec.base_price_credits, affordable=credits_balance >= spec.base_price_credits,
        ))
    return sorted(statuses, key=lambda s: s.tier_required)


def evaluate_part_unlocks(parts: List[UpgradePart], reputation: ReputationBook, credits_balance: int) -> List[UnlockStatus]:
    tier = reputation.overall_tier()
    statuses = []
    for part in parts:
        statuses.append(UnlockStatus(
            item_id=part.part_id, display_name=part.display_name,
            unlocked=tier >= part.tier_required, tier_required=part.tier_required, tier_current=tier,
            price_credits=part.price_credits, affordable=credits_balance >= part.price_credits,
        ))
    return sorted(statuses, key=lambda s: s.tier_required)


def can_purchase(vehicle: VehicleSpec, reputation: ReputationBook, credits_balance: int) -> bool:
    return reputation.overall_tier() >= vehicle.tier and credits_balance >= vehicle.base_price_credits


# A small stock catalogue of upgrade parts -- enough breadth to exercise
# economy.vehicle_market and the garage tuning UI without needing a full
# hand-authored parts database per vehicle.
STOCK_UPGRADE_PARTS: List[UpgradePart] = [
    UpgradePart("turbo_stage1", "turbo", "Stage 1 Turbo Kit", 4200, 1, torque_multiplier=1.12),
    UpgradePart("turbo_stage2", "turbo", "Stage 2 Turbo Kit", 9800, 2, torque_multiplier=1.28, mass_delta_kg=15),
    UpgradePart("engine_internals", "engine", "Forged Internals", 12500, 3, torque_multiplier=1.15, mass_delta_kg=8),
    UpgradePart("street_slicks", "tires", "Street Slick Compound", 2600, 1, mu_delta=0.08, mass_delta_kg=4),
    UpgradePart("semi_slicks", "tires", "Semi-Slick Compound", 6100, 2, mu_delta=0.18, mass_delta_kg=6),
    UpgradePart("coilovers", "suspension", "Adjustable Coilovers", 3400, 1, diff_lock_delta=0.0),
    UpgradePart("front_splitter", "aero", "Carbon Front Splitter", 2900, 1, downforce_delta=0.03, drag_delta=0.01),
    UpgradePart("rear_wing", "aero", "GT Rear Wing", 5200, 2, downforce_delta=0.09, drag_delta=0.025),
    UpgradePart("sequential_box", "gearbox", "Sequential Gearbox", 8800, 3, shift_time_delta_s=-0.09),
    UpgradePart("lsd_upgrade", "gearbox", "Limited-Slip Differential", 4700, 2, diff_lock_delta=0.25),
    UpgradePart("hybrid_boost", "hybrid", "KERS Hybrid Boost Unit", 21000, 5, torque_multiplier=1.2, mass_delta_kg=45),
    UpgradePart("weight_reduction", "engine", "Track Weight Reduction Kit", 7600, 2, mass_delta_kg=-60),
]


def apply_upgrade(spec: VehicleSpec, part: UpgradePart) -> VehicleSpec:
    """Return a *new* VehicleSpec with the part's deltas applied -- never
    mutates the shared preset."""
    import dataclasses
    engine = dataclasses.replace(spec.engine, points=[(rpm, t * part.torque_multiplier) for rpm, t in spec.engine.points])
    drivetrain = dataclasses.replace(
        spec.drivetrain,
        diff_lock=min(1.0, spec.drivetrain.diff_lock + part.diff_lock_delta),
        shift_time_s=max(0.02, spec.drivetrain.shift_time_s + part.shift_time_delta_s),
    )
    tires = dataclasses.replace(spec.tires, mu_peak=spec.tires.mu_peak + part.mu_delta)
    aero = dataclasses.replace(
        spec.aero,
        drag_coefficient=spec.aero.drag_coefficient + part.drag_delta,
        downforce_coefficient=spec.aero.downforce_coefficient + part.downforce_delta,
    )
    return dataclasses.replace(
        spec, mass_kg=max(700.0, spec.mass_kg + part.mass_delta_kg),
        engine=engine, drivetrain=drivetrain, tires=tires, aero=aero,
    )
