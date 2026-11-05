"""SRAM and logic area estimation interfaces (ANALYTICAL).

* :class:`SramAreaModel`            abstract interface used by the explorer
* :class:`AnalyticalSramAreaModel`  bitcell area x bits / array efficiency
* :class:`CompilerTableAreaModel`   plug-in for foundry memory-compiler data
                                    (CSV: words,bits,ports,area_um2[,read_pj,leak_uw])
* :func:`plan_macro_tiling`         mirrors sf_sram_1rw IMPL=1 macro tiling
* :func:`logic_area_mm2`            Yosys NAND2-equivalents -> mm^2

Bitcell areas are public high-density 6T values announced by foundries /
ISSCC papers (e.g. 65 nm ~0.52 um^2, 40 nm ~0.24 um^2, 28 nm ~0.127 um^2) and
NAND2 areas are typical standard-cell-library values; both are INDICATIVE.
An inferred SRAM is never assumed to be a macro: the explorer always maps
logical arrays to explicit macro instances through plan_macro_tiling().
"""
from __future__ import annotations

import csv
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

BITCELL_UM2: dict[int, float] = {180: 4.65, 130: 2.45, 90: 1.0, 65: 0.52, 55: 0.42, 45: 0.30,
                                 40: 0.242, 28: 0.127, 22: 0.092, 16: 0.074}
NAND2_UM2: dict[int, float] = {180: 9.98, 130: 5.1, 90: 2.8, 65: 1.44, 55: 1.2, 45: 0.80,
                               40: 0.71, 28: 0.49, 22: 0.40, 16: 0.20}
PORT_FACTOR = {1: 1.0, 2: 1.8}           # 1RW vs 1R1W / 2RW (8T cell + 2nd periphery)


def _interp(table: dict[int, float], node: int) -> float:
    if node in table:
        return table[node]
    xs = sorted(table)
    if node < xs[0]:
        return table[xs[0]] * (node / xs[0]) ** 2
    if node > xs[-1]:
        return table[xs[-1]] * (node / xs[-1]) ** 2
    lo = max(x for x in xs if x < node)
    hi = min(x for x in xs if x > node)
    f = (math.log(node) - math.log(lo)) / (math.log(hi) - math.log(lo))
    return math.exp(math.log(table[lo]) * (1 - f) + math.log(table[hi]) * f)


class SramAreaModel(ABC):
    """Interface: area of ONE macro instance."""

    @abstractmethod
    def macro_area_um2(self, words: int, bits: int, ports: int = 1) -> float: ...

    @abstractmethod
    def supported(self, words: int, bits: int, ports: int = 1) -> bool: ...

    def array_area_mm2(self, words: int, bits: int, macro_words: int, macro_bits: int,
                       ports: int = 1) -> float:
        plan = plan_macro_tiling(words, bits, macro_words, macro_bits)
        return plan.instances * self.macro_area_um2(macro_words, macro_bits, ports) * 1e-6


@dataclass
class AnalyticalSramAreaModel(SramAreaModel):
    node_nm: int = 40
    eff_max: float = 0.78                # best-case array efficiency (large macros)
    knee_bits: float = 24_000            # efficiency halves at this size
    min_words: int = 64
    max_words: int = 16384
    max_bits: int = 144

    def efficiency(self, total_bits: float) -> float:
        return self.eff_max * total_bits / (total_bits + self.knee_bits)

    def macro_area_um2(self, words: int, bits: int, ports: int = 1) -> float:
        nbits = words * bits
        return nbits * _interp(BITCELL_UM2, self.node_nm) * PORT_FACTOR.get(ports, 2.0) / self.efficiency(nbits)

    def supported(self, words: int, bits: int, ports: int = 1) -> bool:
        return self.min_words <= words <= self.max_words and 4 <= bits <= self.max_bits


