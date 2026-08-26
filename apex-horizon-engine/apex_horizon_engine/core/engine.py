"""
ApexHorizonEngine: the top-level object wiring every subsystem into one
tickable simulation.

This is the only module allowed to import "across the grain" (physics
talking to progression, AI talking to economy, etc.) -- every other
subsystem stays decoupled from its neighbours and only this class knows
how they compose. One call to :meth:`ApexHorizonEngine.tick` advances the
*entire* world by ``dt`` seconds: weather, streaming, traffic, the
player's own vehicle physics, any active AI event, police, progression,
economy, and the adaptive player-style model.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from apex_horizon_engine.ai.adaptive_ai import PlayerStyleModel
from apex_horizon_engine.ai.crowd_simulation import CrowdState
from apex_horizon_engine.ai.racer_ai import RacerAI, build_lap_route
from apex_horizon_engine.core.world_streaming import StreamingReport, WorldStreamer
from apex_horizon_engine.economy.credits import CreditLedger
from apex_horizon_engine.economy.sponsorships import SponsorshipBook
from apex_horizon_engine.economy.vehicle_market import VehicleMarket
from apex_horizon_engine.physics.collision import CircleBody, detect_collision, impulse_magnitude, resolve_collision
from apex_horizon_engine.physics.damage_model import apply_collision_damage
from apex_horizon_engine.physics.traction_model import SurfaceCondition
from apex_horizon_engine.progression.festival_system import FestivalSystem
from apex_horizon_engine.progression.reputation import ReputationBook
from apex_horizon_engine.utils.config import EngineConfig, WORLD_ZONES, get_vehicle_preset
from apex_horizon_engine.utils.logging import get_logger
from apex_horizon_engine.vehicles.vehicle_model import TelemetrySample, Vehicle, VehicleControls
from apex_horizon_engine.world.event_generation import EventGenerator, EventSpec, EventType
from apex_horizon_engine.world.police_system import PoliceSystem
from apex_horizon_engine.world.traffic_system import TrafficSystem
from apex_horizon_engine.world.weather_system import WeatherSystem

logger = get_logger("core.engine")

RACER_ARCHETYPE_TUNING = {
    "drift_focused": dict(skill=0.6, aggression=0.55),
    "highway_aggressive": dict(skill=0.65, aggression=0.75),
    "technical": dict(skill=0.78, aggression=0.4),
    "rally_specialist": dict(skill=0.6, aggression=0.5),
    "balanced": dict(skill=0.55, aggression=0.5),
}

PLAYER_COLLISION_RADIUS_M = 1.7


@dataclass
class ActiveRace:
    spec: EventSpec
    rivals: List[RacerAI]
    route: List
    player_waypoint_index: int = 0
    player_laps_completed: int = 0
    time_elapsed_s: float = 0.0
    finished: bool = False
    player_place: int = 0


@dataclass
class EngineFrame:
    """Everything a CLI/UI layer needs out of one tick, gathered in one
    place so ``main.py`` doesn't have to reach into engine internals."""
    tick: int
    sim_time_s: float
    telemetry: TelemetrySample
    zone_name: str
    weather: str
    is_night: bool
    wanted_stars: int
    credits: int
    reputation: Dict[str, float]
    active_event: Optional[str]
    race_place: Optional[int]
    crowd_cheer: float
    style_preferences: Dict[str, float]


