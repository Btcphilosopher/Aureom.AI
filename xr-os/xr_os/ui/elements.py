"""
Spatial UI: floating windows, panels, 3D buttons, menus, toolbars,
notifications, a virtual keyboard, and a voice-interface hook -- all
positionable relative to the head, hands, room, an object, or world space.
"""

from __future__ import annotations

import time
from typing import Callable

from xr_os.core.math3d import Transform, Vector3
from xr_os.scene.node import SceneNode
from xr_os.scene.nodes import PanelNode, UINode
from xr_os.ui.anchoring import PlacementRef, RelativeTo, resolve_placement

ClickHandler = Callable[["Button3D"], None]

_ROW_KEYS = ["QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"]


class SpatialUIElement:
    """Base class: wraps a ``SceneNode`` plus how it should be anchored."""

    def __init__(self, node: SceneNode, placement: PlacementRef | None = None) -> None:
        self.node = node
        self.placement = placement or PlacementRef(RelativeTo.WORLD, node.local_transform)

    def update_placement(self, tracking_engine=None, world_model=None) -> Transform:
        """Recompute and apply this element's local transform from its placement ref.

        For WORLD placement the node's own local transform already holds the
        position, so this is a no-op there; for HEAD/HAND/ROOM/OBJECT
        placement it re-derives the transform each call so the element keeps
        following its anchor.
        """
        if self.placement.relative_to != RelativeTo.WORLD:
            world_transform = resolve_placement(self.placement, tracking_engine, world_model)
            if self.node.parent is not None:
                self.node.local_transform = self.node.parent.world_transform.inverse().combine(world_transform)
            else:
                self.node.local_transform = world_transform
        return self.node.world_transform

    def mount(self, parent: SceneNode) -> "SpatialUIElement":
        parent.add_child(self.node)
        return self


class SpatialPanel(SpatialUIElement):
    """A floating rectangular spatial surface, the base of most spatial windows."""

    def __init__(
        self,
        position: tuple[float, float, float] = (0.0, 0.0, 0.0),
        size: tuple[float, float] = (1.0, 1.0),
        name: str = "panel",
        placement: PlacementRef | None = None,
    ) -> None:
        node = PanelNode(name, size=size, local_transform=Transform(Vector3.from_tuple(position)))
        node.bounding_radius = max(size) / 2
        super().__init__(node, placement)
        self.size = size
        self.children_elements: list[SpatialUIElement] = []

    def add(self, element: "SpatialUIElement") -> "SpatialUIElement":
        self.node.add_child(element.node)
        self.children_elements.append(element)
        return element


class Button3D(SpatialUIElement):
    """A pressable 3D button. Fires ``on_click`` when it receives a CLICK/PINCH interaction."""

    def __init__(
        self,
        label: str,
        position: tuple[float, float, float] = (0.0, 0.0, 0.0),
        size: tuple[float, float] = (0.1, 0.05),
        on_click: ClickHandler | None = None,
        placement: PlacementRef | None = None,
    ) -> None:
        node = UINode(f"button:{label}", local_transform=Transform(Vector3.from_tuple(position)))
        node.bounding_radius = max(size) / 2
        node.metadata["label"] = label
        super().__init__(node, placement)
        self.label = label
        self.size = size
        self._on_click = on_click
        self.node.on_interact(self._handle_interact)

    def _handle_interact(self, node: SceneNode, event_type: str, payload: dict) -> None:
        if event_type in ("click", "pinch") and self._on_click is not None:
            self._on_click(self)

    def click(self) -> None:
        self.node.interact("click")


class Menu(SpatialPanel):
    """A vertical list of buttons."""

    def __init__(
        self,
        items: list[str],
        position: tuple[float, float, float] = (0.0, 0.0, 0.0),
        on_select: Callable[[str], None] | None = None,
        item_height: float = 0.08,
        placement: PlacementRef | None = None,
    ) -> None:
        super().__init__(position=position, size=(0.4, item_height * max(1, len(items))), name="menu", placement=placement)
        self.buttons: list[Button3D] = []
        for i, label in enumerate(items):
            y = -(i * item_height)
            button = Button3D(label, position=(0.0, y, 0.0), on_click=lambda b, sel=label: on_select and on_select(sel))
            self.add(button)
            self.buttons.append(button)


