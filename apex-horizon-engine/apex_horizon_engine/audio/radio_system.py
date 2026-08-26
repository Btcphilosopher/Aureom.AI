"""
In-car radio: a handful of stations with track rotations, plus DJ
commentary lines triggered by live game events (festival crowd hype,
event start/finish, drift scores, police heat) -- the "festival radio
broadcast" flavor called for in the brief, expressed as data (station,
track, line) rather than actual audio playback.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

STATIONS: Dict[str, List[str]] = {
    "Horizon FM": ["Neon Skyline", "Chrome Pulse", "Midnight Merge", "Voltage Drift"],
    "Apex Bass": ["Redline Theory", "Turbo Static", "Dry Lake Echo", "Overboost"],
    "Coastal Drive": ["Salt Air", "Bridgeline", "Low Tide Run", "Harbor Lights"],
}

_DJ_LINES: Dict[str, List[str]] = {
    "event_start": [
        "Lights out and away we go -- Horizon Festival, live!",
        "This grid is stacked. Let's see who's got the nerve tonight.",
    ],
    "event_finish_win": [
        "And that is how you put on a show! Absolutely dominant.",
        "Straight to the top of the leaderboard -- unreal drive.",
    ],
    "big_drift": [
        "That angle! That is a certified Horizon moment right there.",
        "Smoke everywhere -- the crowd is going wild for that slide!",
    ],
    "police_heat": [
        "We've got sirens closing in out there -- eyes up, driver.",
    ],
}


@dataclass
class RadioState:
    station: str = "Horizon FM"
    track_index: int = 0
    _rng: random.Random = field(default_factory=random.Random)

    def current_track(self) -> str:
        tracks = STATIONS[self.station]
        return tracks[self.track_index % len(tracks)]

    def next_track(self) -> str:
        self.track_index += 1
        return self.current_track()

    def switch_station(self, station: str) -> None:
        if station in STATIONS:
            self.station = station
            self.track_index = 0

    def dj_line(self, trigger: str) -> Optional[str]:
        lines = _DJ_LINES.get(trigger)
        if not lines:
            return None
        return self._rng.choice(lines)