class CompilerTableAreaModel(SramAreaModel):
    """Area from memory-compiler datasheet rows; nearest supported config,
    scaled by bit count when an exact match is missing."""

    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    @classmethod
    def from_csv(cls, path: str | Path) -> "CompilerTableAreaModel":
        with open(path) as f:
            rows = [{k: float(v) for k, v in r.items()} for r in csv.DictReader(f)]
        return cls(rows)

    def _cands(self, ports: int) -> list[dict]:
        return [r for r in self.rows if int(r.get("ports", 1)) == ports]

    def supported(self, words: int, bits: int, ports: int = 1) -> bool:
        return any(int(r["words"]) == words and int(r["bits"]) == bits for r in self._cands(ports))

    def macro_area_um2(self, words: int, bits: int, ports: int = 1) -> float:
        cands = self._cands(ports)
        if not cands:
            raise ValueError(f"no compiler rows for {ports}-port macros")
        exact = [r for r in cands if int(r["words"]) == words and int(r["bits"]) == bits]
        if exact:
            return exact[0]["area_um2"]
        nearest = min(cands, key=lambda r: abs(math.log(r["words"] * r["bits"] / (words * bits))))
        return nearest["area_um2"] * (words * bits) / (nearest["words"] * nearest["bits"])


@dataclass(frozen=True)
class MacroPlan:
    logical_words: int
    logical_bits: int
    macro_words: int
    macro_bits: int
    rows: int
    cols: int
    instances: int
    utilisation: float


def plan_macro_tiling(words: int, bits: int, macro_words: int, macro_bits: int) -> MacroPlan:
    """Grid of macros exactly as built by sf_sram_1rw IMPL=1."""
    rows = math.ceil(words / macro_words)
    cols = math.ceil(bits / macro_bits)
    inst = rows * cols
    util = (words * bits) / (inst * macro_words * macro_bits)
    return MacroPlan(words, bits, macro_words, macro_bits, rows, cols, inst, util)


def choose_macro(words: int, bits: int, model: SramAreaModel, ports: int = 1) -> tuple[MacroPlan, float]:
    """Pick the supported macro (depth x width) minimising area for one bank.

    Wide words are split across macro columns (e.g. a 266-bit SECDED word of
    a 256-bit bank uses two 133-bit macros side by side)."""
    best: tuple[MacroPlan, float] | None = None
    for ncols in (1, 2, 3, 4, 6, 8):
        mbits = math.ceil(bits / ncols)
        for d in (256, 512, 1024, 2048, 4096, 8192, 16384):
            if not model.supported(d, mbits, ports):
                continue
            plan = plan_macro_tiling(words, bits, d, mbits)
            area = plan.instances * model.macro_area_um2(d, mbits, ports)
            if best is None or area < best[1]:
                best = (plan, area)
    if best is None:
        raise ValueError(f"no supported macro configuration for {words}x{bits}")
    return best


def spm_area_mm2(capacity_bytes: int, banks: int, width_bits: int, stored_bits: int,
                 node_nm: int = 40, model: SramAreaModel | None = None) -> tuple[float, MacroPlan]:
    model = model or AnalyticalSramAreaModel(node_nm)
    words = capacity_bytes // (banks * width_bits // 8)
    plan, area_um2 = choose_macro(words, stored_bits, model)
    return banks * area_um2 * 1e-6, plan


def logic_area_mm2(nand2_eq: float, node_nm: int = 40, utilisation: float = 0.70) -> float:
    return nand2_eq * _interp(NAND2_UM2, node_nm) / utilisation * 1e-6


# ---- logic gate-count scaling laws, anchored on Yosys results for the
#      reference parameterisation (8x8 tensor, 4x16 vector, 4-ch DMA, 8 banks)
REF_GE = {"tensor_8x8": 145_538.0, "vec_4x16": 38_477.0, "dma_4ch": 66_224.0,
          "spm_ctrl_8b": 60_000.0, "router": 677.0, "ecc64": 1_211.0}


def scaled_logic_ge(tensor_rows: int, tensor_cols: int, vec_lanes: int, banks: int,
                    width_bits: int, dma_channels: int = 4, ref: dict[str, float] | None = None,
                    cpu_cores: int = 1, cpu_core_ge: float = 60_000.0) -> dict[str, float]:
    r = ref or REF_GE
    return {
        "tensor": r["tensor_8x8"] * tensor_rows * tensor_cols / 64.0,
        "vector": r["vec_4x16"] * vec_lanes / 4.0,
        "dma": r["dma_4ch"] * (0.4 + 0.15 * dma_channels) * width_bits / 64.0,
        "spm_logic": r["spm_ctrl_8b"] * banks / 8.0 * width_bits / 64.0,
        "cpu": cpu_core_ge * cpu_cores,
    }
