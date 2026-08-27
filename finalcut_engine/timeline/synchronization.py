"""Utilities for aligning clips: by embedded timecode, or by audio waveform.

Used directly for "connect clip at its recorded time-of-day" workflows, and
reused by :mod:`finalcut_engine.multicam.synchronizer` for multicam sync.
"""
from __future__ import annotations

from typing import Dict, Optional

import numpy as np

from finalcut_engine.core.timebase import Time, Timecode


def offset_between_timecodes(reference: Timecode, other: Timecode) -> Time:
    """How far ``other`` sits after ``reference`` on a shared wall-clock timeline."""
    return other.to_time() - reference.to_time()


def align_by_timecode(timecodes: Dict[str, Timecode]) -> Dict[str, Time]:
    """Map each id to its offset relative to the earliest timecode in the group."""
    if not timecodes:
        return {}
    earliest_id = min(timecodes, key=lambda k: timecodes[k].to_frame_index())
    reference = timecodes[earliest_id]
    return {key: offset_between_timecodes(reference, tc) for key, tc in timecodes.items()}


def synchronize_by_waveform(
    reference: np.ndarray, target: np.ndarray, sample_rate: int, max_offset_seconds: Optional[float] = None
) -> Time:
    """Find how far ``target`` audio is offset from ``reference`` via cross-correlation.

    A positive result means ``target`` starts *after* ``reference``. This is
    the standard clap-board-free multicam/audio-attachment sync technique:
    align on the audio waveforms rather than requiring matching timecode.
    """
    ref = reference.astype(np.float64)
    tgt = target.astype(np.float64)
    ref = ref - ref.mean()
    tgt = tgt - tgt.mean()

    correlation = np.correlate(tgt, ref, mode="full")
    lag = int(np.argmax(correlation) - (len(ref) - 1))

    if max_offset_seconds is not None:
        max_lag = int(max_offset_seconds * sample_rate)
        lag = max(-max_lag, min(max_lag, lag))

    return Time.from_seconds(lag / sample_rate)
