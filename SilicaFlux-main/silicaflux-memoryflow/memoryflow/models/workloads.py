"""Configurable workload models.

Each workload reports
  * ``ops``                 arithmetic operations (MAC = 2 ops)
  * ``compulsory_bytes``    minimum DRAM traffic (each input read once, output written once)
  * ``dram_bytes(cfg)``     traffic under the best tiling the scratchpad allows
  * ``onchip_bytes(cfg)``   scratchpad -> engine operand traffic (for the SPM ceiling)
  * ``unit``                which SilicaFlux engine executes it (tensor / vector / cpu)

Arithmetic intensity (AI) = ops / dram_bytes.  Everything here is ANALYTICAL.
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass

from memoryflow.models.hardware import SystemConfig
from memoryflow.models.tiling import best_conv_tiling, best_gemm_tiling


class Workload(ABC):
    name: str = "workload"
    unit: str = "vector"
    category: str = ""

    @property
    @abstractmethod
    def ops(self) -> float: ...

    @property
    @abstractmethod
    def compulsory_bytes(self) -> float: ...

    def dram_bytes(self, cfg: SystemConfig) -> float:
        return self.compulsory_bytes

    def onchip_bytes(self, cfg: SystemConfig) -> float:
        """Bytes the engine pulls from the SPM (default: every operand once)."""
        return self.dram_bytes(cfg)

    def ai(self, cfg: SystemConfig) -> float:
        return self.ops / max(self.dram_bytes(cfg), 1.0)

    def ai_compulsory(self) -> float:
        return self.ops / max(self.compulsory_bytes, 1.0)

    def describe(self) -> str:
        return self.name


@dataclass
class Gemm(Workload):
    m: int = 256
    n: int = 256
    k: int = 256
    in_bytes: int = 1
    out_bytes: int = 4
    unit: str = "tensor"
    category: str = "Matrix multiplication"

    def __post_init__(self) -> None:
        self.name = f"GEMM {self.m}x{self.n}x{self.k} int8"

    @property
    def ops(self) -> float:
        return 2.0 * self.m * self.n * self.k

    @property
    def compulsory_bytes(self) -> float:
        return (self.m * self.k + self.k * self.n) * self.in_bytes + self.m * self.n * self.out_bytes

    def tiling(self, cfg: SystemConfig):
        c = cfg.compute
        return best_gemm_tiling(self.m, self.n, self.k, cfg.spm.capacity_bytes,
                                (c.tensor_rows, c.tensor_cols), self.in_bytes, self.out_bytes)

    def dram_bytes(self, cfg: SystemConfig) -> float:
        return float(self.tiling(cfg).dram_bytes)

    def onchip_bytes(self, cfg: SystemConfig) -> float:
        # Each MAC step reads one A beat (TR bytes) from SPM; B tiles are
        # replayed from the reuse buffer, so SPM sees B once per tile column.
        c = cfg.compute
        steps = self.m * self.n * self.k / (c.tensor_rows * c.tensor_cols)
        a = steps * c.tensor_rows * self.in_bytes
        b = self.k * self.n * self.in_bytes * math.ceil(self.m / max(self.tiling(cfg).tm, 1))
        out = self.m * self.n * self.out_bytes
        return a + b + out


@dataclass
class VecAdd(Workload):
    n: int = 1 << 20
    elem_bytes: int = 2
    category: str = "Vector addition"

    def __post_init__(self) -> None:
        self.name = f"VADD n={self.n} int16"

    @property
    def ops(self) -> float:
        return float(self.n)

    @property
    def compulsory_bytes(self) -> float:
        return 3.0 * self.n * self.elem_bytes


@dataclass
class Dot(Workload):
    n: int = 1 << 20
    elem_bytes: int = 2
    category: str = "Dot product"

    def __post_init__(self) -> None:
        self.name = f"DOT n={self.n} int16"

    @property
    def ops(self) -> float:
        return 2.0 * self.n

    @property
    def compulsory_bytes(self) -> float:
        return 2.0 * self.n * self.elem_bytes + 8


@dataclass
class Conv2d(Workload):
    batch: int = 1
    c: int = 64
    h: int = 56
    w: int = 56
    k: int = 64
    r: int = 3
    s: int = 3
    stride: int = 1
    pad: int = 1
    in_bytes: int = 1
    out_bytes: int = 1
    unit: str = "tensor"
    category: str = "Convolution"

    def __post_init__(self) -> None:
        self.name = f"CONV {self.c}x{self.h}x{self.w}->{self.k} k{self.r}"

    @property
    def p(self) -> int:
        return (self.h + 2 * self.pad - self.r) // self.stride + 1

    @property
    def q(self) -> int:
        return (self.w + 2 * self.pad - self.s) // self.stride + 1

    @property
    def ops(self) -> float:
        return 2.0 * self.batch * self.k * self.p * self.q * self.c * self.r * self.s

    @property
    def compulsory_bytes(self) -> float:
        return ((self.batch * self.c * self.h * self.w + self.k * self.c * self.r * self.s) * self.in_bytes
                + self.batch * self.k * self.p * self.q * self.out_bytes)

    def dram_bytes(self, cfg: SystemConfig) -> float:
        t = best_conv_tiling(self.batch, self.c, self.h, self.w, self.k, self.r, self.s, self.stride,
                             self.pad, cfg.spm.capacity_bytes, self.in_bytes, self.out_bytes)
        return float(max(t.dram_bytes, self.compulsory_bytes))

    def onchip_bytes(self, cfg: SystemConfig) -> float:
        # implicit-GEMM on the tensor array: M=K, N=P*Q, Kdim=C*R*S
        g = Gemm(self.k, self.batch * self.p * self.q, self.c * self.r * self.s, self.in_bytes, self.out_bytes)
        return g.onchip_bytes(cfg)


@dataclass
class Fir(Workload):
    n: int = 1 << 20
    taps: int = 64
    elem_bytes: int = 2
    category: str = "Streaming signal processing"

    def __post_init__(self) -> None:
        self.name = f"FIR {self.taps}-tap n={self.n}"

    @property
    def ops(self) -> float:
        return 2.0 * self.n * self.taps

    @property
    def compulsory_bytes(self) -> float:
        return 2.0 * self.n * self.elem_bytes + self.taps * self.elem_bytes

    def onchip_bytes(self, cfg: SystemConfig) -> float:
        # register blocking: taps held in registers, each sample read once
        return self.compulsory_bytes


@dataclass
class Fft(Workload):
    points: int = 4096
    batch: int = 256
    complex_bytes: int = 8              # fp32 complex
    unit: str = "vector"
    category: str = "Streaming signal processing"

    def __post_init__(self) -> None:
        self.name = f"FFT {self.points}-pt x{self.batch}"

    @property
    def ops(self) -> float:
        return 5.0 * self.points * math.log2(self.points) * self.batch

    @property
    def compulsory_bytes(self) -> float:
        return 2.0 * self.points * self.complex_bytes * self.batch

    def dram_bytes(self, cfg: SystemConfig) -> float:
        fit_points = max(cfg.spm.capacity_bytes // (2 * self.complex_bytes), 2)  # double buffered
        if self.points <= fit_points:
            return self.compulsory_bytes
        passes = math.ceil(math.log2(self.points) / math.log2(fit_points))
        return self.compulsory_bytes * passes


@dataclass
class Stencil2D(Workload):
    nx: int = 2048
    ny: int = 2048
    iters: int = 10
    points: int = 5
    elem_bytes: int = 4
    temporal_block: int = 1
    category: str = "Scientific numerical kernel"

    def __post_init__(self) -> None:
        self.name = f"JACOBI2D {self.points}pt {self.nx}x{self.ny} x{self.iters}"

    @property
    def ops(self) -> float:
        return 2.0 * self.points * self.nx * self.ny * self.iters

    @property
    def compulsory_bytes(self) -> float:
        return 2.0 * self.nx * self.ny * self.elem_bytes

    def dram_bytes(self, cfg: SystemConfig) -> float:
        grid = self.nx * self.ny * self.elem_bytes
        if 2 * grid <= cfg.spm.capacity_bytes:
            return self.compulsory_bytes            # whole problem on chip
        # row-buffer streaming: 3 rows (+2 for double buffering) must fit
        if 5 * self.nx * self.elem_bytes > cfg.spm.capacity_bytes:
            return self.compulsory_bytes * self.iters * 3.0   # rows re-fetched
        tb = max(1, self.temporal_block)
        return self.compulsory_bytes * math.ceil(self.iters / tb)


@dataclass
class SpMV(Workload):
    rows: int = 1 << 17
    nnz_per_row: int = 16
    value_bytes: int = 4
    index_bytes: int = 4
    category: str = "Scientific numerical kernel"

    def __post_init__(self) -> None:
        self.name = f"SpMV {self.rows} rows nnz/row={self.nnz_per_row}"

    @property
    def nnz(self) -> int:
        return self.rows * self.nnz_per_row

    @property
    def ops(self) -> float:
        return 2.0 * self.nnz

    @property
    def compulsory_bytes(self) -> float:
        return (self.nnz * (self.value_bytes + self.index_bytes) + (self.rows + 1) * self.index_bytes
                + 2 * self.rows * self.value_bytes)

    def dram_bytes(self, cfg: SystemConfig) -> float:
        x_bytes = self.rows * self.value_bytes
        if x_bytes <= cfg.spm.capacity_bytes // 2:
            return self.compulsory_bytes
        # x does not fit: irregular gathers cost one 8-byte beat each
        return self.compulsory_bytes + self.nnz * 8 * (1 - (cfg.spm.capacity_bytes // 2) / x_bytes)


def default_suite() -> list[Workload]:
    """The SilicaFlux-V reference workload suite."""
    return [
        Gemm(512, 512, 512),
        Gemm(64, 4096, 1024),          # transformer-style skinny GEMM
        Conv2d(1, 64, 56, 56, 64, 3, 3, 1, 1),
        Conv2d(1, 256, 14, 14, 256, 3, 3, 1, 1),
        VecAdd(1 << 20),
        Dot(1 << 20),
        Fir(1 << 20, 64),
        Fft(4096, 64),
        Stencil2D(2048, 2048, 10),
        SpMV(1 << 17, 16),
    ]
