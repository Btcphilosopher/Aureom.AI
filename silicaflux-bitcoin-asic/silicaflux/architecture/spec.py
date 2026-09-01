"""
Declarative architecture specification for a SilicaFlux Bitcoin SHA-256
miner configuration. This is the *only* place architecture choices are
made in one spot; everything downstream (silicaflux.compiler,
silicaflux.generators, and the RTL parameter package they emit) is a
deterministic function of a MinerArchitecture instance.

Nothing in this module touches the hashing datapath itself -- it only
describes structural/configuration choices that the hand-written,
independently-verified RTL in rtl/ already supports as parameters.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ArchitectureError(ValueError):
    """Raised by MinerArchitecture.validate() / silicaflux.compiler.lower()."""


class CoreArchitecture(str, Enum):
    #: rtl/sha256/sha256_compressor.sv -- one round per clock, round-counter
    #: FSM, 64 (+overhead) cycles per block compression. Minimum area per
    #: core; throughput is scaled by replicating many cores instead.
    ITERATIVE = "ITERATIVE"
    #: rtl/pipeline/sha256_pipeline.sv -- all 64 rounds spatially unrolled
    #: into PIPELINE_DEPTH pipeline stages (64/PIPELINE_DEPTH rounds of
    #: combinational logic per stage). One block enters the pipeline every
    #: clock; latency and per-stage combinational depth are set by
    #: PIPELINE_DEPTH. Round hardware count is fixed at 64 regardless of
    #: depth -- depth only changes where pipeline *registers* are inserted.
    PIPELINED = "PIPELINED"


class ScheduleArchitecture(str, Enum):
    #: 16-word circular register window; one new W[t] produced per cycle
    #: from W[t-16..t-1]. Minimum storage (16 words vs. 64). Used by the
    #: ITERATIVE core.
    SLIDING_WINDOW = "SLIDING_WINDOW"
    #: Each pipeline stage carries its own 16-word window forward and
    #: advances it ROUNDS_PER_STAGE times combinationally per stage
    #: (registered at stage boundaries). Used by the PIPELINED core.
    REGISTER_PIPELINED = "REGISTER_PIPELINED"
    #: All of W[16..63] computed combinationally in one shot from W[0..15]
    #: with no intermediate registers. Included for architectural
    #: comparison (section 6 of the project brief); not the recommended
    #: choice for anything but PIPELINE_DEPTH=64, since the combinational
    #: path length grows with how many W-words are chained together
    #: unregistered -- see docs/architecture.md.
    FULL_COMBINATIONAL = "FULL_COMBINATIONAL"

    def is_valid_for(self, core_arch: "CoreArchitecture") -> bool:
        if core_arch == CoreArchitecture.ITERATIVE:
            return self == ScheduleArchitecture.SLIDING_WINDOW
        return self in (ScheduleArchitecture.REGISTER_PIPELINED, ScheduleArchitecture.FULL_COMBINATIONAL)


# Pipeline depths for which sha256_pipeline.sv's generate blocks are
# defined: 64 rounds must divide evenly among stages.
VALID_PIPELINE_DEPTHS = (1, 2, 4, 8, 16, 32, 64)


@dataclass(frozen=True)
class PipelineConfig:
    architecture: CoreArchitecture = CoreArchitecture.ITERATIVE
    #: Only meaningful when architecture == PIPELINED. Must be one of
    #: VALID_PIPELINE_DEPTHS. 64 = one round per stage (max Fmax, max
    #: registers). 1 would mean a single fully-combinational 64-round
    #: stage -- structurally valid but not a realistic synthesis target;
    #: kept only as the degenerate end of the design-space sweep.
    pipeline_depth: int = 1
    schedule_architecture: ScheduleArchitecture = ScheduleArchitecture.SLIDING_WINDOW

    def rounds_per_stage(self) -> int:
        if self.architecture == CoreArchitecture.ITERATIVE:
            return 1
        return 64 // self.pipeline_depth

    def validate(self) -> None:
        if self.architecture == CoreArchitecture.ITERATIVE:
            if self.schedule_architecture != ScheduleArchitecture.SLIDING_WINDOW:
                raise ArchitectureError(
                    "ITERATIVE core requires SLIDING_WINDOW schedule architecture, "
                    f"got {self.schedule_architecture}"
                )
        else:
            if self.pipeline_depth not in VALID_PIPELINE_DEPTHS:
                raise ArchitectureError(
                    f"pipeline_depth={self.pipeline_depth} invalid; must be one of {VALID_PIPELINE_DEPTHS}"
                )
            if 64 % self.pipeline_depth != 0:
                raise ArchitectureError("pipeline_depth must divide 64 evenly")
            if not self.schedule_architecture.is_valid_for(self.architecture):
                raise ArchitectureError(
                    f"schedule_architecture={self.schedule_architecture} invalid for PIPELINED core"
                )


@dataclass(frozen=True)
class NonceAllocConfig:
    #: Bitcoin's header nonce field is architecturally 32 bits. A wider
    #: value is accepted here only for design-space research that treats
    #: nonce+rolled-extranonce as one combined search counter; it is NOT
    #: standards-compliant for the literal header nonce field and RTL
    #: generated with nonce_width != 32 must not be described as
    #: Bitcoin-header-compliant.
    nonce_width: int = 32
    nonce_start: int = 0
    #: Stride between successive nonce values a single core tries. The
    #: allocator gives core `i` the arithmetic sequence
    #!   nonce_start + i*stride, nonce_start + (num_cores+i)*stride, ...
    #: i.e. cores are interleaved so that no two cores (and no two
    #: successive values tried by the same core) ever collide, for any
    #: num_cores >= 1 and stride >= 1. See nonce_allocator.sv.
    nonce_stride: int = 1

    def validate(self, num_cores: int) -> None:
        if not (1 <= self.nonce_width <= 64):
            raise ArchitectureError("nonce_width must be in [1, 64]")
        if self.nonce_width != 32:
            raise ArchitectureError(
                "nonce_width != 32 is not standards-compliant with the Bitcoin "
                "header nonce field; use 32 unless explicitly doing extranonce-"
                "combined research (not supported by the current RTL top level)"
            )
        if self.nonce_stride < 1:
            raise ArchitectureError("nonce_stride must be >= 1")
        if num_cores < 1:
            raise ArchitectureError("num_cores must be >= 1")


@dataclass(frozen=True)
class TelemetryConfig:
    enabled: bool = True
    counter_width: int = 32


@dataclass(frozen=True)
class ClockDomainConfig:
    name: str = "core_clk"
    #: Abstract, non-binding target frequency for the performance model /
    #: design-space exploration scripts. This is NOT a synthesis
    #: constraint or a claim about achievable Fmax on any real process --
    #: see docs/architecture.md "THEORETICAL vs measured" categories.
    target_frequency_mhz: float = 100.0
    enable_clock_gating: bool = False


#: Supported core counts for hash_core_array.sv's generate block. Any
#: positive integer is structurally legal; this list is what the
#: design-space exploration scripts sweep by default (section 8).
SWEEP_CORE_COUNTS = (1, 4, 8, 16, 32, 64, 128)


@dataclass(frozen=True)
class MinerArchitecture:
    name: str
    num_cores: int = 1
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    nonce: NonceAllocConfig = field(default_factory=NonceAllocConfig)
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)
    clock: ClockDomainConfig = field(default_factory=ClockDomainConfig)
    enable_assertions: bool = True
    #: Technology-independence placeholder (section 23): purely
    #: informational metadata carried into the generated package as a
    #: comment. No RTL behaviour depends on this string.
    process_node: str = "generic/unspecified"

    def validate(self) -> None:
        if not self.name or not self.name.isidentifier():
            raise ArchitectureError(f"architecture name {self.name!r} must be a valid identifier")
        if self.num_cores < 1:
            raise ArchitectureError("num_cores must be >= 1")
        self.pipeline.validate()
        self.nonce.validate(self.num_cores)
        if self.telemetry.counter_width < 8:
            raise ArchitectureError("telemetry.counter_width must be >= 8")
        if self.clock.target_frequency_mhz <= 0:
            raise ArchitectureError("clock.target_frequency_mhz must be > 0")

    @staticmethod
    def from_dict(d: dict) -> "MinerArchitecture":
        pd = dict(d.get("pipeline", {}))
        if "architecture" in pd:
            pd["architecture"] = CoreArchitecture(pd["architecture"])
        if "schedule_architecture" in pd:
            pd["schedule_architecture"] = ScheduleArchitecture(pd["schedule_architecture"])
        arch = MinerArchitecture(
            name=d["name"],
            num_cores=int(d.get("num_cores", 1)),
            pipeline=PipelineConfig(**pd),
            nonce=NonceAllocConfig(**d.get("nonce", {})),
            telemetry=TelemetryConfig(**d.get("telemetry", {})),
            clock=ClockDomainConfig(**d.get("clock", {})),
            enable_assertions=bool(d.get("enable_assertions", True)),
            process_node=str(d.get("process_node", "generic/unspecified")),
        )
        arch.validate()
        return arch
