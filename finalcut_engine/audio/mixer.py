"""The audio graph: SOURCE -> GAIN -> EQ -> COMPRESSOR -> EFFECTS -> LIMITER -> MASTER.

Each :class:`AudioTrack` is one channel strip; :class:`AudioMixer` sums the
processed channels onto a master bus, with mute/solo logic, and a final
master limiter to guarantee the mix never clips.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import numpy as np

from finalcut_engine.audio.compressor import Compressor
from finalcut_engine.audio.equalizer import Equalizer
from finalcut_engine.audio.limiter import Limiter
from finalcut_engine.audio.track import AudioTrack
from finalcut_engine.core.timebase import Time

#: An effect is any callable ``(samples, sample_rate) -> samples`` (noise reduction,
#: reverb, de-esser, ...). Left duck-typed so the audio graph has no hard
#: dependency on any specific effect implementation.
AudioEffect = Callable[[np.ndarray, int], np.ndarray]


@dataclass
class ChannelStrip:
    track: AudioTrack
    eq: Optional[Equalizer] = None
    compressor: Optional[Compressor] = None
    effects: List[AudioEffect] = field(default_factory=list)


@dataclass
class AudioGraph:
    strips: Dict[str, ChannelStrip] = field(default_factory=dict)
    master_limiter: Limiter = field(default_factory=lambda: Limiter(ceiling_db=-0.1))

    def add_track(self, track: AudioTrack, eq: Optional[Equalizer] = None, compressor: Optional[Compressor] = None) -> ChannelStrip:
        strip = ChannelStrip(track=track, eq=eq, compressor=compressor)
        self.strips[track.name] = strip
        return strip

    def process_channel(self, name: str, samples: np.ndarray, sample_rate: int, start_time: Time) -> np.ndarray:
        """Run one channel strip's full SOURCE -> ... -> pre-master chain."""
        strip = self.strips[name]
        track = strip.track
        out = samples.astype(np.float64)

        # GAIN (clip-level automation + per-clip trim already baked in by caller,
        # this stage applies the track/channel-strip level automation).
        envelope = track.gain_envelope(sample_rate, len(out), start_time)
        out = out * envelope

        # EQ
        if strip.eq is not None:
            out = strip.eq.process(out, sample_rate)

        # COMPRESSOR
        if strip.compressor is not None:
            out = strip.compressor.process(out, sample_rate)

        # EFFECTS
        for effect in strip.effects:
            out = effect(out, sample_rate)

        # Pan (simple equal-power pan law), producing a stereo pair as (n, 2).
        if out.ndim == 1:
            angle = (track.pan + 1) * (np.pi / 4)
            left, right = np.cos(angle), np.sin(angle)
            out = np.stack([out * left, out * right], axis=1)

        return out.astype(np.float64)

    def mix(self, processed_channels: Dict[str, np.ndarray], sample_rate: int) -> np.ndarray:
        """Sum channels onto the master bus honouring mute/solo, then limit."""
        any_solo = any(strip.track.solo for strip in self.strips.values())
        max_len = max((len(buf) for buf in processed_channels.values()), default=0)
        master = np.zeros((max_len, 2), dtype=np.float64)

        for name, buf in processed_channels.items():
            strip = self.strips.get(name)
            if strip is None:
                continue
            track = strip.track
            audible = (not track.muted) and (track.solo or not any_solo)
            if not audible:
                continue
            master[: len(buf)] += buf

        flat = master.reshape(-1)
        limited = self.master_limiter.process(flat, sample_rate)
        return limited.reshape(master.shape)
