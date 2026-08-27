from __future__ import annotations

import numpy as np

from finalcut_engine.core.timebase import Time, TimeRange
from finalcut_engine.multicam.angle_switching import AngleSwitcher
from finalcut_engine.multicam.camera_angle import CameraAngle
from finalcut_engine.multicam.multicam_clip import MulticamClip
from finalcut_engine.multicam.synchronizer import MulticamSynchronizer


def test_waveform_sync_recovers_known_offset():
    rng = np.random.default_rng(0)
    sr = 48000
    base = rng.uniform(-1, 1, sr * 4).astype(np.float32)
    shifted = np.concatenate([np.zeros(int(0.4 * sr), dtype=np.float32), base])[: len(base)]

    result = MulticamSynchronizer().sync_by_waveform({"A": base, "B": shifted}, sr)
    assert result.offsets["A"].seconds() == 0.0
    assert abs(result.offsets["B"].seconds() - 0.4) < 1e-3


def test_multicam_clip_duration_is_the_overlapping_window():
    angles = {
        "A": CameraAngle("A", "a", Time.zero(), TimeRange(Time.zero(), Time.from_seconds(10))),
        "B": CameraAngle("B", "b", Time.from_seconds(2), TimeRange(Time.zero(), Time.from_seconds(10))),
    }
    clip = MulticamClip("MC", angles, AngleSwitcher(default_angle="A"))
    # A covers [0,10], B covers [2,12] -> overlap is [2,10] = 8s
    assert clip.duration.seconds() == 8.0


def test_angle_switching_and_flatten_produce_correct_cuts():
    angles = {
        "A": CameraAngle("A", "assetA", Time.zero(), TimeRange(Time.zero(), Time.from_seconds(10))),
        "B": CameraAngle("B", "assetB", Time.from_seconds(1), TimeRange(Time.zero(), Time.from_seconds(10))),
    }
    clip = MulticamClip("MC", angles, AngleSwitcher(default_angle="A"))
    clip.switch_angle(Time.from_seconds(3), "B")
    clip.switch_angle(Time.from_seconds(6), "A")

    flat = clip.flatten()
    assert [i.name.split(":")[1] for i in flat.items] == ["A", "B", "A"]
    total = sum(i.duration.seconds() for i in flat.items)
    assert abs(total - clip.duration.seconds()) < 1e-9
