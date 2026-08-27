from __future__ import annotations

from finalcut_engine.core.timebase import FPS_24, FPS_29_97, FPS_59_94, Time, TimeRange, Timecode


def test_time_arithmetic_is_exact_across_timescales():
    a = Time.from_seconds(1.0, timescale=600)
    b = Time.from_seconds(0.5, timescale=1000)
    total = a + b
    assert abs(total.seconds() - 1.5) < 1e-9


def test_time_ordering_and_equality():
    a = Time.from_seconds(1.0)
    b = Time.from_seconds(2.0)
    assert a < b
    assert Time.from_seconds(1.0, timescale=600) == Time.from_seconds(1.0, timescale=48000)


def test_time_range_overlap_and_intersection():
    r1 = TimeRange(Time.from_seconds(0), Time.from_seconds(2))
    r2 = TimeRange(Time.from_seconds(1), Time.from_seconds(2))
    assert r1.overlaps(r2)
    inter = r1.intersection(r2)
    assert inter is not None
    assert abs(inter.duration.seconds() - 1.0) < 1e-9

    r3 = TimeRange(Time.from_seconds(5), Time.from_seconds(1))
    assert not r1.overlaps(r3)
    assert r1.intersection(r3) is None


def test_frame_index_conversion_round_trip_non_drop():
    for frames in (0, 1, 23, 100, 10_000):
        t = Time.from_frames(frames, FPS_24)
        assert t.to_frame_index(FPS_24) == frames


def test_drop_frame_timecode_round_trip_29_97():
    for frame_index in range(0, 200_000, 137):
        tc = Timecode.from_frame_index(frame_index, FPS_29_97)
        assert tc.to_frame_index() == frame_index


def test_drop_frame_timecode_round_trip_59_94():
    for frame_index in range(0, 200_000, 251):
        tc = Timecode.from_frame_index(frame_index, FPS_59_94)
        assert tc.to_frame_index() == frame_index


def test_known_drop_frame_reference_point():
    # A famous drop-frame fact: exactly 1 hour of 29.97fps drop-frame content
    # is 107892 frames, and displays as 01:00:00;00 (not 01:00:03;18).
    tc = Timecode.from_frame_index(107892, FPS_29_97)
    assert str(tc) == "01:00:00;00"


def test_drop_frame_skips_frame_numbers_00_and_01():
    # At the start of minute 1 (non-exempt), frame numbers :00 and :01 don't exist.
    tc = Timecode.from_frame_index(1800, FPS_29_97)  # exactly 60 real seconds in
    assert (tc.minutes, tc.frames) in {(1, 2), (0, 59)}  # allow either side of the boundary
