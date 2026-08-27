"""Computes per-angle sync offsets for a multicam group.

Supports the three methods listed in spec section 8: matching embedded
timecode, cross-correlating scratch audio, and accepting manually defined
sync points (e.g. a user-marked clap).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np

from finalcut_engine.core.timebase import Time, Timecode
from finalcut_engine.timeline.synchronization import align_by_timecode, synchronize_by_waveform


@dataclass
class SyncResult:
    offsets: Dict[str, Time]  # angle name -> offset from the earliest angle
    method: str


class MulticamSynchronizer:
    def sync_by_timecode(self, timecodes: Dict[str, Timecode]) -> SyncResult:
        return SyncResult(offsets=align_by_timecode(timecodes), method="timecode")

    def sync_by_waveform(
        self, audio_by_angle: Dict[str, np.ndarray], sample_rate: int, reference: str | None = None
    ) -> SyncResult:
        names = list(audio_by_angle)
        if not names:
            return SyncResult(offsets={}, method="waveform")
        ref_name = reference or names[0]
        ref_audio = audio_by_angle[ref_name]
        offsets: Dict[str, Time] = {ref_name: Time.zero()}
        for name in names:
            if name == ref_name:
                continue
            offsets[name] = synchronize_by_waveform(ref_audio, audio_by_angle[name], sample_rate)
        # Normalise so the earliest angle sits at zero (matches sync_by_timecode's convention).
        earliest = min(offsets.values(), key=lambda t: t.seconds())
        offsets = {name: off - earliest for name, off in offsets.items()}
        return SyncResult(offsets=offsets, method="waveform")

    def sync_manual(self, sync_points: Dict[str, Time]) -> SyncResult:
        earliest = min(sync_points.values(), key=lambda t: t.seconds())
        return SyncResult(offsets={name: t - earliest for name, t in sync_points.items()}, method="manual")
