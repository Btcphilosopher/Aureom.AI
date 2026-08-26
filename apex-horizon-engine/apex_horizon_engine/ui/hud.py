"""
HUD frame assembly: pulls together telemetry, drift, police, and economy
state into one flat, display-ready snapshot each tick. Owns no state of
its own -- pure aggregation, so it can't drift out of sync with the
systems it reports on.
"""

from __future__ import annotations

from dataclasses import dataclass

from apex_horizon_engine.vehicles.vehicle_model import TelemetrySample


@dataclass
class HUDFrame:
    speed_kph: float
    speed_mph: float
    rpm: float
    rpm_frac: float
    gear_label: str
    drift_phase: str
    drift_angle_deg: float
    wanted_stars: int
    credits: int
    zone_name: str
    weather_label: str
    time_of_day_label: str
    damage_pct: float


def _gear_label(gear: int) -> str:
    if gear <= 0:
        return "R"
    return str(gear)


def _time_label(time_of_day_frac: float) -> str:
    total_minutes = int(time_of_day_frac * 24 * 60)
    hh, mm = divmod(total_minutes, 60)
    return f"{hh:02d}:{mm:02d}"


def build_hud_frame(
    telemetry: TelemetrySample,
    redline_rpm: float,
    wanted_stars: int,
    credits: int,
    zone_name: str,
    weather_label: str,
    time_of_day_frac: float,
    damage_fraction: float,
) -> HUDFrame:
    return HUDFrame(
        speed_kph=round(telemetry.speed_kph, 1),
        speed_mph=round(telemetry.speed_kph * 0.621371, 1),
        rpm=round(telemetry.rpm),
        rpm_frac=max(0.0, min(1.0, telemetry.rpm / max(1.0, redline_rpm))),
        gear_label=_gear_label(telemetry.gear),
        drift_phase=telemetry.drift_phase,
        drift_angle_deg=round(telemetry.drift_angle_deg, 1),
        wanted_stars=wanted_stars,
        credits=credits,
        zone_name=zone_name,
        weather_label=weather_label,
        time_of_day_label=_time_label(time_of_day_frac),
        damage_pct=round(damage_fraction * 100.0, 1),
    )
