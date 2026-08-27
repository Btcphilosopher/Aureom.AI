"""The internal per-clip render graph:

```
SOURCE -> TRANSFORM -> CROP -> COLOUR -> EFFECT -> COMPOSITE -> TEXT -> OUTPUT
```

Each node's cache key is a hash of its own parameters *plus* the keys of all
its inputs (computed recursively). Evaluation memoizes on that key via
:class:`~finalcut_engine.render.cache.RenderCache`, so "only recompute what
changed" falls out of ordinary memoization rather than manual dirty-flag
bookkeeping: change a colour node's parameters and only it (and anything
downstream of it) misses the cache; the source decode and any sibling
branches are untouched.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, List, Optional

import numpy as np

from finalcut_engine.core.timebase import Time
from finalcut_engine.render.cache import RenderCache


class RenderNode(ABC):
    def __init__(self, name: str = "Node", inputs: Optional[List["RenderNode"]] = None) -> None:
        self.id = uuid.uuid4().hex
        self.name = name
        self.inputs: List[RenderNode] = inputs or []

    @abstractmethod
    def local_params(self, t: Time) -> tuple:
        """A hashable snapshot of this node's own parameters at time ``t``."""

    @abstractmethod
    def compute(self, t: Time, input_frames: List[np.ndarray]) -> np.ndarray:
        """Produce this node's output frame from its already-evaluated inputs."""

    def compute_key(self, t: Time) -> tuple:
        return (type(self).__name__, self.local_params(t), tuple(i.compute_key(t) for i in self.inputs))


class SourceNode(RenderNode):
    """Decodes (or synthesises) the raw frame for a clip at time ``t``."""

    def __init__(self, asset_id: str, frame_loader: Callable[[str, Time], np.ndarray], name: str = "Source"):
        super().__init__(name=name, inputs=[])
        self.asset_id = asset_id
        self.frame_loader = frame_loader

    def local_params(self, t: Time) -> tuple:
        return (self.asset_id, round(t.seconds(), 6))

    def compute(self, t: Time, input_frames: List[np.ndarray]) -> np.ndarray:
        return self.frame_loader(self.asset_id, t)


class TransformNode(RenderNode):
    def __init__(self, upstream: RenderNode, transform_at: Callable[[Time], object], name: str = "Transform"):
        super().__init__(name=name, inputs=[upstream])
        self.transform_at = transform_at

    def local_params(self, t: Time) -> tuple:
        transform = self.transform_at(t)
        return (transform.position, transform.scale, transform.rotation_degrees, transform.anchor, transform.crop)

    def compute(self, t: Time, input_frames: List[np.ndarray]) -> np.ndarray:
        return self.transform_at(t).apply(input_frames[0])


class ColourNode(RenderNode):
    def __init__(self, upstream: RenderNode, pipeline, name: str = "Colour"):
        super().__init__(name=name, inputs=[upstream])
        self.pipeline = pipeline

    def local_params(self, t: Time) -> tuple:
        # The pipeline may itself contain keyframed (callable) stages; applying
        # it is cheap relative to hashing every stage's internals, so key on
        # the *result* of resolving stages would be circular — instead key on
        # identity + time, which still gives correct invalidation whenever the
        # pipeline object is replaced (e.g. the user adjusts a grade).
        return (id(self.pipeline), round(t.seconds(), 6))

    def compute(self, t: Time, input_frames: List[np.ndarray]) -> np.ndarray:
        return self.pipeline.apply(input_frames[0], t)


class EffectNode(RenderNode):
    def __init__(self, upstream: RenderNode, filter_stack, name: str = "Effect"):
        super().__init__(name=name, inputs=[upstream])
        self.filter_stack = filter_stack

    def local_params(self, t: Time) -> tuple:
        return self.filter_stack.cache_key(t)

    def compute(self, t: Time, input_frames: List[np.ndarray]) -> np.ndarray:
        return self.filter_stack.apply(input_frames[0], t)


class CompositeNode(RenderNode):
    """Composites one or more overlay inputs onto a base input, in order."""

    def __init__(self, base: RenderNode, overlays: List[RenderNode], mode="normal", opacity: float = 1.0, name: str = "Composite"):
        super().__init__(name=name, inputs=[base] + overlays)
        self.mode = mode
        self.opacity = opacity

    def local_params(self, t: Time) -> tuple:
        return (self.mode, self.opacity)

    def compute(self, t: Time, input_frames: List[np.ndarray]) -> np.ndarray:
        from finalcut_engine.effects.compositing import composite, BlendMode

        base = input_frames[0]
        for overlay in input_frames[1:]:
            base = composite(base, overlay, BlendMode(self.mode), self.opacity)
        return base


class TextNode(RenderNode):
    def __init__(self, upstream: RenderNode, title, name: str = "Text"):
        super().__init__(name=name, inputs=[upstream])
        self.title = title

    def local_params(self, t: Time) -> tuple:
        return (self.title.text, self.title.colour, self.title.position, round(self.title.opacity_at(t), 4))

    def compute(self, t: Time, input_frames: List[np.ndarray]) -> np.ndarray:
        return self.title.render_onto(input_frames[0], t)


class OutputNode(RenderNode):
    def __init__(self, upstream: RenderNode, name: str = "Output"):
        super().__init__(name=name, inputs=[upstream])

    def local_params(self, t: Time) -> tuple:
        return ()

    def compute(self, t: Time, input_frames: List[np.ndarray]) -> np.ndarray:
        return input_frames[0]


@dataclass
class RenderGraph:
    output: RenderNode

    def evaluate(self, t: Time, cache: Optional[RenderCache] = None) -> np.ndarray:
        cache = cache if cache is not None else RenderCache()

        def _eval(node: RenderNode) -> np.ndarray:
            key = node.compute_key(t)
            cached = cache.get(key)
            if cached is not None:
                return cached
            input_frames = [_eval(i) for i in node.inputs]
            frame = node.compute(t, input_frames)
            cache.put(key, frame)
            return frame

        return _eval(self.output)

    def node_count(self) -> int:
        seen = set()

        def _walk(node: RenderNode) -> None:
            if node.id in seen:
                return
            seen.add(node.id)
            for i in node.inputs:
                _walk(i)

        _walk(self.output)
        return len(seen)
