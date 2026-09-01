"""
Synthetic multi-core mining simulator (section 29).

Models exactly the nonce-search scheme implemented in rtl/nonce/
nonce_allocator.sv + rtl/top/hash_core_array.sv (core i searches
nonce_start + i*stride, +NUM_CORES*stride, ...; every core advances in
lockstep; whichever core matches first wins), using the Python golden
model for the actual hashing (not the RTL -- this is a fast, pure-Python
architectural simulator for exploring many scenarios quickly, distinct
from the RTL simulation in silicaflux_bitcoin.simulate).

Uses an ARTIFICIALLY EASY target by design (section 29/42) -- this
module is a research/verification tool, not a network miner, and must
never be pointed at real Bitcoin network difficulty (see section 29's
explicit warning against implying network profitability).

Timing reported by run() is clearly split:
  wall_clock_seconds     -- how long this Python simulation itself took.
  simulated_hw_seconds    -- a THEORETICAL estimate of how long the
                             *hardware* would take, using the RTL-
                             simulation-measured cycles/hash figure from
                             performance_model.py and an assumed clock.
                             This is NOT a hardware measurement.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from silicaflux_bitcoin.reference import block_header as bh
from silicaflux_bitcoin.benchmarks.performance_model import MEASURED_CYCLES_PER_HASH_ITERATIVE


@dataclass
class MiningResult:
    found: bool
    winning_core: int | None
    nonce: int | None
    hash_hex: str | None
    trials_per_core: list[int]
    total_hashes: int
    wall_clock_seconds: float
    simulated_hw_seconds: float
    simulated_hw_hashrate: float


@dataclass
class MiningSimulator:
    header: bh.BlockHeader
    num_cores: int = 4
    nonce_start: int = 0
    nonce_stride: int = 1
    target: int = 0
    clock_mhz: float = 100.0
    cycles_per_hash: int = MEASURED_CYCLES_PER_HASH_ITERATIVE

    def run(self, max_trials_per_core: int = 100_000) -> MiningResult:
        if self.target <= 0:
            raise ValueError("target must be > 0 (an unreachable/zero target would never finish)")

        step = self.nonce_stride * self.num_cores
        nonces = [(self.nonce_start + i * self.nonce_stride) & 0xFFFFFFFF for i in range(self.num_cores)]
        trials = [0] * self.num_cores

        t0 = time.monotonic()
        winner_core = winner_nonce = winner_hash = None
        for _ in range(max_trials_per_core):
            for c in range(self.num_cores):
                h = self.header.with_nonce(nonces[c])
                ph = h.pow_hash()
                trials[c] += 1
                if bh.target_meets(ph, self.target):
                    winner_core, winner_nonce, winner_hash = c, nonces[c], ph
                    break
                nonces[c] = (nonces[c] + step) & 0xFFFFFFFF
            if winner_core is not None:
                break
        wall = time.monotonic() - t0

        total_hashes = sum(trials)
        # Every core runs the same number of trials by the time any one
        # wins (lockstep, section 8) -- matches hash_core_array.sv's
        # total_hashes_completed semantics exactly (see
        # generate_vectors.py:gen_hash_core_array_vectors).
        if winner_core is not None:
            total_hashes = self.num_cores * trials[winner_core]

        sim_seconds = (total_hashes * self.cycles_per_hash) / (self.clock_mhz * 1e6)
        sim_hashrate = total_hashes / sim_seconds if sim_seconds > 0 else 0.0

        return MiningResult(
            found=winner_core is not None,
            winning_core=winner_core,
            nonce=winner_nonce,
            hash_hex=(bh.to_display_hex(winner_hash) if winner_hash else None),
            trials_per_core=trials,
            total_hashes=total_hashes,
            wall_clock_seconds=wall,
            simulated_hw_seconds=sim_seconds,
            simulated_hw_hashrate=sim_hashrate,
        )
