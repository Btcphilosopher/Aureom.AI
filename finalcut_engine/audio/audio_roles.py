"""Audio role buses: Dialogue / Music / Effects / Ambience (spec section 9)."""
from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Dict, Iterable, List

from finalcut_engine.timeline.roles import AudioRole, Role

if TYPE_CHECKING:
    from finalcut_engine.audio.track import AudioTrack


def group_tracks_by_role(tracks: Iterable["AudioTrack"]) -> Dict[str, List["AudioTrack"]]:
    groups: Dict[str, List["AudioTrack"]] = defaultdict(list)
    for track in tracks:
        groups[track.role.name].append(track)
    return dict(groups)


#: The four standard buses every mix starts with.
STANDARD_BUSES = [Role(AudioRole.DIALOGUE.value), Role(AudioRole.MUSIC.value), Role(AudioRole.EFFECTS.value), Role(AudioRole.AMBIENCE.value)]
