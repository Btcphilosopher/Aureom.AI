from __future__ import annotations

import pytest

from finalcut_engine.core.timebase import Time
from finalcut_engine.timeline.magnetic_timeline import MagneticTimeline
from finalcut_engine.timeline.storyline import StorylineError
from finalcut_engine.timeline.transitions import Transition


def test_positions_are_derived_and_ripple_automatically(make_clip):
    tl = MagneticTimeline()
    a, b, c, d = (make_clip(n, d) for n, d in [("A", 4), ("B", 3), ("C", 5), ("D", 2)])
    for clip in (a, b, c, d):
        tl.append_clip(clip)

    assert [tl.primary.item_start(x.id).seconds() for x in (a, b, c, d)] == [0.0, 4.0, 7.0, 12.0]
    assert tl.duration.seconds() == 14.0

    tl.ripple_trim(b.id, Time.from_seconds(1.0))
    assert [tl.primary.item_start(x.id).seconds() for x in (a, b, c, d)] == [0.0, 4.0, 5.0, 10.0]
    assert tl.duration.seconds() == 12.0


def test_connected_clip_stays_attached_to_anchor_through_ripple(make_clip):
    tl = MagneticTimeline()
    a, b, c = (make_clip(n, 3) for n in "ABC")
    for clip in (a, b, c):
        tl.append_clip(clip)
    broll = make_clip("broll", 1.0)
    connected = tl.connect_clip(b.id, broll, Time.from_seconds(0.5), lane=1)

    before = tl.absolute_position_of_connected(connected.id)
    tl.ripple_trim(a.id, Time.from_seconds(5.0))  # A grows, pushing B later
    after = tl.absolute_position_of_connected(connected.id)

    # B moved by +2s (5 - 3); the connected clip, anchored to B at a fixed
    # offset, should have moved by exactly the same amount.
    assert abs((after - before).seconds() - 2.0) < 1e-9


def test_connected_clip_offset_clamps_to_shrunk_anchor_duration(make_clip):
    tl = MagneticTimeline()
    a, b = make_clip("A", 3), make_clip("B", 3)
    tl.append_clip(a)
    tl.append_clip(b)
    broll = make_clip("broll", 1.0)
    connected = tl.connect_clip(b.id, broll, Time.from_seconds(2.5), lane=1)

    tl.ripple_trim(b.id, Time.from_seconds(1.0))  # B shrinks below the 2.5s offset
    abs_pos = tl.absolute_position_of_connected(connected.id)
    b_start = tl.primary.item_start(b.id)
    assert abs((abs_pos - b_start).seconds() - 1.0) < 1e-9  # clamped to B's new duration


def test_roll_trim_preserves_total_duration(make_clip):
    tl = MagneticTimeline()
    a, b = make_clip("A", 4), make_clip("B", 3)
    tl.append_clip(a)
    tl.append_clip(b)
    tl.trim_clip(a.id, Time.from_seconds(1.0))

    assert tl.duration.seconds() == 7.0
    assert tl.primary.get(a.id).duration.seconds() == 5.0
    assert tl.primary.get(b.id).duration.seconds() == 2.0


def test_ripple_delete_reanchors_orphaned_connected_clips(make_clip):
    tl = MagneticTimeline()
    a, b, c = (make_clip(n, 2) for n in "ABC")
    for clip in (a, b, c):
        tl.append_clip(clip)
    connected = tl.connect_clip(b.id, make_clip("broll", 1), Time.zero())

    tl.delete_clip(b.id, ripple=True)

    assert tl.connected[connected.id].anchor_item_id == a.id
    assert tl.duration.seconds() == 4.0


def test_lift_delete_preserves_positions_via_gap(make_clip):
    tl = MagneticTimeline()
    a, b, c = (make_clip(n, 2) for n in "ABC")
    for clip in (a, b, c):
        tl.append_clip(clip)

    tl.delete_clip(b.id, ripple=False)
    assert tl.duration.seconds() == 6.0  # unchanged: B became a same-length Gap
    assert tl.primary.item_start(c.id).seconds() == 4.0  # C didn't move


def test_compound_clip_groups_contiguous_items_and_tracks_nested_duration(make_clip):
    tl = MagneticTimeline()
    clips = [make_clip(n, 2) for n in "ABCD"]
    for clip in clips:
        tl.append_clip(clip)

    compound = tl.create_compound_clip([clips[1].id, clips[2].id], name="BC")
    assert [type(i).__name__ for i in tl.primary.items] == ["Clip", "CompoundClip", "Clip"]
    assert compound.duration.seconds() == 4.0

    compound.nested.ripple_trim(clips[1].id, Time.from_seconds(5.0))
    assert compound.duration.seconds() == 7.0  # outer duration tracks the nested edit


def test_compound_clip_requires_contiguous_items(make_clip):
    tl = MagneticTimeline()
    clips = [make_clip(n, 2) for n in "ABCD"]
    for clip in clips:
        tl.append_clip(clip)
    with pytest.raises(StorylineError):
        tl.create_compound_clip([clips[0].id, clips[2].id])


def test_transition_preserves_total_duration_and_crossfades(make_clip):
    tl = MagneticTimeline()
    x, y = make_clip("X", 3), make_clip("Y", 3)
    tl.append_clip(x)
    tl.append_clip(y)
    transition = tl.add_transition(x.id, Time.from_seconds(1.0))

    assert tl.duration.seconds() == 6.0
    kinds = [type(i).__name__ for i in tl.primary.items]
    assert kinds == ["Clip", "Transition", "Clip"]
    assert isinstance(tl.primary.get(transition.id), Transition)


def test_move_clip_reorders_without_changing_total_duration(make_clip):
    tl = MagneticTimeline()
    a, b, c = (make_clip(n, 2) for n in "ABC")
    for clip in (a, b, c):
        tl.append_clip(clip)
    tl.move_clip(c.id, 0)
    assert [i.name for i in tl.primary.items] == ["C", "A", "B"]
    assert tl.duration.seconds() == 6.0


def test_replace_clip_fits_longer_replacement_without_rippling(make_clip):
    tl = MagneticTimeline()
    a = make_clip("A", 3)
    tl.append_clip(a)
    replacement = make_clip("A2", 10)  # much longer source
    tl.replace_clip(a.id, replacement)
    assert tl.duration.seconds() == 3.0  # fitted to the old duration


def test_split_clip_produces_two_contiguous_clips_with_same_total_duration(make_clip):
    tl = MagneticTimeline()
    a = make_clip("A", 4)
    tl.append_clip(a)
    left, right = tl.primary.split_clip(a.id, Time.from_seconds(1.5))
    assert abs(left.duration.seconds() - 1.5) < 1e-9
    assert abs(right.duration.seconds() - 2.5) < 1e-9
    assert tl.duration.seconds() == 4.0
