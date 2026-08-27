from __future__ import annotations

import numpy as np

from finalcut_engine.audio.compressor import Compressor
from finalcut_engine.audio.equalizer import EQBand, Equalizer, FilterType
from finalcut_engine.audio.limiter import Limiter
from finalcut_engine.audio.mixer import AudioGraph
from finalcut_engine.audio.noise_reduction import NoiseReducer
from finalcut_engine.audio.track import AudioTrack
from finalcut_engine.core.timebase import Time

SR = 48000


def test_limiter_never_exceeds_ceiling():
    rng = np.random.default_rng(1)
    loud = (3.0 * rng.standard_normal(SR)).astype(np.float32)
    limiter = Limiter(ceiling_db=-1.0)
    out = limiter.process(loud, SR)
    ceiling = 10 ** (-1.0 / 20)
    assert np.abs(out).max() <= ceiling + 1e-6


def test_compressor_reduces_dynamic_range():
    rng = np.random.default_rng(2)
    quiet = 0.05 * rng.standard_normal(SR).astype(np.float32)
    loud = 0.8 * rng.standard_normal(SR).astype(np.float32)
    signal = np.concatenate([quiet, loud])
    comp = Compressor(threshold_db=-20, ratio=4.0, attack_ms=5, release_ms=50)
    out = comp.process(signal, SR)

    def rms(x):
        return np.sqrt(np.mean(x.astype(np.float64) ** 2))

    # Compare steady-state RMS per section rather than the whole buffer's
    # crest factor: a brief attack-time overshoot right at the loud section's
    # onset is expected compressor behaviour and would make a naive
    # whole-buffer crest-factor check flaky.
    input_ratio = rms(loud) / rms(quiet)
    output_ratio = rms(out[SR:]) / rms(out[:SR])
    assert output_ratio < input_ratio
    # The quiet section (well below threshold) should be essentially untouched.
    assert abs(rms(out[:SR]) - rms(quiet)) / rms(quiet) < 0.05


def test_equalizer_high_pass_removes_low_frequency_energy():
    t = np.arange(SR) / SR
    low_tone = np.sin(2 * np.pi * 50 * t).astype(np.float32)
    eq = Equalizer().add_band(EQBand(FilterType.HIGH_PASS, freq_hz=500, q=0.707))
    out = eq.process(low_tone, SR)
    assert np.sqrt(np.mean(out[2000:] ** 2)) < 0.3 * np.sqrt(np.mean(low_tone[2000:] ** 2))


def test_noise_reduction_lowers_noise_floor_without_blowing_up():
    rng = np.random.default_rng(3)
    noise_a = 0.05 * rng.standard_normal(SR).astype(np.float32)
    noise_b = 0.05 * rng.standard_normal(SR).astype(np.float32)
    reducer = NoiseReducer()
    profile = reducer.learn_noise_profile(noise_a)
    cleaned = reducer.process(noise_b, profile)

    assert len(cleaned) == len(noise_b)
    assert np.abs(cleaned).max() < 1.0  # regression guard for the STFT edge blow-up
    assert np.sqrt(np.mean(cleaned.astype(np.float64) ** 2)) < np.sqrt(np.mean(noise_b.astype(np.float64) ** 2))


def test_audio_graph_mix_respects_mute_and_ceiling():
    graph = AudioGraph()
    loud_track = AudioTrack("Loud")
    quiet_track = AudioTrack("Muted", muted=True)
    graph.add_track(loud_track)
    graph.add_track(quiet_track)

    rng = np.random.default_rng(4)
    loud_samples = (2.0 * rng.standard_normal(SR)).astype(np.float32)
    quiet_samples = (2.0 * rng.standard_normal(SR)).astype(np.float32)

    processed = {
        "Loud": graph.process_channel("Loud", loud_samples, SR, Time.zero()),
        "Muted": graph.process_channel("Muted", quiet_samples, SR, Time.zero()),
    }
    mix = graph.mix(processed, SR)
    assert np.abs(mix).max() <= 10 ** (graph.master_limiter.ceiling_db / 20) + 1e-6

    # The muted track should contribute nothing: mixing without it must be identical.
    mix_without_muted = graph.mix({"Loud": processed["Loud"]}, SR)
    assert np.allclose(mix, mix_without_muted)