class ApexHorizonEngine:
    def __init__(self, config: Optional[EngineConfig] = None):
        self.config = config or EngineConfig()
        self._rng = random.Random(self.config.seed)
        self.tick_count = 0
        self.sim_time_s = 0.0

        self.weather = WeatherSystem(WORLD_ZONES, seed=self.config.seed, day_length_minutes=self.config.day_length_minutes)
        self.streamer = WorldStreamer(WORLD_ZONES, streaming_radius_m=self.config.streaming_radius_m)
        self.traffic = TrafficSystem(WORLD_ZONES, seed=self.config.seed)
        self.police = PoliceSystem(_rng=random.Random(self.config.seed + 1))
        self.event_generator = EventGenerator(seed=self.config.seed)

        self.reputation = ReputationBook()
        self.credits = CreditLedger(balance=self.config.starting_credits)
        self.festival = FestivalSystem()
        self.sponsorships = SponsorshipBook()
        self.market = VehicleMarket(seed=self.config.seed)
        self.style_model = PlayerStyleModel(_rng=random.Random(self.config.seed + 2))
        self.crowd = CrowdState()

        self.player_vehicle = Vehicle(get_vehicle_preset(self.config.starting_vehicle))
        start_zone = WORLD_ZONES[self.config.starting_zone]
        self.player_vehicle.state.x, self.player_vehicle.state.y = start_zone.center_xy
        self.owned_vehicle_ids: List[str] = [self.config.starting_vehicle]

        self.active_race: Optional[ActiveRace] = None
        self.events_completed = 0
        self.events_won = 0
        self._event_cooldown_s = 4.0
        self._last_streaming_report: Optional[StreamingReport] = None
        self._sponsor_income_timer_s = 0.0
        # Scratch slot + dedicated seeded RNG for
        # core.simulation_loop.default_autopilot's wander target; the
        # engine itself never reads either. Owning a seeded RNG here
        # (rather than the autopilot falling back to the global ``random``
        # module) is what keeps a fully headless/autopiloted run
        # reproducible under EngineConfig.deterministic.
        self._autopilot_wander_target: Optional[tuple] = None
        self._autopilot_rng = random.Random(self.config.seed + 999)

    # -- per-tick orchestration ---------------------------------------------------
    def tick(self, dt: float, player_controls: Optional[VehicleControls] = None) -> EngineFrame:
        self.weather.update(dt)
        report = self.streamer.update(self.player_vehicle.state.x, self.player_vehicle.state.y)
        self._last_streaming_report = report
        zone = report.active_zone
        weather_state = self.weather.condition_for(zone.zone_id)

        condition = SurfaceCondition(base_grip=zone.base_grip, wetness=weather_state.wetness)

        controls = player_controls or VehicleControls()
        telemetry = self.player_vehicle.step(dt, controls, condition, ambient_temp_c=22.0 - 8.0 * self.weather.clock.is_night)

        self.traffic.update_population(zone, self.config.streaming_radius_m)
        condition_by_zone = {zid: SurfaceCondition(base_grip=z.base_grip,
                                                     wetness=self.weather.condition_for(zid).wetness)
                              for zid, z in WORLD_ZONES.items()}
        player_point = [(self.player_vehicle.state.x, self.player_vehicle.state.y)]
        self.traffic.step(dt, condition_by_zone, extra_obstacles=player_point)
        self._resolve_player_traffic_collision(dt)

        self._update_police(dt, telemetry, zone)
        self._update_adaptive_model(dt, telemetry)
        self._update_event_lifecycle(dt, zone, weather_state.kind)
        self._update_crowd(dt, telemetry)
        self._update_sponsorships(dt)

        self.tick_count += 1
        self.sim_time_s += dt

        return EngineFrame(
            tick=self.tick_count, sim_time_s=self.sim_time_s, telemetry=telemetry,
            zone_name=zone.display_name, weather=weather_state.kind.value,
            is_night=self.weather.clock.is_night, wanted_stars=self.police.wanted_stars,
            credits=self.credits.balance, reputation=self.reputation.as_dict(),
            active_event=self.active_race.spec.event_type.value if self.active_race else None,
            race_place=self.active_race.player_place if self.active_race else None,
            crowd_cheer=round(self.crowd.cheer_intensity, 3),
            style_preferences=self.style_model.style_preferences(),
        )

    # -- collisions ---------------------------------------------------------------
    def _resolve_player_traffic_collision(self, dt: float) -> None:
        pv = self.player_vehicle.state
        player_body = CircleBody("player", pv.x, pv.y, PLAYER_COLLISION_RADIUS_M,
                                  self.player_vehicle.spec.mass_kg, pv.vx, pv.vy)
        for npc in self.traffic.active:
            nv = npc.vehicle.state
            npc_body = CircleBody(npc.npc_id, nv.x, nv.y, 1.6, npc.vehicle.spec.mass_kg, nv.vx, nv.vy)
            info = detect_collision(player_body, npc_body)
            if info is None:
                continue
            resolve_collision(player_body, npc_body, info)
            impulse = impulse_magnitude(player_body.mass_kg, npc_body.mass_kg, info.impact_speed_mps)
            apply_collision_damage(pv.damage, impulse)
            apply_collision_damage(nv.damage, impulse)
            pv.x, pv.y, pv.vx, pv.vy = player_body.x, player_body.y, player_body.vx, player_body.vy
            nv.x, nv.y, nv.vx, nv.vy = npc_body.x, npc_body.y, npc_body.vx, npc_body.vy
            # A collision impulse changes body velocity instantly, but a
            # wheel can't spin up/down that fast -- without resyncing it,
            # the drivetrain would read a wildly wrong RPM/gear off a
            # wheel speed left over from before the hit. Snap both axles'
            # angular speed back to rolling contact with the new speed as
            # a reasonable post-impact approximation (real grip re-bites
            # within a few tire revolutions, not instantly, but "instantly"
            # beats "stuck at the pre-collision value indefinitely").
            self.player_vehicle.state.w_front = pv.vx / self.player_vehicle.wheel_radius_m
            self.player_vehicle.state.w_rear = pv.vx / self.player_vehicle.wheel_radius_m
            npc.vehicle.state.w_front = nv.vx / npc.vehicle.wheel_radius_m
            npc.vehicle.state.w_rear = nv.vx / npc.vehicle.wheel_radius_m
            if impulse > 4000:
                self.police.register_infraction("collision", severity=min(2.0, impulse / 20000))

    # -- police ---------------------------------------------------------------------
    def _update_police(self, dt: float, telemetry: TelemetrySample, zone) -> None:
        speed_limit_kph = 55.0 if zone.kind.value == "megacity" else 90.0
        if telemetry.speed_kph > speed_limit_kph * 1.4:
            # Heat from sustained speeding accrues as a per-second rate
            # (scaled by dt), not a flat per-tick jump -- otherwise a
            # continuous violation would max out the wanted level in a
            # fraction of a second regardless of tick rate.
            self.police.register_infraction("speeding", severity=0.5 * dt)
        condition = SurfaceCondition(base_grip=zone.base_grip, wetness=self.weather.condition_for(zone.zone_id).wetness)
        self.police.update(dt, self.player_vehicle.state.x, self.player_vehicle.state.y,
                            self.player_vehicle.state.speed_mps, condition)

    # -- adaptive AI ------------------------------------------------------------------
    def _update_adaptive_model(self, dt: float, telemetry: TelemetrySample) -> None:
        near_top_speed = telemetry.rpm > 0 and telemetry.gear == max(1, telemetry.gear)  # cheap proxy, refined below
        near_top_speed = telemetry.speed_kph > 0 and (telemetry.long_accel_g < 0.05 and telemetry.speed_kph > 120)
        self.style_model.observe_tick(
            drift_phase=telemetry.drift_phase, lat_accel_g=telemetry.lat_accel_g,
            long_accel_g=telemetry.long_accel_g, off_road=False, near_top_speed=near_top_speed,
        )
        self.style_model.decay_toward_neutral(dt)

    # -- crowd ------------------------------------------------------------------------
    def _update_crowd(self, dt: float, telemetry: TelemetrySample) -> None:
        action = 0.0
        if telemetry.drift_phase in ("drift", "transition"):
            action += min(1.0, telemetry.drift_angle_deg / 60.0)
        if telemetry.speed_kph > 140:
            action += 0.3
        if self.active_race is not None:
            action += 0.4
        tier = self.festival.global_tier(self.reputation)
        self.crowd.update(dt, min(1.0, action), tier)

    # -- sponsorships -------------------------------------------------------------------
    def _update_sponsorships(self, dt: float) -> None:
        self._sponsor_income_timer_s += dt
        day_s = max(60.0, self.config.day_length_minutes * 60.0)
        if self._sponsor_income_timer_s >= day_s:
            self._sponsor_income_timer_s -= day_s
            income = self.sponsorships.daily_income()
            if income:
                self.credits.earn(income, reason="sponsorship_income")
            lapsed = self.sponsorships.check_upkeep(self.reputation)
            for sponsor_id in lapsed:
                logger.info("Sponsorship lapsed: %s (reputation fell below upkeep)", sponsor_id)

    # -- event / race lifecycle ----------------------------------------------------------
    def _update_event_lifecycle(self, dt: float, zone, weather_kind) -> None:
        if self.active_race is None:
            self._event_cooldown_s -= dt
            if self._event_cooldown_s <= 0:
                self._start_event(zone, weather_kind)
            return

        race = self.active_race
        race.time_elapsed_s += dt
        condition = SurfaceCondition(base_grip=zone.base_grip, wetness=self.weather.condition_for(zone.zone_id).wetness)

        rival_positions = [(r.vehicle.state.x, r.vehicle.state.y) for r in race.rivals]
        for rival in race.rivals:
            others = [p for p in rival_positions if p != (rival.vehicle.state.x, rival.vehicle.state.y)]
            controls = rival.step(dt, condition, rival_positions=others)
            rival.vehicle.step(dt, controls, condition)

        # Track the player's own progress along the same route the rivals
        # use, exactly the way ``ai.racer_ai.RacerAI.step`` does for them
        # -- so a fully headless/autopiloted run (see main.py) closes the
        # loop without any external caller having to drive it.
        wp = race.route[race.player_waypoint_index]
        pv = self.player_vehicle.state
        if math.hypot(wp.x - pv.x, wp.y - pv.y) < 20.0:
            race.player_waypoint_index += 1
            if race.player_waypoint_index >= len(race.route):
                race.player_waypoint_index = 0
                race.player_laps_completed += 1

        finishers_ahead_of_player = sum(1 for r in race.rivals if r.laps_completed > race.player_laps_completed)
        race.player_place = finishers_ahead_of_player + 1

        target_laps = race.spec.laps
        player_done = race.player_laps_completed >= target_laps
        timeout = race.time_elapsed_s > 600.0
        if player_done or timeout:
            self._finish_event(finishers_ahead_of_player == 0 and player_done)

    def advance_player_lap_progress(self, waypoint_reached: bool, lap_completed: bool) -> None:
        """Called by the driving/track-progress layer (main.py's demo
        loop, or a future input layer) when the player crosses a route
        waypoint/finish line during an active race."""
        if self.active_race is None:
            return
        if lap_completed:
            self.active_race.player_laps_completed += 1

    def _start_event(self, zone, weather_kind) -> None:
        spec = self.event_generator.generate(zone, weather_kind, self.reputation.as_dict(),
                                              self.style_model.style_preferences())
        route = build_lap_route(zone.center_xy[0], zone.center_xy[1],
                                 radius_m=min(zone.radius_m * 0.6, 900.0), waypoint_count=10, rng=self._rng)
        rivals = []
        for i in range(spec.rival_count):
            archetype = self.style_model.sample_archetype()
            tuning = RACER_ARCHETYPE_TUNING.get(archetype, RACER_ARCHETYPE_TUNING["balanced"])
            vehicle = Vehicle(get_vehicle_preset(self._rng.choice(
                ["meridian_gt_hatch", "ironclad_v8_muscle", "vagrant_drift_spec", "outrider_rally"])))
            vehicle.state.x, vehicle.state.y = route[0].x + self._rng.uniform(-10, 10), route[0].y + self._rng.uniform(-10, 10)
            skill = min(1.0, tuning["skill"] + spec.difficulty * 0.25)
            rivals.append(RacerAI(f"rival_{i}", vehicle, route, skill=skill,
                                   aggression=tuning["aggression"], archetype=archetype,
                                   _rng=random.Random(self.config.seed + i + self.tick_count)))
        self.active_race = ActiveRace(spec=spec, rivals=rivals, route=route)
        logger.info("Event started: %s in %s (difficulty=%.2f, rivals=%d)",
                    spec.event_type.value, zone.display_name, spec.difficulty, len(rivals))

    def _finish_event(self, player_won: bool) -> None:
        race = self.active_race
        if race is None:
            return
        mult = self.sponsorships.reward_multiplier_for(race.spec.discipline)
        reward = int(race.spec.reward_credits * mult * (1.15 if player_won else 0.55))
        self.credits.earn(reward, reason=f"event:{race.spec.event_type.value}")
        rep_gain = race.spec.reward_reputation * (1.2 if player_won else 0.6)
        self.reputation.gain(race.spec.discipline, rep_gain)
        self.festival.award_influence(race.spec.zone_id, rep_gain * 2.5)
        self.style_model.observe_event_completed(race.spec.discipline, finished_well=player_won)
        self.crowd.pulse(0.35 if player_won else 0.15)
        self.events_completed += 1
        self.events_won += 1 if player_won else 0
        logger.info("Event finished: %s won=%s reward=%d rep+=%.1f",
                    race.spec.event_type.value, player_won, reward, rep_gain)
        self.active_race = None
        self._event_cooldown_s = self._rng.uniform(6.0, 18.0)
