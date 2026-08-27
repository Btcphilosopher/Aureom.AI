"""GPU/CPU compute backend abstraction (spec section 19).

Real Apple Silicon acceleration (Metal compute shaders, ProRes hardware
encode/decode, unified-memory zero-copy buffer sharing between CPU and GPU)
is fundamentally a native-code concern. This module defines the seam:
:class:`ComputeBackend` is the interface every render-graph node effect could
run through; :class:`CPUBackend` is the only backend that actually runs in
pure Python, and :class:`MetalBackend` documents exactly what a native
implementation must provide, failing loudly rather than pretending to
accelerate anything.
"""
from __future__ import annotations

import platform
import sys
from dataclasses import dataclass
from typing import Callable, Protocol

import numpy as np


@dataclass
class SharedBuffer:
    """A buffer that *could* be zero-copy shared between CPU and GPU under a
    unified-memory architecture. On the CPU backend it's just a numpy array;
    a native backend would wrap an ``MTLBuffer`` backed by the same memory
    Core Video/Core Media already decoded into, with no extra copy.
    """

    data: np.ndarray
    gpu_resident: bool = False


class ComputeBackend(Protocol):
    name: str

    def is_available(self) -> bool: ...

    def run(self, op: Callable[[np.ndarray], np.ndarray], buffer: SharedBuffer) -> SharedBuffer: ...


class CPUBackend:
    name = "cpu"

    def is_available(self) -> bool:
        return True

    def run(self, op: Callable[[np.ndarray], np.ndarray], buffer: SharedBuffer) -> SharedBuffer:
        return SharedBuffer(data=op(buffer.data), gpu_resident=False)


class MetalBackend:
    """Integration point for a native Metal compute backend.

    On real Apple Silicon hardware, a native implementation would compile
    each render-graph node's operation to a Metal compute shader, dispatch it
    against a unified-memory ``MTLBuffer``, and never round-trip pixels
    through the CPU. This class only reports availability truthfully and
    fails clearly — it never silently falls back and calls itself
    accelerated.
    """

    name = "metal"

    def is_available(self) -> bool:
        return sys.platform == "darwin" and platform.machine() == "arm64"

    def run(self, op: Callable[[np.ndarray], np.ndarray], buffer: SharedBuffer) -> SharedBuffer:
        raise NotImplementedError(
            "MetalBackend is an integration point for a native Metal compute shader implementation; "
            "it is not implemented in this Python prototype. Use CPUBackend, or provide a native binding."
        )


def select_backend(prefer_gpu: bool = True) -> ComputeBackend:
    if prefer_gpu:
        metal = MetalBackend()
        if metal.is_available():
            return metal
    return CPUBackend()
