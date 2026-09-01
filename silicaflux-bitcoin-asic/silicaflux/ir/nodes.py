"""
Minimal hardware intermediate representation used as the pivot point
between a declarative silicaflux.architecture.MinerArchitecture and the
generated SystemVerilog parameter package.

Every IR node is tagged with one of the eight structural categories the
project brief asks the SilicaFlux layer to be able to describe (section
15): DATAFLOW, PIPELINE, REGISTER, COMBINATIONAL, MEMORY, CONTROL,
CLOCK, INTERFACE. The tag is carried through to the emitted RTL as a
comment grouping, so the generated package's structure documents *why*
each parameter exists, not just its value.

This IR is intentionally small: it is a real (if simple) compiler pass
-- silicaflux.compiler.lower() validates a MinerArchitecture and
produces exactly one IRDesign, and silicaflux.generators.sv_emitter
is a pure function IRDesign -> str with no access back to the spec
layer. That separation is what keeps the SilicaFlux -> RTL translation
deterministic and inspectable rather than an opaque template dump.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Union


class IRKind(Enum):
    DATAFLOW = auto()       # nonce search / hashing dataflow shape (core count, stride)
    PIPELINE = auto()       # pipeline depth / staging choices
    REGISTER = auto()       # register/storage architecture (schedule storage, telemetry width)
    COMBINATIONAL = auto()  # purely combinational structural choices
    MEMORY = auto()         # any addressed storage (none in this design; reserved)
    CONTROL = auto()        # control-plane / FSM-facing parameters
    CLOCK = auto()          # clock domain / frequency / gating metadata
    INTERFACE = auto()      # external interface widths (nonce width, header width)


@dataclass(frozen=True)
class IRParam:
    """One generated `localparam` (or `parameter`, for the top-level knobs
    left overridable at instantiation)."""
    name: str
    value: Union[int, str, bool]
    kind: IRKind
    comment: str = ""
    #: SystemVerilog type string, e.g. "int", "logic [31:0]", "string".
    sv_type: str = "int"
    #: If True, emitted as `parameter` (overridable); else `localparam`.
    overridable: bool = False


@dataclass(frozen=True)
class IRClockDomain:
    name: str
    target_frequency_mhz: float
    enable_clock_gating: bool
    kind: IRKind = IRKind.CLOCK


@dataclass(frozen=True)
class IRDesign:
    """Root IR node: the fully-lowered, validated description of one
    MinerArchitecture, ready for deterministic SystemVerilog emission."""
    top_name: str
    source_config_name: str
    params: list = field(default_factory=list)          # list[IRParam]
    clock_domains: list = field(default_factory=list)    # list[IRClockDomain]
    notes: list = field(default_factory=list)             # list[str], carried into the file header

    def params_by_kind(self, kind: IRKind):
        return [p for p in self.params if p.kind is kind]
