"""
Lightweight, dependency-free "ML-style" adaptation.

No external AI APIs, no gradient descent framework -- this is an online,
weighted, exponential-moving-average behavioural model plus a softmax
sampler, which is exactly the class of technique real racing games have
used for driver-style adaptation for two decades. It reads real telemetry
every tick (``vehicles.vehicle_model.TelemetrySample`` + a few event-level
signals) and slowly reshapes:

  * ``style_preferences()``      -> fed into ``world.event_generation``
    so the *kind* of events the world offers shifts toward what the
    player actually does.
  * ``rival_archetype_bias()``   -> fed into rival spawning so AI racer
    archetypes (drift-happy, highway-aggressive, technical, balanced)
    track the player's own style, creating rivals that feel like foils.

The whole model is a handful of floats in [0, 1] per dimension, updated
by a simple reinforcement-style rule: observations pull the weight toward
1.0 or 0.0 with a learning rate, then everything is renormalised. It is
intentionally legible and inspectable -- ``snapshot()`` returns the raw
numbers driving every downstream decision.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, Optional

STYLE_DIMENSIONS = ("drift", "street", "circuit", "offroad", "endurance")
LEARNING_RATE = 0.035
DECAY_TOWARD_NEUTRAL = 0.002  # slow drift back to neutral if a style goes unobserved


@dataclass
class PlayerStyleModel:
    """One instance per player/save. Cheap enough to update every tick."""

    weights: Dict[str, float] = field(default_factory=lambda: {k: 0.3 for k in STYLE_DIMENSIONS})
    braking_aggression: float = 0.4     # EMA of brake-pedal severity near corners
    cornering_aggression: float = 0.4   # EMA of lateral-g magnitude used
    top_speed_bias: float = 0.4         # EMA of time spent near a vehicle's redline/top speed
    off_road_usage: float = 0.1         # fraction of recent distance driven off-road
    sample_count: int = 0
    _rng: random.Random = field(default_factory=random.Random)

    # -- raw telemetry ingestion -------------------------------------------------
    def observe_tick(self, drift_phase: str, lat_accel_g: float, long_accel_g: float,
                      off_road: bool, near_top_speed: bool) -> None:
        self.sample_count += 1
        self._nudge_style("drift", 1.0 if drift_phase in ("drift", "transition") else 0.0)
        self.cornering_aggression = self._ema(self.cornering_aggression, min(1.0, abs(lat_accel_g) / 1.1))
        if long_accel_g < -0.15:
            self.braking_aggression = self._ema(self.braking_aggression, min(1.0, abs(long_accel_g) / 1.0))
        self.off_road_usage = self._ema(self.off_road_usage, 1.0 if off_road else 0.0)
        self._nudge_style("offroad", 1.0 if off_road else 0.0)
        self.top_speed_bias = self._ema(self.top_speed_bias, 1.0 if near_top_speed else 0.0)

    def observe_event_completed(self, discipline: str, finished_well: bool) -> None:
        """A bigger, event-level nudge -- finishing (and finishing well)
        in a discipline is a much stronger style signal than a single
        physics tick."""
        if discipline not in self.weights:
            return
        self._nudge_style(discipline, 1.0 if finished_well else 0.6, rate=LEARNING_RATE * 4)

    def decay_toward_neutral(self, dt_s: float) -> None:
        for key in self.weights:
            self.weights[key] += (0.3 - self.weights[key]) * min(1.0, DECAY_TOWARD_NEUTRAL * dt_s)

    def _nudge_style(self, key: str, target: float, rate: float = LEARNING_RATE) -> None:
        self.weights[key] = self._ema(self.weights[key], target, rate)
        self._renormalize_softly()

    @staticmethod
    def _ema(current: float, observation: float, rate: float = LEARNING_RATE) -> float:
        return current + (observation - current) * rate

    def _renormalize_softly(self) -> None:
        # Keep weights bounded in [0, 1] without forcing them to sum to 1
        # (multiple styles can be simultaneously "high" for a versatile
        # player) -- just clamp.
        for key in self.weights:
            self.weights[key] = max(0.0, min(1.0, self.weights[key]))

    # -- downstream consumers ----------------------------------------------------
    def style_preferences(self) -> Dict[str, float]:
        return dict(self.weights)

    def dominant_style(self) -> str:
        return max(self.weights, key=self.weights.get)

    def rival_archetype_bias(self) -> Dict[str, float]:
        """Softmax over a small set of AI archetypes, driven by the same
        weights -- this is what makes the world "generate more drift
        rivals" for a drift-focused player, per the design brief."""
        raw = {
            "drift_focused": self.weights["drift"] * 1.4,
            "highway_aggressive": (self.weights["street"] + self.top_speed_bias) * 0.8,
            "technical": (self.weights["circuit"] + self.cornering_aggression) * 0.8,
            "rally_specialist": self.weights["offroad"] * 1.3,
            "balanced": 0.35,
        }
        return _softmax(raw)

    def snapshot(self) -> Dict[str, float]:
        return {
            **{f"style_{k}": v for k, v in self.weights.items()},
            "braking_aggression": self.braking_aggression,
            "cornering_aggression": self.cornering_aggression,
            "top_speed_bias": self.top_speed_bias,
            "off_road_usage": self.off_road_usage,
            "samples": float(self.sample_count),
        }

    def sample_archetype(self) -> str:
        """Reinforcement-style probability draw -- callers that need to
        pick *one* archetype (e.g. spawning a single new rival) sample
        from the softmax distribution rather than always taking the max,
        so the rival pool stays varied instead of homogenizing."""
        biases = self.rival_archetype_bias()
        keys = list(biases.keys())
        weights = list(biases.values())
        return self._rng.choices(keys, weights=weights, k=1)[0]


def _softmax(raw: Dict[str, float], temperature: float = 0.6) -> Dict[str, float]:
    keys = list(raw.keys())
    values = [raw[k] / max(1e-6, temperature) for k in keys]
    m = max(values)
    exps = [math.exp(v - m) for v in values]
    total = sum(exps) or 1.0
    return {k: e / total for k, e in zip(keys, exps)}
