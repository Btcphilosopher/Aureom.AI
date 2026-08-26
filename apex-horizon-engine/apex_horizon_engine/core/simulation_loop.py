"""
Fixed-timestep simulation loop driving ``core.engine.ApexHorizonEngine``.

Mirrors the shape of a real game loop (fixed ``dt``, accumulate frames,
periodic logging) but stays headless -- no windowing/input dependency --
so it works identically from ``main.py``, a test, or a notebook.
"""

from __future__ import annotations

import math
import random
from typing import Callable, List, Optional

from apex_horizon_engine.ai.traffic_ai import SteerTarget, follow_point_controls
from apex_horizon_engine.core.engine import ApexHorizonEngine, EngineFrame
from apex_horizon_engine.utils.logging import get_logger
from apex_horizon_engine.vehicles.vehicle_model import VehicleControls

logger = get_logger("core.simulation_loop")

ControlsFn = Callable[[ApexHorizonEngine], VehicleControls]


def default_autopilot(engine: ApexHorizonEngine, rng: Optional[random.Random] = None) -> VehicleControls:
    """A minimal self-driving controller so a fully headless run has
    something to observe: when an event is active it chases the same
    route waypoints the AI rivals use (see ``core.engine`` for how player
    lap progress is tracked against that route); otherwise it wanders
    toward a loose random target inside the current zone. Real input
    (a human, or a smarter bot) is a drop-in replacement -- just pass a
    different ``controls_fn`` to :func:`run_simulation`.
    """
    # Deliberately not falling back to the global ``random`` module here:
    # that module's state is process-global and call-order-dependent, so
    # using it would silently break EngineConfig.deterministic for any
    # headless run. The engine owns a seeded RNG for exactly this.
    rng = rng or engine._autopilot_rng
    state = engine.player_vehicle.state

    if engine.active_race is not None:
        wp = engine.active_race.route[engine.active_race.player_waypoint_index]
        target = SteerTarget(wp.x, wp.y, speed_limit_mps=max(14.0, 40.0 - wp.corner_sharpness * 22.0))
        return follow_point_controls(state, target, steer_gain=1.8)

    zone = engine.streamer.nearest_zone(state.x, state.y)
    if engine._autopilot_wander_target is None:
        engine._autopilot_wander_target = _random_zone_point(zone, rng)
    tx, ty = engine._autopilot_wander_target
    if math.hypot(tx - state.x, ty - state.y) < 40.0:
        engine._autopilot_wander_target = _random_zone_point(zone, rng)
        tx, ty = engine._autopilot_wander_target
    target = SteerTarget(tx, ty, speed_limit_mps=24.0)
    return follow_point_controls(state, target)


def _random_zone_point(zone, rng: random.Random):
    angle = rng.uniform(0, 2 * math.pi)
    radius = rng.uniform(0.1, 0.8) * zone.radius_m
    return zone.center_xy[0] + radius * math.cos(angle), zone.center_xy[1] + radius * math.sin(angle)


def run_simulation(
    engine: ApexHorizonEngine,
    ticks: int,
    dt: Optional[float] = None,
    controls_fn: Optional[ControlsFn] = None,
    log_interval: int = 0,
    frame_callback: Optional[Callable[[EngineFrame], None]] = None,
) -> List[EngineFrame]:
    """Advance ``engine`` for ``ticks`` fixed steps, returning the full
    per-tick :class:`EngineFrame` history. Pass ``log_interval`` > 0 to
    emit a dashboard log line every N ticks."""
    dt = dt if dt is not None else 1.0 / engine.config.tick_rate_hz
    controls_fn = controls_fn or default_autopilot
    frames: List[EngineFrame] = []

    for i in range(ticks):
        controls = controls_fn(engine)
        frame = engine.tick(dt, controls)
        frames.append(frame)
        if frame_callback:
            frame_callback(frame)
        if log_interval and (i % log_interval == 0):
            logger.info(
                "t=%6.1fs zone=%-18s wx=%-9s spd=%5.1fkph gear=%s rpm=%5.0f event=%-14s stars=%d credits=%d",
                frame.sim_time_s, frame.zone_name, frame.weather, frame.telemetry.speed_kph,
                frame.telemetry.gear, frame.telemetry.rpm, frame.active_event or "-",
                frame.wanted_stars, frame.credits,
            )
    return frames
