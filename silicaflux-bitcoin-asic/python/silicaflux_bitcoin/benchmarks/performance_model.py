"""
Performance model for the SilicaFlux Bitcoin SHA-256 miner (section 35).

Every number here is tagged with exactly one of five categories, and the
categories are never mixed in one computation (section 35's rule):

  THEORETICAL       -- pure formula (clock_freq / cycles_per_hash * cores),
                        no simulation run.
  RTL SIMULATION     -- an actual measured value from an Icarus Verilog run
                        of this project's RTL (cycle counts, pass/fail
                        counts). See MEASURED_CYCLES_PER_HASH_ITERATIVE
                        below and its provenance comment.
  SYNTHESIS ESTIMATE -- from an actual yosys/verilator run against this
                        RTL (cell counts, lint-clean status). See
                        python/silicaflux_bitcoin/optimisation/
                        design_space_explore.py and reports/synthesis_*.
  POST-LAYOUT ESTIMATE, SILICON MEASUREMENT -- NOT AVAILABLE. This
                        project has neither a place-and-route flow nor
                        fabricated silicon; any function that would
                        require either raises NotImplementedError rather
                        than fabricating a plausible-looking number.
"""
from __future__ import annotations

from dataclasses import dataclass

# RTL SIMULATION (measured): cycles from `start` to `done` on
# sha256_double_hash.sv in use_midstate=1 mode -- the exact path
# hash_core.sv drives for every nonce trial after the first. Measured
# directly via Icarus Verilog simulation during this project's
# benchmarking pass (see reports/cycle_measurement.txt); NOT a
# theoretical formula. The theoretical figure would be 2 blocks * 64
# rounds = 128 cycles; the extra 4 cycles are FSM handoff overhead
# between sha256_double_hash's BLOCK2/DIGEST states and the compressor's
# own IDLE/RUN entry, also directly observed rather than guessed.
MEASURED_CYCLES_PER_HASH_ITERATIVE = 132

# THEORETICAL only (no midstate reuse, no FSM overhead modelled): the
# textbook "2 blocks x 64 rounds" figure, kept only for comparison against
# the measured value above -- see docs/architecture.md section 13.
THEORETICAL_CYCLES_PER_HASH_NAIVE = 128

# RTL SIMULATION (measured): sha256_pipeline.sv's per-block-compression
# latency is PIPELINE_DEPTH+1 cycles (see rtl/pipeline/sha256_pipeline.sv
# and tb/integration/tb_sha256_pipeline.sv, verified at all 7 supported
# depths), but -- per hash_core.sv's documented scoping decision -- this
# design does not ship a multi-nonce-in-flight streaming integration of
# it, so there is no measured or even fully-designed "cycles per full
# double-hash search trial" figure for the pipelined architecture. Only
# its per-block streaming THROUGHPUT (a property of the verified,
# standalone module) is modelled below; do not read
# pipelined_block_throughput_per_sec() as a mining hashrate.


@dataclass(frozen=True)
class HashrateEstimate:
    category: str            # "THEORETICAL" or "RTL SIMULATION"
    architecture: str
    num_cores: int
    clock_mhz: float
    cycles_per_hash: int
    hashes_per_sec: float
    hashes_per_joule: float | None = None  # only set if a power assumption was explicitly given


def iterative_array_hashrate(num_cores: int, clock_mhz: float,
                              cycles_per_hash: int = MEASURED_CYCLES_PER_HASH_ITERATIVE,
                              power_watts: float | None = None) -> HashrateEstimate:
    """Hashrate for the architecture actually integrated and simulated in
    this project (hash_core_array.sv of `num_cores` ITERATIVE cores,
    section 7/8), at an assumed clock frequency. clock_mhz is a
    THEORETICAL target frequency -- this project ran no timing analysis
    against a real technology library, so achievable Fmax on real silicon
    is unknown (see docs/architecture.md). cycles_per_hash defaults to
    the RTL-simulation-measured value above, but the resulting
    hashes_per_sec is still THEORETICAL overall because clock_mhz itself
    is an assumption, not a measurement.
    """
    if num_cores < 1 or clock_mhz <= 0:
        raise ValueError("num_cores and clock_mhz must be positive")
    hashes_per_core = (clock_mhz * 1e6) / cycles_per_hash
    total = num_cores * hashes_per_core
    hpj = (total / power_watts) if power_watts else None
    return HashrateEstimate("THEORETICAL", "ITERATIVE array", num_cores, clock_mhz,
                             cycles_per_hash, total, hpj)


def pipelined_block_throughput_per_sec(clock_mhz: float) -> float:
    """THEORETICAL steady-state block-COMPRESSION throughput (not full
    double-hash search throughput -- see module docstring) of one
    sha256_pipeline.sv instance: one new block accepted per clock cycle
    in steady state, independent of PIPELINE_DEPTH (only latency depends
    on depth, verified in tb_sha256_pipeline.sv). This is a property of
    the standalone, independently-verified pipeline module, not a mining
    hashrate for this project's shipped miner_top.sv.
    """
    if clock_mhz <= 0:
        raise ValueError("clock_mhz must be positive")
    return clock_mhz * 1e6


def cycles_to_seconds(cycles: int, clock_mhz: float) -> float:
    return cycles / (clock_mhz * 1e6)


def post_layout_estimate(*args, **kwargs):
    raise NotImplementedError(
        "No place-and-route flow was run in this project -- there is no post-layout "
        "timing/area/power data to report. See docs/architecture.md's category rules."
    )


def silicon_measurement(*args, **kwargs):
    raise NotImplementedError(
        "This design has not been fabricated -- there is no silicon measurement to report."
    )
