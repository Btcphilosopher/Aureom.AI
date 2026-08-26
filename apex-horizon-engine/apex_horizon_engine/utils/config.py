"""
Configuration objects and presets for APEX HORIZON ENGINE.

Nothing in this module *simulates* anything -- it only describes the
starting conditions (vehicle specs, world zones, engine tuning knobs) that
every other subsystem reads. Keeping all of it in plain, serialisable
dataclasses means the exact same objects can be built by hand in Python,
loaded from a save file (see ``core.state_manager``), or round-tripped
through JSON for tooling.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


# --------------------------------------------------------------------------- #
# Vehicles
# --------------------------------------------------------------------------- #

class DrivetrainLayout(str, Enum):
    FWD = "FWD"
    RWD = "RWD"
    AWD = "AWD"


class VehicleClass(str, Enum):
    HOT_HATCH = "hot_hatch"
    MUSCLE = "muscle"
    HYPERCAR = "hypercar"
    DRIFT = "drift"
    RALLY = "rally"
    ELECTRIC_HYPER = "electric_hyper"
    PROTOTYPE = "prototype"


@dataclass
class EngineCurve:
    """Torque(RPM) described as a piecewise-linear curve.

    ``points`` is a list of ``(rpm, torque_nm)`` pairs, sorted ascending.
    Interpolated at query time by :meth:`torque_at`; this is what makes
    the engine "feel" different across the rev range instead of just
    scaling a single peak-torque number.
    """

    points: List[Tuple[float, float]]
    redline_rpm: float
    idle_rpm: float = 900.0

    def torque_at(self, rpm: float) -> float:
        rpm = max(self.idle_rpm, min(rpm, self.redline_rpm))
        pts = self.points
        if rpm <= pts[0][0]:
            return pts[0][1]
        for (r0, t0), (r1, t1) in zip(pts, pts[1:]):
            if r0 <= rpm <= r1:
                if r1 == r0:
                    return t1
                frac = (rpm - r0) / (r1 - r0)
                return t0 + frac * (t1 - t0)
        return pts[-1][1]

    def peak_power_kw(self) -> float:
        best = 0.0
        for rpm, torque in self.points:
            power = torque * rpm * 2.0 * math.pi / 60.0 / 1000.0
            best = max(best, power)
        return best


@dataclass
class TireCompound:
    """Friction characteristics of a tire compound.

    ``peak_slip_ratio`` / ``peak_slip_angle`` are where longitudinal /
    lateral grip peak before falling off (the classic Pacejka "magic
    formula" hump) -- see ``vehicles.tire_model`` for the curve itself.
    """

    name: str
    mu_peak: float          # peak coefficient of friction, dry tarmac
    peak_slip_ratio: float  # ~0.10-0.20 for road tires, lower for slicks
    peak_slip_angle_deg: float
    wear_rate: float        # fraction of grip lost per km at full load
    optimal_temp_c: float = 90.0
    temp_sensitivity: float = 0.012  # grip loss per degree away from optimal


@dataclass
class SuspensionSpec:
    spring_rate_n_m: float
    damping_ratio: float
    travel_m: float
    anti_roll_bar: float = 0.5     # 0 = none, 1 = fully stiff (roll resistance)
    ride_height_m: float = 0.14


@dataclass
class AeroSpec:
    drag_coefficient: float
    frontal_area_m2: float
    downforce_coefficient: float   # generates downforce ~ v^2 like drag
    downforce_balance_front: float = 0.45  # fraction of total downforce on front axle


@dataclass
class DrivetrainSpec:
    layout: DrivetrainLayout
    gear_ratios: List[float]
    final_drive: float
    front_torque_split: float = 0.5   # only relevant for AWD
    diff_lock: float = 0.3            # 0 = open diff, 1 = fully locked
    shift_time_s: float = 0.15
    drivetrain_efficiency: float = 0.88
    is_electric: bool = False


@dataclass
class VehicleSpec:
    """Complete, self-contained definition of a car."""

    vehicle_id: str
    display_name: str
    vehicle_class: VehicleClass
    mass_kg: float
    wheelbase_m: float
    track_width_m: float
    cg_height_m: float
    weight_dist_front: float  # fraction of static weight on front axle
    drag_area_frontal: float
    engine: EngineCurve
    drivetrain: DrivetrainSpec
    tires: TireCompound
    suspension: SuspensionSpec
    aero: AeroSpec
    base_price_credits: int
    tier: int = 1  # unlock tier, gates it behind reputation/progression

    def weight_dist_rear(self) -> float:
        return 1.0 - self.weight_dist_front


# Upgrade deltas applied multiplicatively/additively on top of a VehicleSpec.
# See progression.unlock_tree and vehicles.vehicle_model for how these compose.
@dataclass
class UpgradePart:
    part_id: str
    category: str  # "engine" | "turbo" | "tires" | "suspension" | "aero" | "gearbox" | "hybrid"
    display_name: str
    price_credits: int
    tier_required: int
    torque_multiplier: float = 1.0
    mass_delta_kg: float = 0.0
    mu_delta: float = 0.0
    drag_delta: float = 0.0
    downforce_delta: float = 0.0
    diff_lock_delta: float = 0.0
    shift_time_delta_s: float = 0.0


def default_engine_curve(peak_torque: float, redline: float) -> EngineCurve:
    """Build a plausible naturally-aspirated-shaped torque curve from a
    single peak-torque figure, so vehicle presets stay readable."""
    idle = 900.0
    pts = [
        (idle, peak_torque * 0.35),
        (redline * 0.25, peak_torque * 0.72),
        (redline * 0.45, peak_torque * 0.95),
        (redline * 0.65, peak_torque * 1.00),
        (redline * 0.85, peak_torque * 0.90),
        (redline, peak_torque * 0.68),
    ]
    return EngineCurve(points=pts, redline_rpm=redline, idle_rpm=idle)


def _tires(name: str, mu: float, wear: float = 0.015, slip_ratio: float = 0.13,
           slip_angle: float = 8.0) -> TireCompound:
    return TireCompound(name=name, mu_peak=mu, peak_slip_ratio=slip_ratio,
                         peak_slip_angle_deg=slip_angle, wear_rate=wear)


VEHICLE_PRESETS: Dict[str, VehicleSpec] = {
    "meridian_gt_hatch": VehicleSpec(
        vehicle_id="meridian_gt_hatch", display_name="Meridian GT Hatch",
        vehicle_class=VehicleClass.HOT_HATCH, mass_kg=1280, wheelbase_m=2.60,
        track_width_m=1.55, cg_height_m=0.52, weight_dist_front=0.62,
        drag_area_frontal=2.15,
        engine=default_engine_curve(320, 7200),
        drivetrain=DrivetrainSpec(DrivetrainLayout.FWD, [3.4, 2.1, 1.5, 1.15, 0.92, 0.78], 3.9),
        tires=_tires("Street Sport", 1.05),
        suspension=SuspensionSpec(28000, 0.35, 0.12),
        aero=AeroSpec(0.31, 2.15, 0.05),
        base_price_credits=24000, tier=1,
    ),
    "ironclad_v8_muscle": VehicleSpec(
        vehicle_id="ironclad_v8_muscle", display_name="Ironclad V8",
        vehicle_class=VehicleClass.MUSCLE, mass_kg=1720, wheelbase_m=2.85,
        track_width_m=1.62, cg_height_m=0.55, weight_dist_front=0.53,
        drag_area_frontal=2.6,
        engine=default_engine_curve(710, 6800),
        drivetrain=DrivetrainSpec(DrivetrainLayout.RWD, [3.1, 2.0, 1.4, 1.0, 0.80], 3.3, diff_lock=0.55),
        tires=_tires("Sticky Street", 1.12, wear=0.02),
        suspension=SuspensionSpec(32000, 0.30, 0.13),
        aero=AeroSpec(0.34, 2.4, 0.08),
        base_price_credits=52000, tier=2,
    ),
    "solace_hypercar": VehicleSpec(
        vehicle_id="solace_hypercar", display_name="Solace Hypercar",
        vehicle_class=VehicleClass.HYPERCAR, mass_kg=1390, wheelbase_m=2.70,
        track_width_m=1.68, cg_height_m=0.42, weight_dist_front=0.42,
        drag_area_frontal=1.9,
        engine=default_engine_curve(880, 8600),
        drivetrain=DrivetrainSpec(DrivetrainLayout.AWD, [3.6, 2.3, 1.7, 1.3, 1.02, 0.82, 0.68], 3.6,
                                   front_torque_split=0.32, diff_lock=0.45, shift_time_s=0.08),
        tires=_tires("Semi-Slick", 1.35, wear=0.03, slip_ratio=0.11, slip_angle=7.0),
        suspension=SuspensionSpec(58000, 0.45, 0.09, anti_roll_bar=0.75),
        aero=AeroSpec(0.29, 1.9, 0.42, downforce_balance_front=0.38),
        base_price_credits=340000, tier=5,
    ),
    "vagrant_drift_spec": VehicleSpec(
        vehicle_id="vagrant_drift_spec", display_name="Vagrant Drift Spec",
        vehicle_class=VehicleClass.DRIFT, mass_kg=1310, wheelbase_m=2.62,
        track_width_m=1.58, cg_height_m=0.50, weight_dist_front=0.54,
        drag_area_frontal=2.2,
        engine=default_engine_curve(560, 7800),
        drivetrain=DrivetrainSpec(DrivetrainLayout.RWD, [3.3, 2.05, 1.45, 1.05, 0.85], 3.7, diff_lock=0.95),
        tires=_tires("Drift Compound", 0.95, wear=0.045, slip_ratio=0.09, slip_angle=5.0),
        suspension=SuspensionSpec(34000, 0.22, 0.14, anti_roll_bar=0.35),
        aero=AeroSpec(0.36, 2.25, 0.10),
        base_price_credits=61000, tier=2,
    ),
    "outrider_rally": VehicleSpec(
        vehicle_id="outrider_rally", display_name="Outrider Rally",
        vehicle_class=VehicleClass.RALLY, mass_kg=1260, wheelbase_m=2.55,
        track_width_m=1.54, cg_height_m=0.48, weight_dist_front=0.56,
        drag_area_frontal=2.3,
        engine=default_engine_curve(400, 6500),
        drivetrain=DrivetrainSpec(DrivetrainLayout.AWD, [3.8, 2.4, 1.7, 1.25, 0.98], 4.4,
                                   front_torque_split=0.45, diff_lock=0.7),
        tires=_tires("All-Terrain", 0.85, wear=0.02, slip_ratio=0.18, slip_angle=10.0),
        suspension=SuspensionSpec(24000, 0.55, 0.22, anti_roll_bar=0.4),
        aero=AeroSpec(0.42, 2.3, 0.06),
        base_price_credits=48000, tier=2,
    ),
    "arclight_ev_hyper": VehicleSpec(
        vehicle_id="arclight_ev_hyper", display_name="Arclight EV Hyper",
        vehicle_class=VehicleClass.ELECTRIC_HYPER, mass_kg=1980, wheelbase_m=2.75,
        track_width_m=1.70, cg_height_m=0.40, weight_dist_front=0.46,
        drag_area_frontal=1.95,
        engine=EngineCurve(points=[(0, 1150), (2000, 1150), (6000, 620), (11000, 300), (14000, 180)],
                            redline_rpm=14000, idle_rpm=0),
        drivetrain=DrivetrainSpec(DrivetrainLayout.AWD, [9.5], 1.0, front_torque_split=0.40,
                                   diff_lock=0.6, shift_time_s=0.0, drivetrain_efficiency=0.94,
                                   is_electric=True),
        tires=_tires("Semi-Slick", 1.30, wear=0.028, slip_ratio=0.10, slip_angle=7.0),
        suspension=SuspensionSpec(62000, 0.5, 0.09, anti_roll_bar=0.8),
        aero=AeroSpec(0.27, 1.95, 0.38, downforce_balance_front=0.40),
        base_price_credits=410000, tier=6,
    ),
    "horizon_x_prototype": VehicleSpec(
        vehicle_id="horizon_x_prototype", display_name="Horizon-X Prototype",
        vehicle_class=VehicleClass.PROTOTYPE, mass_kg=980, wheelbase_m=2.90,
        track_width_m=1.90, cg_height_m=0.32, weight_dist_front=0.40,
        drag_area_frontal=1.55,
        engine=EngineCurve(points=[(0, 900), (3000, 1400), (9000, 900), (13000, 500)],
                            redline_rpm=13000, idle_rpm=0),
        drivetrain=DrivetrainSpec(DrivetrainLayout.AWD, [7.2], 1.0, front_torque_split=0.5,
                                   diff_lock=0.5, shift_time_s=0.0, drivetrain_efficiency=0.95,
                                   is_electric=True),
        tires=_tires("Prototype Slick", 1.55, wear=0.05, slip_ratio=0.09, slip_angle=6.0),
        suspension=SuspensionSpec(85000, 0.55, 0.07, anti_roll_bar=0.9),
        aero=AeroSpec(0.24, 1.55, 0.70, downforce_balance_front=0.45),
        base_price_credits=900000, tier=8,
    ),
}


# --------------------------------------------------------------------------- #
# World
# --------------------------------------------------------------------------- #

class ZoneKind(str, Enum):
    MEGACITY = "megacity"
    INDUSTRIAL_DESERT = "industrial_desert"
    FOREST_MOUNTAIN = "forest_mountain"
    COASTAL_HIGHWAY = "coastal_highway"
    LOGISTICS_ZONE = "logistics_zone"


@dataclass
class ZoneSpec:
    zone_id: str
    kind: ZoneKind
    display_name: str
    center_xy: Tuple[float, float]
    radius_m: float
    base_grip: float               # baseline tarmac/surface friction multiplier
    traffic_density: float         # vehicles per km^2, baseline
    elevation_variance_m: float
    weather_bias: Dict[str, float] # weather -> relative likelihood weight
    hazard_types: List[str] = field(default_factory=list)


WORLD_ZONES: Dict[str, ZoneSpec] = {
    "meridian_city": ZoneSpec(
        "meridian_city", ZoneKind.MEGACITY, "Meridian Megacity",
        center_xy=(0.0, 0.0), radius_m=6000, base_grip=1.0, traffic_density=42.0,
        elevation_variance_m=25.0,
        weather_bias={"clear": 0.55, "rain": 0.25, "fog": 0.10, "storm": 0.10},
        hazard_types=["dense_traffic", "tunnels", "elevated_highway"],
    ),
    "silica_flats": ZoneSpec(
        "silica_flats", ZoneKind.INDUSTRIAL_DESERT, "Silica Flats",
        center_xy=(12000.0, 2000.0), radius_m=8000, base_grip=0.82, traffic_density=4.0,
        elevation_variance_m=8.0,
        weather_bias={"clear": 0.60, "sandstorm": 0.30, "fog": 0.10},
        hazard_types=["dry_lake", "solar_glare", "sandstorm"],
    ),
    "pinegrade_range": ZoneSpec(
        "pinegrade_range", ZoneKind.FOREST_MOUNTAIN, "Pinegrade Range",
        center_xy=(-9000.0, 7000.0), radius_m=9000, base_grip=0.90, traffic_density=6.0,
        elevation_variance_m=340.0,
        weather_bias={"clear": 0.40, "fog": 0.35, "rain": 0.20, "snow": 0.05},
        hazard_types=["hairpins", "wildlife", "fog_banks"],
    ),
    "azurewake_coast": ZoneSpec(
        "azurewake_coast", ZoneKind.COASTAL_HIGHWAY, "Azurewake Coast",
        center_xy=(2000.0, -11000.0), radius_m=7000, base_grip=0.95, traffic_density=10.0,
        elevation_variance_m=60.0,
        weather_bias={"clear": 0.50, "storm": 0.25, "rain": 0.20, "fog": 0.05},
        hazard_types=["bridges", "crosswinds", "cliff_edges"],
    ),
    "harborline_yards": ZoneSpec(
        "harborline_yards", ZoneKind.LOGISTICS_ZONE, "Harborline Yards",
        center_xy=(-3000.0, -6000.0), radius_m=5000, base_grip=0.88, traffic_density=18.0,
        elevation_variance_m=10.0,
        weather_bias={"clear": 0.55, "rain": 0.25, "fog": 0.20},
        hazard_types=["rail_crossings", "container_stacks", "heavy_machinery"],
    ),
}


# --------------------------------------------------------------------------- #
# Engine-wide tuning
# --------------------------------------------------------------------------- #

@dataclass
class EngineConfig:
    tick_rate_hz: float = 60.0
    seed: int = 42
    deterministic: bool = True
    starting_zone: str = "meridian_city"
    starting_vehicle: str = "meridian_gt_hatch"
    starting_credits: int = 35000
    streaming_radius_m: float = 2500.0
    day_length_minutes: float = 24.0  # in-world minutes for a full day/night cycle


def clone(obj):
    """Deep-copy any of the dataclasses above (used when handing a preset
    to a specific player/vehicle instance so mutation never bleeds back
    into the shared preset table)."""
    return dataclasses.replace(obj) if not _has_nested_dataclass(obj) else _deep_clone(obj)


def _has_nested_dataclass(obj) -> bool:
    if not dataclasses.is_dataclass(obj):
        return False
    return any(dataclasses.is_dataclass(getattr(obj, f.name)) for f in dataclasses.fields(obj))


def _deep_clone(obj):
    if dataclasses.is_dataclass(obj):
        kwargs = {}
        for f in dataclasses.fields(obj):
            kwargs[f.name] = _deep_clone(getattr(obj, f.name))
        return dataclasses.replace(obj, **kwargs)
    if isinstance(obj, list):
        return [_deep_clone(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _deep_clone(v) for k, v in obj.items()}
    return obj


def get_vehicle_preset(vehicle_id: str) -> VehicleSpec:
    if vehicle_id not in VEHICLE_PRESETS:
        raise KeyError(f"Unknown vehicle preset '{vehicle_id}'. Available: {sorted(VEHICLE_PRESETS)}")
    return _deep_clone(VEHICLE_PRESETS[vehicle_id])


def get_zone(zone_id: str) -> ZoneSpec:
    if zone_id not in WORLD_ZONES:
        raise KeyError(f"Unknown zone '{zone_id}'. Available: {sorted(WORLD_ZONES)}")
    return WORLD_ZONES[zone_id]
