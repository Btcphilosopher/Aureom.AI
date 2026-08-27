"""Command architecture and the undo/redo engine (spec section 23).

Every editing operation that mutates the project — inserting a clip, trimming,
applying an effect, adjusting colour — is expressed as a :class:`Command`
rather than a direct mutation. The :class:`UndoManager` owns the undo/redo
stacks. This is what lets the magnetic timeline, effects, and colour systems
share one reversible-history mechanism instead of each inventing its own.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional

from finalcut_engine.core.events import EventBus


class Command(ABC):
    """A single reversible editing operation."""

    #: Human-readable label shown in an "Undo ___" menu item. Deliberately a
    #: bare annotation (no default) — every concrete subclass sets it. Giving
    #: it a default here would set an actual class attribute that `dataclass`
    #: subclasses (via `getattr` during field collection) would silently pick
    #: up as an inherited default, breaking their own field ordering.
    label: str

    @abstractmethod
    def do(self) -> None:
        """Apply the command's effect. Called once on first execution."""

    @abstractmethod
    def undo(self) -> None:
        """Exactly reverse :meth:`do`."""

    def redo(self) -> None:
        """Re-apply after an undo. Defaults to calling :meth:`do` again."""
        self.do()


@dataclass
class CompositeCommand(Command):
    """Groups several commands so they undo/redo as one unit."""

    label: str
    commands: List[Command] = field(default_factory=list)

    def do(self) -> None:
        for c in self.commands:
            c.do()

    def undo(self) -> None:
        for c in reversed(self.commands):
            c.undo()

    def redo(self) -> None:
        for c in self.commands:
            c.redo()


class UndoManager:
    """Owns the undo/redo stacks for a project.

    ``max_history`` bounds memory use for very long sessions; ``None`` means
    unlimited, matching the spec's "unlimited or configurable" requirement.
    """

    def __init__(self, max_history: Optional[int] = None, events: Optional[EventBus] = None) -> None:
        self.max_history = max_history
        self._undo_stack: List[Command] = []
        self._redo_stack: List[Command] = []
        self.events = events or EventBus()
        self._batch: Optional[CompositeCommand] = None

    # -- executing commands ---------------------------------------------
    def execute(self, command: Command) -> None:
        command.do()
        self._push(command)

    def _push(self, command: Command) -> None:
        if self._batch is not None:
            self._batch.commands.append(command)
            return
        self._undo_stack.append(command)
        self._redo_stack.clear()
        if self.max_history is not None:
            while len(self._undo_stack) > self.max_history:
                self._undo_stack.pop(0)
        self.events.publish("history_changed", source=self, can_undo=self.can_undo, can_redo=self.can_redo)

    class _Batch:
        """Context manager: ``with undo_manager.batch("Ripple Trim"): ...``"""

        def __init__(self, manager: "UndoManager", label: str):
            self.manager = manager
            self.label = label

        def __enter__(self) -> "UndoManager":
            self.manager._batch = CompositeCommand(label=self.label)
            return self.manager

        def __exit__(self, exc_type, exc, tb) -> bool:
            batch = self.manager._batch
            self.manager._batch = None
            if exc_type is None and batch.commands:
                self.manager._undo_stack.append(batch)
                self.manager._redo_stack.clear()
                self.manager.events.publish(
                    "history_changed", source=self.manager, can_undo=True, can_redo=self.manager.can_redo
                )
            return False

    def batch(self, label: str) -> "UndoManager._Batch":
        """Group all commands executed inside the ``with`` block into one undo step."""
        return UndoManager._Batch(self, label)

    # -- undo / redo -------------------------------------------------------
    @property
    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def undo(self) -> Optional[str]:
        if not self._undo_stack:
            return None
        command = self._undo_stack.pop()
        command.undo()
        self._redo_stack.append(command)
        self.events.publish("history_changed", source=self, can_undo=self.can_undo, can_redo=self.can_redo)
        return command.label

    def redo(self) -> Optional[str]:
        if not self._redo_stack:
            return None
        command = self._redo_stack.pop()
        command.redo()
        self._undo_stack.append(command)
        self.events.publish("history_changed", source=self, can_undo=self.can_undo, can_redo=self.can_redo)
        return command.label

    def history_labels(self) -> List[str]:
        return [c.label for c in self._undo_stack]

    def clear(self) -> None:
        self._undo_stack.clear()
        self._redo_stack.clear()
