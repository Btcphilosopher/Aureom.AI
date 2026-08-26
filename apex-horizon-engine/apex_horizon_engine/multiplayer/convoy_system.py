"""
Convoy system: a group of vehicles (human sessions and/or AI) travelling
together with loose formation-keeping, and a shared "convoy cohesion"
score that rewards staying together over a long drive -- the mechanism
behind the brief's "AI convoy races" game mode.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Tuple

from apex_horizon_engine.multiplayer.session_manager import PlayerSession

FORMATION_OFFSETS_M: List[Tuple[float, float]] = [
    (0.0, 0.0), (-12.0, -4.0), (-12.0, 4.0), (-24.0, -4.0), (-24.0, 4.0), (-36.0, 0.0),
]
COHESION_RADIUS_M = 90.0


@dataclass
class ConvoyGroup:
    convoy_id: str
    member_session_ids: List[str] = field(default_factory=list)
    leader_session_id: str = ""
    cohesion_score: float = 0.0
    _time_together_s: float = 0.0

    def set_leader(self, session_id: str) -> None:
        self.leader_session_id = session_id
        if session_id not in self.member_session_ids:
            self.member_session_ids.insert(0, session_id)

    def add_member(self, session_id: str) -> None:
        if session_id not in self.member_session_ids:
            self.member_session_ids.append(session_id)

    def formation_target(self, member_index: int, leader: PlayerSession) -> Tuple[float, float]:
        """World-space target position for a convoy member, offset behind
        the leader in the leader's heading frame."""
        idx = min(member_index, len(FORMATION_OFFSETS_M) - 1)
        ox, oy = FORMATION_OFFSETS_M[idx]
        heading = leader.vehicle.state.heading_rad
        wx = leader.vehicle.state.x + ox * math.cos(heading) - oy * math.sin(heading)
        wy = leader.vehicle.state.y + ox * math.sin(heading) + oy * math.cos(heading)
        return wx, wy

    def update_cohesion(self, dt: float, sessions_by_id: dict) -> None:
        leader = sessions_by_id.get(self.leader_session_id)
        if leader is None or len(self.member_session_ids) < 2:
            return
        distances = []
        for sid in self.member_session_ids:
            if sid == self.leader_session_id:
                continue
            member = sessions_by_id.get(sid)
            if member is None:
                continue
            dist = math.hypot(member.vehicle.state.x - leader.vehicle.state.x,
                               member.vehicle.state.y - leader.vehicle.state.y)
            distances.append(dist)
        if not distances:
            return
        all_together = all(d <= COHESION_RADIUS_M for d in distances)
        if all_together:
            self._time_together_s += dt
            self.cohesion_score = min(100.0, self.cohesion_score + dt * 1.5)
        else:
            self._time_together_s = 0.0
            self.cohesion_score = max(0.0, self.cohesion_score - dt * 3.0)

    @property
    def bonus_multiplier(self) -> float:
        """Reward multiplier applied to convoy-mode event payouts --
        scales with sustained cohesion, capped at a healthy but not
        game-breaking +40%."""
        return 1.0 + min(0.4, self.cohesion_score / 250.0)