class Toolbar(SpatialPanel):
    """A horizontal strip of buttons, e.g. mounted below a panel."""

    def __init__(
        self,
        items: list[str],
        position: tuple[float, float, float] = (0.0, 0.0, 0.0),
        on_select: Callable[[str], None] | None = None,
        item_width: float = 0.12,
        placement: PlacementRef | None = None,
    ) -> None:
        super().__init__(position=position, size=(item_width * max(1, len(items)), 0.1), name="toolbar", placement=placement)
        self.buttons: list[Button3D] = []
        for i, label in enumerate(items):
            x = i * item_width
            button = Button3D(label, position=(x, 0.0, 0.0), on_click=lambda b, sel=label: on_select and on_select(sel))
            self.add(button)
            self.buttons.append(button)


class Notification(SpatialUIElement):
    """A transient HUD-style message, head-locked by default, with a time-to-live."""

    def __init__(
        self,
        text: str,
        duration_seconds: float = 3.0,
        position: tuple[float, float, float] = (0.0, 0.1, -1.0),
        placement: PlacementRef | None = None,
    ) -> None:
        node = UINode("notification", local_transform=Transform(Vector3.from_tuple(position)))
        node.metadata["text"] = text
        placement = placement or PlacementRef(RelativeTo.HEAD, node.local_transform)
        super().__init__(node, placement)
        self.text = text
        self.created_at = time.time()
        self.duration_seconds = duration_seconds

    @property
    def expired(self) -> bool:
        return (time.time() - self.created_at) >= self.duration_seconds


class VirtualKeyboard(SpatialPanel):
    """A QWERTY spatial keyboard; each key press appends to ``buffer``."""

    def __init__(
        self,
        position: tuple[float, float, float] = (0.0, -0.2, -0.5),
        on_key: Callable[[str], None] | None = None,
        key_size: float = 0.045,
        placement: PlacementRef | None = None,
    ) -> None:
        rows = _ROW_KEYS
        width = key_size * max(len(r) for r in rows)
        super().__init__(position=position, size=(width, key_size * len(rows)), name="keyboard", placement=placement)
        self.buffer: str = ""
        self.keys: dict[str, Button3D] = {}
        for row_idx, row in enumerate(rows):
            y = -(row_idx * key_size)
            offset = row_idx * key_size * 0.5
            for col_idx, char in enumerate(row):
                x = offset + col_idx * key_size
                key = Button3D(char, position=(x, y, 0.0), on_click=lambda b, c=char: self._press(c, on_key))
                self.add(key)
                self.keys[char] = key

    def _press(self, char: str, on_key: Callable[[str], None] | None) -> None:
        self.buffer += char
        if on_key is not None:
            on_key(char)

    def backspace(self) -> None:
        self.buffer = self.buffer[:-1]

    def clear(self) -> None:
        self.buffer = ""


class VoiceInterface:
    """
    A minimal voice-interface hook: apps register intents/phrases, and feed
    recognized transcripts in (from whatever speech-to-text backend is
    wired up at the platform level via ``xr_os.input``).
    """

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[str], None]] = {}
        self._fallback: Callable[[str], None] | None = None

    def on_phrase(self, phrase: str, handler: Callable[[str], None]) -> None:
        self._handlers[phrase.lower().strip()] = handler

    def on_unmatched(self, handler: Callable[[str], None]) -> None:
        self._fallback = handler

    def handle_transcript(self, transcript: str) -> bool:
        key = transcript.lower().strip()
        if key in self._handlers:
            self._handlers[key](transcript)
            return True
        for phrase, handler in self._handlers.items():
            if phrase in key:
                handler(transcript)
                return True
        if self._fallback is not None:
            self._fallback(transcript)
        return False
