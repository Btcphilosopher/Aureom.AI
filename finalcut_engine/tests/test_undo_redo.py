from __future__ import annotations

import numpy as np

from finalcut_engine.api.engine_api import EngineAPI
from finalcut_engine.core.engine import FinalCutEngine
from finalcut_engine.core.state import Command, UndoManager
from finalcut_engine.core.timebase import Time, TimeRange
from finalcut_engine.effects.blur import GaussianBlurEffect
from finalcut_engine.timeline.clip import Clip


def _loader(asset_id, t):
    return np.zeros((4, 4, 3))


def test_basic_command_undo_redo():
    class Counter:
        value = 0

    class IncrementCommand(Command):
        label = "Increment"

        def do(self):
            Counter.value += 1

        def undo(self):
            Counter.value -= 1

    manager = UndoManager()
    manager.execute(IncrementCommand())
    manager.execute(IncrementCommand())
    assert Counter.value == 2
    manager.undo()
    assert Counter.value == 1
    manager.redo()
    assert Counter.value == 2


def test_undo_manager_batches_commands_as_one_step():
    class Counter:
        value = 0

    class IncrementCommand(Command):
        label = "Increment"

        def do(self):
            Counter.value += 1

        def undo(self):
            Counter.value -= 1

    manager = UndoManager()
    with manager.batch("Add three"):
        for _ in range(3):
            manager.execute(IncrementCommand())
    assert Counter.value == 3
    manager.undo()
    assert Counter.value == 0  # the whole batch reverses in one undo


def test_undo_manager_respects_max_history():
    class NoOpCommand(Command):
        label = "noop"

        def do(self):
            pass

        def undo(self):
            pass

    manager = UndoManager(max_history=2)
    for _ in range(5):
        manager.execute(NoOpCommand())
    assert len(manager.history_labels()) == 2


def test_engine_api_ripple_trim_undo_redo_round_trips_timeline_state():
    engine = FinalCutEngine.new("Lib", _loader)
    api = EngineAPI(engine)
    project = engine.create_project("P")
    tl = project.create_timeline("T")

    a = api.append_clip(tl, Clip(asset_id="A", source_range=TimeRange(Time.zero(), Time.from_seconds(3))))
    api.append_clip(tl, Clip(asset_id="B", source_range=TimeRange(Time.zero(), Time.from_seconds(2))))
    assert tl.duration.seconds() == 5.0

    api.ripple_trim(tl, a.id, Time.from_seconds(1.0))
    assert tl.duration.seconds() == 3.0

    api.undo()
    assert tl.duration.seconds() == 5.0
    api.redo()
    assert tl.duration.seconds() == 3.0
    engine.shutdown()


def test_apply_effect_command_is_reversible():
    engine = FinalCutEngine.new("Lib", _loader)
    api = EngineAPI(engine)
    clip = Clip(asset_id="A", source_range=TimeRange(Time.zero(), Time.from_seconds(1)))
    blur = GaussianBlurEffect(radius=2.0)

    api.apply_effect(clip, blur)
    assert blur in clip.effects
    api.undo()
    assert blur not in clip.effects
    api.redo()
    assert blur in clip.effects
    engine.shutdown()
