"""DMA transfer-time models.

* :func:`dma_copy_cycles_analytic` -- closed form (ANALYTICAL):
      rate = min(issue_rate, outstanding / round_trip, memory_rate)  [beats/cycle]
  with issue_rate = B/(B+1) (one scheduling cycle per burst), outstanding =
  min(DFIFO_DEPTH, (DESC_DEPTH+1) * B) beats (Little's law).
* :func:`simulate_dma_copy` -- cycle-level model of one sf_dma_engine moving
  a 1-D buffer (PY_SIMULATION), including SPM bank conflicts between the
  read and write streams of an SPM->SPM copy.
Both are compared with RTL cycle counts by :func:`calibration_table`.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

from memoryflow.provenance import Provenance
from memoryflow.verify.golden import bank_map

# visibility latencies measured from the RTL structure (cycles from request
# acceptance to the beat being usable by the DMA write side)
SPM_READ_VIS = 4          # SPM accept -> rsp FIFO -> DMA data FIFO -> visible
SPM_WRITE_ACK = 3
APB_OVERHEAD = 5          # testbench START write + completion poll granularity


@dataclass(frozen=True)
class DmaEstimate:
    cycles: float
    beats: int
    beats_per_cycle: float
    bound: str
    provenance: Provenance


def dma_copy_cycles_analytic(nbytes: int, burst: int, read_latency: float, beat_bytes: int = 8,
                             dfifo: int = 16, desc_depth: int = 4, mem_rate: float = 1.0,
                             overhead: float = APB_OVERHEAD) -> DmaEstimate:
    beats = math.ceil(nbytes / beat_bytes)
    nb = max(1, min(burst, beats))
    issue = nb / (nb + 1)
    outstanding = min(dfifo, (desc_depth + 1) * nb)
    little = outstanding / max(read_latency + 1, 1)
    rate = min(issue, little, mem_rate)
    bound = "issue" if rate == issue else ("latency" if rate == little else "memory")
    cycles = beats / rate + read_latency + overhead
    return DmaEstimate(cycles, beats, beats / cycles, bound, Provenance.ANALYTICAL)


def simulate_dma_copy(nbytes: int, burst: int, src: str = "spm", dst: str = "spm",
                      ext_latency: int = 20, ext_interval: int = 1, beat_bytes: int = 8,
                      dfifo: int = 16, desc_depth: int = 4, wout: int = 8,
                      spm_banks: int = 4, spm_bank_depth: int = 512, spm_mode: int = 0,
                      src_addr: int = 0, dst_addr: int = 0x2000,
                      overhead: int = APB_OVERHEAD, max_cycles: int = 10_000_000) -> DmaEstimate:
    """Cycle-level model of a single-channel 1-D copy through sf_dma_engine 0."""
    beats = math.ceil(nbytes / beat_bytes)
    rd_vis = SPM_READ_VIS if src == "spm" else ext_latency + 1
    wr_ack = SPM_WRITE_ACK if dst == "spm" else ext_latency
    sched_left = beats
    rs_idle, r_left, r_word = True, 0, src_addr // beat_bytes
    desc: deque[int] = deque()
    reserved = 0
    dfifo_q: deque[int] = deque()       # cycle from which each beat is visible
    inflight_rd: deque[int] = deque()   # arrival cycles of outstanding reads
    ws_idle, w_left, w_word = True, 0, dst_addr // beat_bytes
    acks: deque[int] = deque()
    written = acked = 0
    ext_rd_last = ext_wr_last = -10**9
    spm_prio = [0] * spm_banks
    t = 0
    while acked < beats and t < max_cycles:
        # responses arriving this cycle become visible next cycle
        while inflight_rd and inflight_rd[0] <= t:
            dfifo_q.append(inflight_rd.popleft() + 1)
        while acks and acks[0] <= t:
            acks.popleft()
            acked += 1
        # ---- read-side decision
        rd_issue = False
        sched = False
        if rs_idle:
            if sched_left > 0 and len(desc) < desc_depth:
                sched = True
        elif reserved < dfifo:
            rd_issue = True
        # ---- write-side decision
        wr_issue = False
        desc_pop = False
        if ws_idle:
            desc_pop = len(desc) > 0
        elif dfifo_q and dfifo_q[0] <= t and len(acks) < wout:
            wr_issue = True
        # ---- memory acceptance (SPM bank arbitration between port0/port1)
        if src == "spm" and dst == "spm" and rd_issue and wr_issue:
            br, _ = bank_map(r_word, spm_banks, spm_bank_depth, spm_mode)
            bw, _ = bank_map(w_word, spm_banks, spm_bank_depth, spm_mode)
            if br == bw:
                if (0 - spm_prio[br]) % 2 <= (1 - spm_prio[br]) % 2:
                    wr_issue = False
                    spm_prio[br] = 1
                else:
                    rd_issue = False
                    spm_prio[br] = 0
            else:
                spm_prio[br] = 1
                spm_prio[bw] = 0
        if src == "ext" and rd_issue and t - ext_rd_last < ext_interval:
            rd_issue = False
        if dst == "ext" and wr_issue and t - ext_wr_last < ext_interval:
            wr_issue = False
        # ---- edge updates
        if sched:
            nb = min(burst, sched_left)
            sched_left -= nb
            desc.append(nb)
            rs_idle, r_left = False, nb
        if rd_issue:
            reserved += 1
            inflight_rd.append(t + rd_vis - 1)
            r_word += 1
            r_left -= 1
            if src == "ext":
                ext_rd_last = t
            if r_left == 0:
                rs_idle = True
        if desc_pop and not sched:
            ws_idle, w_left = False, desc.popleft()
        elif desc_pop and sched:
            ws_idle, w_left = False, desc.popleft()
        if wr_issue:
            dfifo_q.popleft()
            reserved -= 1
            acks.append(t + wr_ack)
            written += 1
            w_word += 1
            w_left -= 1
            if dst == "ext":
                ext_wr_last = t
            if w_left == 0:
                ws_idle = True
        t += 1
    cycles = t + 1 + overhead
    return DmaEstimate(cycles, beats, beats / cycles, "simulated", Provenance.PY_SIMULATION)


def calibration_table(rtl_metrics: dict[str, float], ext_latency: int = 20) -> list[dict]:
    """Model vs RTL for the tb_dma burst sweep (4 KiB copies)."""
    rows = []
    for b in (1, 2, 4, 8, 16):
        for kind, src, dst, lat in (("ext2spm", "ext", "spm", ext_latency + 1), ("spm2spm", "spm", "spm", SPM_READ_VIS)):
            key = f"dma_{kind}_4k_burst{b}_cycles"
            if key not in rtl_metrics:
                continue
            rtl = rtl_metrics[key]
            sim = simulate_dma_copy(4096, b, src, dst, ext_latency=ext_latency, dst_addr=0x0 if src == "ext" else 0x2000).cycles
            ana = dma_copy_cycles_analytic(4096, b, lat).cycles
            rows.append({"metric": key, "burst": b, "path": kind, "rtl": rtl, "sim": sim, "analytic": ana,
                         "sim_err_pct": 100 * (sim - rtl) / rtl, "analytic_err_pct": 100 * (ana - rtl) / rtl})
    return rows


def dma_path_bw(beat_bytes: int, clock_hz: float, latency_cycles: float, burst: int = 16,
                dfifo: int = 16, desc_depth: int = 4, onchip_latency: float = 6.0) -> float:
    """Sustained bytes/s one DMA engine can pull from a memory with the given
    round-trip latency (ANALYTICAL, Little's law -- validated against RTL in
    calibration_table).  The bandwidth-delay product of the external memory
    must fit in the DMA's outstanding-beat capacity, otherwise the engine,
    not DRAM, sets the ceiling."""
    nb = max(1, burst)
    issue = nb / (nb + 1)
    outstanding = min(dfifo, (desc_depth + 1) * nb)
    rate = min(issue, outstanding / (latency_cycles + onchip_latency + 1))
    return rate * beat_bytes * clock_hz


def dma_write_bw(beat_bytes: int, clock_hz: float, latency_cycles: float, wout: int = 8,
                 onchip_latency: float = 6.0) -> float:
    """Sustained bytes/s of the DMA WRITE path: at most ``wout`` writes may wait
    for their acknowledgement, so rate <= wout / ack round trip (Little's law).
    Calibrated by tb_sf25_dma_bridge: SPM -> EXT with WOUT = 8 and a 20-cycle
    memory runs at 6.06 B/cycle (model: 8 / 21 x 16 = 6.10)."""
    return min(1.0, wout / (latency_cycles + onchip_latency + 1)) * beat_bytes * clock_hz


def required_outstanding_beats(bw_bytes_s: float, latency_s: float, beat_bytes: int) -> int:
    """Bandwidth-delay product in DMA beats."""
    return math.ceil(bw_bytes_s * latency_s / beat_bytes)
