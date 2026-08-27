"""Spectral-gating noise reduction (a numpy-only STFT noise gate).

Learns a noise magnitude profile from a noise-only reference segment (e.g. a
room-tone selection) and attenuates frequency bins in the target audio that
sit close to that noise floor — the same basic technique behind classic
"noise print" denoisers, simplified to run without extra DSP dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def _stft(x: np.ndarray, frame_size: int, hop: int) -> np.ndarray:
    window = np.hanning(frame_size)
    n_frames = 1 + max(0, (len(x) - frame_size) // hop)
    frames = np.stack([x[i * hop : i * hop + frame_size] * window for i in range(n_frames)])
    return np.fft.rfft(frames, axis=1)


def _istft(spectrum: np.ndarray, frame_size: int, hop: int, length: int) -> np.ndarray:
    window = np.hanning(frame_size)
    frames = np.fft.irfft(spectrum, n=frame_size, axis=1)
    out = np.zeros(length + frame_size, dtype=np.float64)
    norm = np.zeros_like(out)
    for i in range(frames.shape[0]):
        start = i * hop
        out[start : start + frame_size] += frames[i] * window
        norm[start : start + frame_size] += window**2
    norm[norm < 1e-8] = 1.0
    return (out / norm)[:length]


@dataclass
class NoiseReducer:
    frame_size: int = 2048
    hop: int = 512
    reduction_db: float = -18.0  # how much to attenuate bins identified as noise
    sensitivity: float = 1.5  # multiplier over the learned noise floor

    def learn_noise_profile(self, noise_samples: np.ndarray) -> np.ndarray:
        spectrum = _stft(noise_samples.astype(np.float64), self.frame_size, self.hop)
        magnitude = np.abs(spectrum)
        return magnitude.mean(axis=0)  # average noise magnitude per frequency bin

    def process(self, samples: np.ndarray, noise_profile: np.ndarray) -> np.ndarray:
        # Once the spectrum is modified per-bin, the overlap-add reconstruction
        # near the very edges divides a near-zero numerator by a near-zero
        # window-normalisation term (only one frame's tapered edge covers those
        # samples), which is numerically unstable. Padding by a full frame on
        # each side guarantees every real sample has full multi-frame overlap
        # coverage; the padding is then trimmed back off.
        pad = self.frame_size
        x = np.concatenate([np.zeros(pad), samples.astype(np.float64), np.zeros(pad)])

        spectrum = _stft(x, self.frame_size, self.hop)
        magnitude = np.abs(spectrum)
        phase = np.angle(spectrum)

        noise_gate = magnitude < (noise_profile[np.newaxis, :] * self.sensitivity)
        attenuation = 10 ** (self.reduction_db / 20.0)
        gain = np.where(noise_gate, attenuation, 1.0)

        cleaned_magnitude = magnitude * gain
        cleaned_spectrum = cleaned_magnitude * np.exp(1j * phase)
        result = _istft(cleaned_spectrum, self.frame_size, self.hop, len(x))
        result = result[pad : pad + len(samples)]
        return result.astype(samples.dtype)
