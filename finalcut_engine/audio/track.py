"""Audio track / channel-strip model: volume automation, pan, fades, mute/solo."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import numpy as np

from finalcut_engine.core.timebase import Time
from finalcut_engine.timeline.roles import DEFAULT_DIALOGUE_ROLE, Role


@dataclass(frozen=True)
class VolumeKeyframe:
    time: Time
    gain_db: float


@dataclass
class AudioTrack:
    name: str
    role: Role = field(default_factory=lambda: DEFAULT_DIALOGUE_ROLE)
    volume_automation: List[VolumeKeyframe] = field(default_factory=list)
    pan: float = 0.0  # -1 (left) .. +1 (right)
    muted: bool = False
    solo: bool = False
    fade_in: Time = field(default_factory=Time.zero)
    fade_out: Time = field(default_factory=Time.zero)

    def add_keyframe(self, t: Time, gain_db: float) -> None:
        self.volume_automation = sorted(
            [kf for kf in self.volume_automation if kf.time != t] + [VolumeKeyframe(t, gain_db)],
            key=lambda kf: kf.time.seconds(),
        )

    def gain_at(self, t: Time) -> float:
        """Linear (in dB) interpolation between the surrounding keyframes."""
        if not self.volume_automation:
            return 0.0
        kfs = self.volume_automation
        if t.seconds() <= kfs[0].time.seconds():
            return kfs[0].gain_db
        if t.seconds() >= kfs[-1].time.seconds():
            return kfs[-1].gain_db
        for a, b in zip(kfs, kfs[1:]):
            if a.time.seconds() <= t.seconds() <= b.time.seconds():
                span = b.time.seconds() - a.time.seconds()
                frac = 0.0 if span == 0 else (t.seconds() - a.time.seconds()) / span
                return a.gain_db + frac * (b.gain_db - a.gain_db)
        return kfs[-1].gain_db

    def gain_envelope(self, sample_rate: int, n_samples: int, start_time: Time) -> np.ndarray:
        """A per-sample linear-gain envelope covering ``[start_time, start_time + n_samples/sr)``."""
        times = start_time.seconds() + np.arange(n_samples) / sample_rate
        db = np.array([self.gain_at(Time.from_seconds(float(t))) for t in times[:: max(1, n_samples // 256) or 1]])
        # Interpolate a coarse sampling back up to full resolution for speed on long buffers.
        coarse_idx = np.linspace(0, n_samples - 1, num=len(db))
        db_full = np.interp(np.arange(n_samples), coarse_idx, db)
        db_full = self._apply_fade_curves(db_full, sample_rate, n_samples)
        return np.power(10.0, db_full / 20.0)

    def _apply_fade_curves(self, db: np.ndarray, sample_rate: int, n_samples: int) -> np.ndarray:
        out = db.copy()
        fi = int(self.fade_in.seconds() * sample_rate)
        fo = int(self.fade_out.seconds() * sample_rate)
        if fi > 0:
            fi = min(fi, n_samples)
            atten = np.linspace(-60.0, 0.0, fi)
            out[:fi] = np.minimum(out[:fi], atten)
        if fo > 0:
            fo = min(fo, n_samples)
            atten = np.linspace(0.0, -60.0, fo)
            out[-fo:] = np.minimum(out[-fo:], atten)
        return out
