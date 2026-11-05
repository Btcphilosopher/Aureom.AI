"""Tiling models: DRAM traffic of tiled kernels under a scratchpad budget.

GEMM uses an output-stationary schedule that matches sf_tensor_array: an
(tm x tn) output tile is accumulated on chip while A (tm x tk) and B
(tk x tn) panels stream through double-buffered scratchpad regions.
  A traffic = M*K*in * ceil(N/tn)       B traffic = K*N*in * ceil(M/tm)
  C traffic = M*N*out (written once)
The search is exhaustive over tile sizes that are multiples of the array
dimensions, so results are exact for the model (ANALYTICAL provenance).
"""
from __future__ import annotations

import functools
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class GemmTiling:
    tm: int
    tn: int
    tk: int
    footprint_bytes: int
    dram_bytes: int
    a_bytes: int
    b_bytes: int
    c_bytes: int
    fits: bool

    @property
    def reuse_a(self) -> float:
        return self.tn


def gemm_footprint(tm: int, tn: int, tk: int, in_b: int = 1, acc_b: int = 4, nbuf: int = 2) -> int:
    """SPM bytes: nbuf x (A panel + B panel) + partial-sum tile."""
    return nbuf * (tm * tk + tk * tn) * in_b + tm * tn * acc_b


def gemm_traffic(m: int, n: int, k: int, tm: int, tn: int, in_b: int = 1, out_b: int = 4) -> tuple[int, int, int]:
    a = m * k * in_b * math.ceil(n / tn)
    b = k * n * in_b * math.ceil(m / tm)
    c = m * n * out_b
    return a, b, c


def _cands(limit: int, step: int) -> list[int]:
    out = set()
    v = step
    while v < limit:
        out.add(v)
        v *= 2
    out.add(max(step, math.ceil(limit / step) * step))
    for mult in (3, 5, 6, 12, 24, 48, 96):
        if step * mult <= limit:
            out.add(step * mult)
    return sorted(out)


@functools.lru_cache(maxsize=65536)
def best_gemm_tiling(m: int, n: int, k: int, capacity: int, array: tuple[int, int] = (8, 8),
                     in_b: int = 1, out_b: int = 4, acc_b: int = 4, nbuf: int = 2) -> GemmTiling:
    """Minimum-traffic output-stationary tiling that fits ``capacity`` bytes."""
    best: GemmTiling | None = None
    for tm in _cands(m, array[0]):
        for tn in _cands(n, array[1]):
            for tk in _cands(k, 8):
                fp = gemm_footprint(tm, tn, tk, in_b, acc_b, nbuf)
                if fp > capacity:
                    continue
                a, b, c = gemm_traffic(m, n, k, tm, tn, in_b, out_b)
                t = GemmTiling(tm, tn, tk, fp, a + b + c, a, b, c, True)
                if best is None or (t.dram_bytes, t.footprint_bytes) < (best.dram_bytes, best.footprint_bytes):
                    best = t
    if best is None:  # nothing fits: fall back to array-sized tiles, single buffered
        tm, tn, tk = array[0], array[1], 8
        a, b, c = gemm_traffic(m, n, k, tm, tn, in_b, out_b)
        best = GemmTiling(tm, tn, tk, gemm_footprint(tm, tn, tk, in_b, acc_b, 1), a + b + c, a, b, c, False)
    return best


def gemm_traffic_lower_bound(m: int, n: int, k: int, capacity: int, in_b: int = 1) -> float:
    """Hong-Kung style I/O lower bound ~ 2 M N K / sqrt(S) elements (sanity check)."""
    s = max(capacity // in_b, 1)
    return max(2 * m * n * k / math.sqrt(s) * in_b, (m * k + k * n) * in_b)


@dataclass(frozen=True)
class ConvTiling:
    kt: int
    pt: int
    qt: int
    footprint_bytes: int
    dram_bytes: int
    order: str
    fits: bool


@functools.lru_cache(maxsize=65536)
def best_conv_tiling(n: int, c: int, h: int, w: int, k: int, r: int, s: int, stride: int = 1,
                     pad: int = 0, capacity: int = 256 * 1024, in_b: int = 1, out_b: int = 4,
                     nbuf: int = 2) -> ConvTiling:
    """Direct-convolution tiling over output channels (kt) and output rows/cols.

    Two loop orders are evaluated: input-stationary (each input tile loaded once,
    weights re-streamed per spatial tile) and weight-stationary (weights for kt
    output channels loaded once, inputs re-streamed per channel tile).
    """
    p = (h + 2 * pad - r) // stride + 1
    q = (w + 2 * pad - s) // stride + 1
    best: ConvTiling | None = None
    for kt in sorted({min(k, v) for v in (8, 16, 32, 64, 128, 256, k)}):
        for pt in sorted({min(p, v) for v in (1, 2, 4, 8, 16, 32, p)}):
            for qt in sorted({min(q, v) for v in (8, 16, 32, 64, q)}):
                ih = (pt - 1) * stride + r
                iw = (qt - 1) * stride + s
                in_tile = c * ih * iw * in_b
                w_tile = kt * c * r * s * in_b
                o_tile = kt * pt * qt * 4
                fp = nbuf * (in_tile + w_tile) + o_tile
                if fp > capacity:
                    continue
                n_sp = n * math.ceil(p / pt) * math.ceil(q / qt)
                n_k = math.ceil(k / kt)
                out_bytes = n * k * p * q * out_b
                halo = (ih * iw) / max(pt * stride * qt * stride, 1)
                inputs_once = n * c * h * w * in_b * max(halo, 1.0)
                weights = k * c * r * s * in_b
                t_is = inputs_once + weights * n_sp + out_bytes          # input stationary
                t_ws = weights + inputs_once * n_k + out_bytes           # weight stationary
                for order, t in (("input-stationary", t_is), ("weight-stationary", t_ws)):
                    cand = ConvTiling(kt, pt, qt, fp, int(t), order, True)
                    if best is None or cand.dram_bytes < best.dram_bytes:
                        best = cand
    if best is None:
        best = ConvTiling(8, 1, 8, 0, int((n * c * h * w + k * c * r * s) * in_b * 8 + n * k * p * q * out_b),
                          "spill", False)
    return best
