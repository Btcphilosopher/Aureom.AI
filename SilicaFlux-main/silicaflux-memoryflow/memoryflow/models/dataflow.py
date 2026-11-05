"""Accelerator data-movement models: double buffering, tiling pipelines,
operand reuse, register blocking, producer/consumer stalls and deadlock.

* :func:`pipeline_sim`       discrete-event load/compute/store pipeline with N
                             buffers (PY_SIMULATION)
* :func:`pipeline_analytic`  closed-form makespan (ANALYTICAL)
* :func:`tensor_tiles_cycles` sf_tensor_array cycles for back-to-back tiles
                             (ANALYTICAL; compared with RTL in tb_accel)
* :func:`joined_stream_deadlock` deadlock predicate for two operand streams
                             delivered by one burst-serial producer
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from memoryflow.provenance import Provenance


@dataclass(frozen=True)
class PipelineResult:
    makespan: float
    compute_busy: float
    utilisation: float
    load_stall: float          # compute idle waiting for operands
    buffer_stall: float        # load idle waiting for a free buffer
    provenance: Provenance


def pipeline_sim(tiles: int, t_load: float, t_compute: float, t_store: float = 0.0,
                 nbuf: int = 2) -> PipelineResult:
    """Three-stage pipeline (DMA load -> compute -> DMA store) with nbuf tile buffers.

    A tile buffer is held from the start of its load until its store finishes
    (in-place output).  Loads and stores overlap because SilicaFlux's DMA has
    independent MM2S and S2MM engines.
    """
    if nbuf < 1:
        raise ValueError("nbuf >= 1")
    load_end = [0.0] * tiles
    comp_end = [0.0] * tiles
    store_end = [0.0] * tiles
    load_stall = buffer_stall = 0.0
    for i in range(tiles):
        free_at = store_end[i - nbuf] if i >= nbuf else 0.0
        prev_load = load_end[i - 1] if i else 0.0
        start_load = max(prev_load, free_at)
        buffer_stall += max(0.0, free_at - prev_load)
        load_end[i] = start_load + t_load
        prev_comp = comp_end[i - 1] if i else 0.0
        start_comp = max(prev_comp, load_end[i])
        load_stall += max(0.0, load_end[i] - prev_comp)
        comp_end[i] = start_comp + t_compute
        prev_store = store_end[i - 1] if i else 0.0
        store_end[i] = max(prev_store, comp_end[i]) + t_store
    makespan = store_end[-1] if tiles else 0.0
    busy = tiles * t_compute
    return PipelineResult(makespan, busy, busy / makespan if makespan else 0.0, load_stall,
                          buffer_stall, Provenance.PY_SIMULATION)


def pipeline_analytic(tiles: int, t_load: float, t_compute: float, t_store: float = 0.0,
                      nbuf: int = 2) -> float:
    if nbuf == 1:
        return tiles * (t_load + t_compute + t_store)
    bottleneck = max(t_load, t_compute, t_store)
    return t_load + t_compute + t_store + (tiles - 1) * bottleneck


def tensor_tiles_cycles(k: int, tiles: int, tr: int = 8, tc: int = 8, accw: int = 32, dw: int = 64,
                        dbuf: bool = True, fill: int | None = None) -> float:
    """Cycles for ``tiles`` back-to-back K-step tiles with saturated inputs/outputs.

    drain = TR*TC*ACCW/DW beats; with accumulator double-buffering the array
    overlaps drain(n) with compute(n+1): per tile max(K, drain); otherwise K + drain.
    """
    drain = tr * tc * accw // dw
    if fill is None:                 # skid-buffer/pipeline fill observed in RTL
        fill = 1 if dbuf else 3
    per_tile = max(k, drain) if dbuf else k + drain
    return k + drain + (tiles - 1) * per_tile + fill if dbuf else tiles * per_tile + fill


def tensor_mac_utilisation(k: int, tiles: int, dbuf: bool = True, **kw) -> float:
    return k * tiles / tensor_tiles_cycles(k, tiles, dbuf=dbuf, **kw)


def operand_bytes_per_mac(tr: int, tc: int, in_bytes: int = 1) -> float:
    """Outer-product register blocking: (TR + TC) operand bytes per TR*TC MACs."""
    return (tr + tc) * in_bytes / (tr * tc)


def vector_register_blocking_ai(block: int, elem_bytes: int = 2) -> float:
    """AI of a blocked matrix-vector product on the vector unit: each loaded
    element of x is reused ``block`` times from registers."""
    return 2.0 * block / ((block + 1) * elem_bytes)


def joined_stream_deadlock(fifo_depth: int, burst_beats: int, sequenced: bool = False) -> bool:
    """True if two joined operand streams fed by one in-order DMA engine can deadlock.

    The engine delivers bursts serially.  If the consumer needs one beat of
    BOTH streams to make progress, a burst of stream A can only complete when
    A's input FIFO absorbs the whole burst (the matching B beats are queued
    behind it).  Deadlock-free iff fifo_depth >= burst_beats, or the operand
    streams are sequenced (B completely loaded before A starts).
    """
    return (not sequenced) and fifo_depth < burst_beats


def min_fifo_for_joined_streams(burst_beats: int) -> int:
    return burst_beats


def reuse_traffic_factor(m: int, tm: int, replay: int) -> float:
    """B-operand SPM/DMA traffic reduction from the reuse buffer."""
    return float(min(replay, math.ceil(m / tm)))
