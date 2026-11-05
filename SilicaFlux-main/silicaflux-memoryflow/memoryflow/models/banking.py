"""Scratchpad banking: address maps, conflict models and banking maps.

* :func:`simulate_spm` is a cycle-level Python model of ``sf_spm_banked``
  (per-bank round-robin arbitration, per-port credits with the RTL's 4-cycle
  credit round trip).  Its output is PY_SIMULATION and is calibrated against
  the RTL testbench measurements in :func:`calibration_table`.
* :func:`expected_random_throughput` is the closed-form ANALYTICAL estimate
  (expected number of distinct banks touched by P uniform requests).
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, Sequence

from memoryflow.provenance import Provenance
from memoryflow.verify.golden import bank_map

MODES = {"modulo": 0, "xor": 1, "block": 2}

# accept -> credit returned (cycles): accept(t), bank s1(t+1), bank rsp reg(t+2),
# FIFO visible(t+3) popped at end of t+3 -> slot reusable at t+4.
CREDIT_ROUND_TRIP = 4


@dataclass(frozen=True)
class SpmSimResult:
    cycles: int
    accepted: int
    throughput: float            # accepted requests per cycle (all ports)
    per_port: tuple[int, ...]
    conflict_cycles: int
    provenance: Provenance = Provenance.PY_SIMULATION


def simulate_spm(streams: Sequence[Sequence[int]], nbanks: int, bank_depth: int, mode: str = "modulo",
                 rsp_depth: int = 4, max_cycles: int = 10_000_000) -> SpmSimResult:
    """Run per-port word-address streams through a model of sf_spm_banked.

    The run ends when every port has issued its whole stream (the RTL
    testbench measures the same interval).
    """
    nports = len(streams)
    m = MODES[mode] if isinstance(mode, str) else mode
    heads = [0] * nports
    outstanding = [0] * nports
    returns: dict[int, list[int]] = {}
    prio = [0] * nbanks
    accepted = [0] * nports
    conflicts = 0
    t = 0
    total = sum(len(s) for s in streams)
    while sum(accepted) < total and t < max_cycles:
        for p in returns.pop(t, []):
            outstanding[p] -= 1
        req: dict[int, list[int]] = {}
        for p in range(nports):
            if heads[p] < len(streams[p]) and outstanding[p] < rsp_depth:
                b, _ = bank_map(streams[p][heads[p]], nbanks, bank_depth, m)
                req.setdefault(b, []).append(p)
        if any(len(v) > 1 for v in req.values()):
            conflicts += 1
        for b, ps in req.items():
            winner = min(ps, key=lambda p: (p - prio[b]) % nports)
            prio[b] = (winner + 1) % nports
            heads[winner] += 1
            accepted[winner] += 1
            outstanding[winner] += 1
            returns.setdefault(t + CREDIT_ROUND_TRIP, []).append(winner)
        t += 1
    return SpmSimResult(t, sum(accepted), sum(accepted) / max(t, 1), tuple(accepted), conflicts)


def stride_streams(nports: int, n: int, stride: int, capacity_words: int,
                   bases: Sequence[int] = (0, 37, 101, 211)) -> list[list[int]]:
    return [[(bases[p] + i * stride) % capacity_words for i in range(n)] for p in range(nports)]


def random_streams(nports: int, n: int, capacity_words: int, seed: int = 1) -> list[list[int]]:
    rng = random.Random(seed)
    return [[rng.randrange(capacity_words) for _ in range(n)] for _ in range(nports)]


def hot_streams(nports: int, n: int, nbanks: int, bank_depth: int, mode: str, seed: int = 2) -> list[list[int]]:
    rng = random.Random(seed)
    cap = nbanks * bank_depth
    out = []
    m = MODES[mode]
    for _ in range(nports):
        s = []
        while len(s) < n:
            w = rng.randrange(cap)
            if bank_map(w, nbanks, bank_depth, m)[0] == 0:
                s.append(w)
        out.append(s)
    return out


def expected_random_throughput(nports: int, nbanks: int) -> float:
    """E[# distinct banks] for nports independent uniform requests (ANALYTICAL)."""
    return nbanks * (1.0 - (1.0 - 1.0 / nbanks) ** nports)


def banking_map(nwords: int, nbanks: int, bank_depth: int, mode: str) -> list[tuple[int, int, int]]:
    """(word, bank, index) for the first ``nwords`` words -- for banking-map figures."""
    m = MODES[mode]
    return [(w, *bank_map(w, nbanks, bank_depth, m)) for w in range(nwords)]


def stride_conflict_matrix(nbanks_list: Sequence[int], strides: Sequence[int], mode: str,
                           nports: int = 3, n: int = 256, bank_depth: int = 256) -> dict[tuple[int, int], float]:
    """Simulated throughput for each (banks, stride) pair."""
    out = {}
    for nb in nbanks_list:
        for s in strides:
            r = simulate_spm(stride_streams(nports, n, s, nb * bank_depth), nb, bank_depth, mode)
            out[(nb, s)] = r.throughput
    return out


def calibration_table(rtl_metrics: dict[str, dict[str, float]]) -> list[dict]:
    """Compare the Python SPM model against RTL measurements.

    ``rtl_metrics`` maps an RTL test name (spm_mod, spm_xor, spm_block_8b,
    spm_rsp2) to its MF_METRIC dictionary.
    """
    setups: dict[str, tuple[int, str, int]] = {
        "spm_mod": (4, "modulo", 4), "spm_xor": (4, "xor", 4),
        "spm_block_8b": (8, "block", 4), "spm_rsp2": (4, "modulo", 2),
    }
    rows = []
    bd = 256
    for test, metrics in rtl_metrics.items():
        if test not in setups:
            continue
        nb, mode, rd = setups[test]
        cap = nb * bd
        cases: list[tuple[str, Callable[[], SpmSimResult]]] = [
            (f"spm_stride{s}_throughput",
             (lambda s=s: simulate_spm(stride_streams(3, 512, s, cap), nb, bd, mode, rd)))
            for s in (1, 2, 4, 8, 16)
        ]
        cases.append(("spm_random3_throughput",
                      lambda: simulate_spm(random_streams(3, 2000, cap), nb, bd, mode, rd)))
        cases.append(("spm_single_port_throughput",
                      lambda: simulate_spm([list(range(1024))], nb, bd, mode, rd)))
        cases.append(("spm_hotbank_throughput",
                      lambda: simulate_spm(hot_streams(3, 600, nb, bd, mode), nb, bd, mode, rd)))
        for key, fn in cases:
            if key not in metrics:
                continue
            sim = fn().throughput
            rtl = metrics[key]
            rows.append({"test": test, "metric": key, "rtl": rtl, "model": sim,
                         "error_pct": 100.0 * (sim - rtl) / rtl if rtl else 0.0,
                         "analytic": (expected_random_throughput(3, nb) if "random" in key else None)})
    return rows
