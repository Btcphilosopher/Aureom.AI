"""
APEX HORIZON ENGINE -- command-line entry point.

Examples
--------
Free-roam a hot hatch through the megacity for two minutes::

    python -m apex_horizon_engine.main --zone meridian_city --vehicle meridian_gt_hatch --duration 120

Try the desert dry-lake zone in a hypercar, exporting telemetry::

    python -m apex_horizon_engine.main --zone silica_flats --vehicle solace_hypercar --duration 90 --csv out.csv

Run the deterministic replay check (same seed, same checksums)::

    python -m apex_horizon_engine.main --determinism-check
"""

from __future__ import annotations

import argparse
import csv
import sys
from typing import List

from apex_horizon_engine.core.engine import ApexHorizonEngine
from apex_horizon_engine.core.simulation_loop import run_simulation
from apex_horizon_engine.multiplayer.sync_system import lockstep_checksum
from apex_horizon_engine.utils.config import VEHICLE_PRESETS, WORLD_ZONES, EngineConfig
from apex_horizon_engine.utils.logging import get_logger, setup_logging

logger = get_logger("main")


def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="APEX HORIZON ENGINE -- open-world racing simulation")
    p.add_argument("--vehicle", choices=sorted(VEHICLE_PRESETS), default="meridian_gt_hatch")
    p.add_argument("--zone", choices=sorted(WORLD_ZONES), default="meridian_city")
    p.add_argument("--duration", type=float, default=120.0, help="Simulated seconds to run.")
    p.add_argument("--tick-rate", type=float, default=60.0)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--credits", type=int, default=35000)
    p.add_argument("--log-interval-s", type=float, default=10.0, help="Seconds between dashboard log lines.")
    p.add_argument("--csv", default=None, help="Write full per-tick telemetry to this CSV path.")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--determinism-check", action="store_true",
                    help="Run two identical-seed simulations and verify their lockstep checksums match.")
    return p.parse_args(argv)


def build_config(args: argparse.Namespace) -> EngineConfig:
    return EngineConfig(
        tick_rate_hz=args.tick_rate, seed=args.seed, starting_zone=args.zone,
        starting_vehicle=args.vehicle, starting_credits=args.credits,
    )


def _write_csv(path: str, frames) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["tick", "sim_time_s", "zone", "weather", "speed_kph", "rpm", "gear",
                          "drift_phase", "drift_angle_deg", "credits", "wanted_stars", "event"])
        for fr in frames:
            t = fr.telemetry
            writer.writerow([fr.tick, round(fr.sim_time_s, 3), fr.zone_name, fr.weather,
                              round(t.speed_kph, 2), round(t.rpm), t.gear, t.drift_phase,
                              round(t.drift_angle_deg, 2), fr.credits, fr.wanted_stars, fr.active_event or ""])


def run_determinism_check(args: argparse.Namespace) -> bool:
    dt = 1.0 / args.tick_rate
    ticks = max(60, int(args.duration * args.tick_rate))

    def run_once():
        engine = ApexHorizonEngine(build_config(args))
        frames = run_simulation(engine, ticks=min(ticks, 1200), dt=dt, log_interval=0)
        return lockstep_checksum(engine.tick_count, {"player": engine.player_vehicle}), frames[-1]

    checksum_a, frame_a = run_once()
    checksum_b, frame_b = run_once()
    ok = checksum_a == checksum_b
    logger.info("Determinism check: %s (%s vs %s)", "PASS" if ok else "FAIL", checksum_a, checksum_b)
    return ok


def main(argv: List[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    setup_logging()

    if args.determinism_check:
        return 0 if run_determinism_check(args) else 1

    config = build_config(args)
    engine = ApexHorizonEngine(config)
    dt = 1.0 / config.tick_rate_hz
    ticks = max(1, int(args.duration * config.tick_rate_hz))
    log_interval = 0 if args.quiet else max(1, int(args.log_interval_s * config.tick_rate_hz))

    logger.info("APEX HORIZON ENGINE -- starting %s in %s for %.1fs (seed=%d)",
                VEHICLE_PRESETS[args.vehicle].display_name, WORLD_ZONES[args.zone].display_name,
                args.duration, args.seed)

    frames = run_simulation(engine, ticks=ticks, dt=dt, log_interval=log_interval)

    last = frames[-1]
    top_speed = max(f.telemetry.speed_kph for f in frames)
    distance_km = engine.player_vehicle.state.odometer_m / 1000.0

    print("\n=== SESSION SUMMARY ===")
    print(f"  Zone (final):        {last.zone_name}")
    print(f"  Weather (final):     {last.weather}")
    print(f"  Distance driven:     {distance_km:.2f} km")
    print(f"  Top speed:           {top_speed:.1f} kph")
    print(f"  Credits:             {last.credits}")
    print(f"  Reputation:          {last.reputation}")
    print(f"  Festival tier:       {engine.festival.global_tier(engine.reputation)}")
    print(f"  Events completed:    {engine.events_completed} (won {engine.events_won})")
    print(f"  Wanted stars:        {last.wanted_stars}")
    print(f"  Player style:        {last.style_preferences}")

    if args.csv:
        _write_csv(args.csv, frames)
        logger.info("Wrote telemetry CSV to %s", args.csv)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
