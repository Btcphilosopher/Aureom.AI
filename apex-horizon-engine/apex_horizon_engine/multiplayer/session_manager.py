"""
Local session management: tracks the set of active player slots (human
or bot-controlled) sharing one simulation -- the substrate for local
multiplayer, AI convoy races, and split-session testing. Networking
itself (state diffing/serialization) lives in ``multiplayer.sync_system``;
this module only owns *who* is playing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from apex_horizon_engine.vehicles.vehicle_model import Vehicle, VehicleControls


@dataclass
class PlayerSession:
    session_id: str
    display_name: str
    vehicle: Vehicle
    is_local_human: bool = True
    controls_provider: Optional[Callable[[], VehicleControls]] = None
    connected: bool = True

    def poll_controls(self) -> VehicleControls:
        if self.controls_provider is not None:
            return self.controls_provider()
        return VehicleControls()


@dataclass
class SessionManager:
    sessions: Dict[str, PlayerSession] = field(default_factory=dict)
    _next_id: int = 0

    def add_session(self, display_name: str, vehicle: Vehicle, is_local_human: bool = True,
                     controls_provider: Optional[Callable[[], VehicleControls]] = None) -> PlayerSession:
        session_id = f"session_{self._next_id}"
        self._next_id += 1
        session = PlayerSession(session_id, display_name, vehicle, is_local_human, controls_provider)
        self.sessions[session_id] = session
        return session

    def remove_session(self, session_id: str) -> None:
        self.sessions.pop(session_id, None)

    def set_connected(self, session_id: str, connected: bool) -> None:
        if session_id in self.sessions:
            self.sessions[session_id].connected = connected

    def active_sessions(self) -> List[PlayerSession]:
        return [s for s in self.sessions.values() if s.connected]

    def local_human_sessions(self) -> List[PlayerSession]:
        return [s for s in self.active_sessions() if s.is_local_human]
