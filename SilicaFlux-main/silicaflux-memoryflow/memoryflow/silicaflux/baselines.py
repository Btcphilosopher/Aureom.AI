"""SilicaFlux machines MemoryFlow compares against: as built, as documented,
as recommended.

Each :class:`Baseline` is an ordinary :class:`SystemConfig` so the same
roofline / area / energy models evaluate all of them.  Every parameter carries
where it came from:

* ``RTL``       read from the repository RTL (parameter defaults, port widths)
* ``RTL_SIM``   measured by memoryflow.silicaflux.characterise on that RTL
* ``DOC``       stated in a repository design document (doc_targets)
* ``ASSUME``    MemoryFlow assumption (e.g. an external link the RTL lacks)

The as-built machines cannot be synthesised with the repository's proposed
open flow (Yosys 0.33 rejects the SilicaFlux packages; see the inventory), so
their logic area comes from MemoryFlow's Yosys-anchored scaling laws and is
ANALYTICAL.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from memoryflow.models.explore import BUDGETS, Budget, DesignPoint, evaluate
from memoryflow.models.hardware import (EXTMEM_PRESETS, ComputeConfig, DmaConfig, ExtMemConfig,
                                        ScratchpadConfig, SystemConfig)
from memoryflow.models.workloads import default_suite
from memoryflow.silicaflux.characterise import load_results

#: fallbacks used only when no characterisation results exist (values from the
#: shipped reports/data/sf_char_results.json of this release)
_FALLBACK = {
    "sf1_scalar_load_bytes_per_cycle": 1.333, "sf1_vload_bytes_per_cycle": 2.286,
    "sf1_tensor_macs_per_cycle": 0.941,
    "sf25_vector_load_stream_bytes_per_cycle": 15.98, "sf25_tensor_macs_per_cycle": 63.37,
    "sf25_tensor_products_per_cycle_drain1of4": 0.249, "sf25_burst_load_beats_per_cycle_L16": 0.80,
    "sf25_dma_ext_to_spm_bytes_per_cycle": 11.43, "sf25_dma_spm_to_ext_bytes_per_cycle": 6.06,
}


def measured() -> tuple[dict[str, float], str]:
    """All characterisation metrics (flat) and their provenance."""
    res = load_results()
    flat = {k: v for r in res.values() for k, v in r.get("metrics", {}).items()}
    if flat:
        return flat, "RTL_SIM"
    return dict(_FALLBACK), "RTL_SIM (archived)"


@dataclass
class Baseline:
    key: str
    title: str
    kind: str                          # AS-BUILT | INTEGRATED | DOCUMENTED | RECOMMENDED
    cfg: SystemConfig
    budget: Budget
    params: list[tuple[str, str, str]] = field(default_factory=list)   # (item, value, provenance)
    notes: list[str] = field(default_factory=list)


#: the SilicaFlux v1 cluster has no external-memory interface at all; data
#: enters through the chiplet tile interface (8-bit link at the core clock).
SF1_LINK = ExtMemConfig("SF1 chiplet link x8 (no DRAM)", "link", 100, 8, 1, 0.80, 200, 30.0, 0.0, 180,
                        "ASSUME: tile_interface LINK_WIDTH=8 at 100 MHz, 4 beats per 32-bit flit carry "
                        "payload; no external memory controller exists in any SilicaFlux generation")


def silicaflux_v1() -> Baseline:
    m, prov = measured()
    vload = m.get("sf1_vload_bytes_per_cycle", _FALLBACK["sf1_vload_bytes_per_cycle"])
    tmac = m.get("sf1_tensor_macs_per_cycle", _FALLBACK["sf1_tensor_macs_per_cycle"])
    b = BUDGETS["silicaflux-v-65"]
    cfg = SystemConfig(
        ComputeConfig(clock_hz=100e6, cpu_cores=1, cpu_ops_per_cycle=1.0, vec_lanes=4, vec_ops_per_lane=1.0,
                      vec_lane_bits=32, tensor_rows=1, tensor_cols=1, tensor_ops_per_mac=2.0 * tmac,
                      tensor_in_bytes=4, tensor_acc_bytes=4),
        ScratchpadConfig(capacity_bytes=1024, banks=1, bank_width_bits=32, ports=1, ecc="none",
                         interleave="modulo", port_efficiency=vload / 4.0),
        DmaConfig(burst_beats=4, dfifo_depth=1, desc_depth=0, beat_bytes=4, channels=1, engines=1, wout=1),
        SF1_LINK, 65, "SilicaFlux v1 cluster", tiles=4)
    return Baseline("sf1", "SilicaFlux v1 cluster (as built)", "AS-BUILT", cfg, b, [
        ("clock", "100 MHz", "RTL (synth/silicaflux.sdc period 10 ns)"),
        ("tiles", "4", "RTL (silicaflux_pkg NUM_TILES)"),
        ("SPM per tile", "1 KiB (256 x 32 b), one FSM port", "RTL (SRAM_DEPTH=256)"),
        ("SPM -> engine", f"{vload:.2f} B/cycle per tile (VLOAD)", prov),
        ("vector", "4 x 32-bit lanes per tile", "RTL (LANES_DEFAULT=4, XLEN=32)"),
        ("tensor", f"{tmac:.2f} MAC/cycle per tile (sequential 4x4, 32-bit)", prov),
        ("external memory", "none; chiplet link x8", "RTL + ASSUME (link rate)"),
        ("node", "65 nm (evaluated at the SilicaFlux-V node)", "DOC"),
    ], ["DFLOAD/DFSTORE bursts > 4 words are defective (tb_sf1_memctrl); modelled as 4-word bursts.",
        "The SPM is written by two always_ff blocks (2 writes/cycle measured): no single-port macro "
        "can implement it as written."])


def silicaflux_25_tile(integrated: bool = False) -> Baseline:
    """The Gen-2.5 tile as its in-repo RTL defines it (one tile, 200 MHz)."""
    m, prov = measured()
    vport = m.get("sf25_vector_load_stream_bytes_per_cycle", _FALLBACK["sf25_vector_load_stream_bytes_per_cycle"])
    tmac = m.get("sf25_tensor_macs_per_cycle", _FALLBACK["sf25_tensor_macs_per_cycle"])
    drain = 64.0 * m.get("sf25_tensor_products_per_cycle_drain1of4",
                         _FALLBACK["sf25_tensor_products_per_cycle_drain1of4"])
    b = BUDGETS["silicaflux-v-65"]
    em = EXTMEM_PRESETS["DDR3-1600 x16"] if integrated else EXTMEM_PRESETS["QSPI 104 MHz (no DRAM)"]
    cfg = SystemConfig(
        ComputeConfig(clock_hz=200e6, cpu_cores=1, cpu_ops_per_cycle=1.0, vec_lanes=4, vec_ops_per_lane=1.0,
                      vec_lane_bits=32, tensor_rows=4, tensor_cols=4, tensor_depth=4,
                      tensor_ops_per_mac=2.0 * tmac / 64.0, tensor_dataflow="block",
                      tensor_drain_bytes_per_cycle=drain),
        ScratchpadConfig(capacity_bytes=64 * 1024, banks=8, bank_width_bits=128, ports=3, ecc="parity",
                         interleave="modulo", port_efficiency=vport / 16.0),
        DmaConfig(burst_beats=16, dfifo_depth=16, desc_depth=0 if not integrated else 4, beat_bytes=16,
                  channels=2, engines=2, wout=8),
        em, 65, "SilicaFlux 2.5 tile" + (" + MemoryFlow DMA" if integrated else ""))
    params = [
        ("clock", "200 MHz", "DOC (03-11-26 update p.7, p.9)"),
        ("SPM", "64 KiB = 8 banks x 512 x 128 b, 3 requesters", "RTL (memory_controller.sf defaults)"),
        ("SPM -> engine", f"{vport:.2f} B/cycle (vector port)", prov),
        ("tensor", f"4x4x4 INT8 block, {tmac:.1f} MAC/cycle, no accumulation buffer", prov + " + RTL"),
        ("tensor result drain", f"{drain:.1f} B/cycle (one 128-bit VRF write port)", "RTL (VRF_WR_PORTS=1) + " + prov),
        ("vector", "4 x 32-bit lanes", "RTL (vector_engine.sf LANES=4)"),
    ]
    if integrated:
        params += [("DMA", "MemoryFlow sf_dma via sf_mc25_vport_bridge", "RTL_SIM (tb_sf25_dma_bridge)"),
                   ("external memory", "DDR3-1600 x16", "ASSUME (MemoryFlow preset)")]
        title, kind = "SilicaFlux 2.5 tile + MemoryFlow DMA + DDR3", "INTEGRATED"
    else:
        params += [("external memory", "none: burst port with no DMA engine; QSPI-class host link", "RTL + ASSUME")]
        title, kind = "SilicaFlux 2.5 tile (as built)", "AS-BUILT"
    return Baseline("sf25_int" if integrated else "sf25", title, kind, cfg, b, params,
                    ["compute_tile.sf does not elaborate (interface drift); the tile is assembled here from "
                     "the units that do: memory_controller.sf, tensor_unit.sf, vector_engine.sf, register_bank.sf."])


def silicaflux_v_documented(no_dram: bool = True) -> Baseline:
    b = BUDGETS["silicaflux-v-65"]
    em = EXTMEM_PRESETS["QSPI 104 MHz (no DRAM)"] if no_dram else EXTMEM_PRESETS["DDR3-1600 x16"]
    cfg = SystemConfig(
        ComputeConfig(clock_hz=200e6, cpu_cores=1, cpu_ops_per_cycle=1.0, vec_lanes=4, vec_ops_per_lane=2.0,
                      vec_lane_bits=32, tensor_rows=4, tensor_cols=4),
        ScratchpadConfig(capacity_bytes=256 * 1024, banks=4, bank_width_bits=64, ports=3, ecc="none",
                         interleave="modulo"),
        DmaConfig(burst_beats=16, dfifo_depth=16, beat_bytes=8, wout=8), em, 65,
        "SilicaFlux-V (documented)")
    return Baseline("sfv_doc" if no_dram else "sfv_doc_dram",
                    "SilicaFlux-V documented target" + (" (no DRAM)" if no_dram else " + DDR3"),
                    "DOCUMENTED", cfg, b, [
                        ("node / clock", "65 nm / 200 MHz", "DOC (reduced-ASIC p.3; update p.7)"),
                        ("on-chip SRAM", "256 KiB (L2 as scratchpad, 32K x 64 b)", "DOC (reduced-ASIC p.1, p.7)"),
                        ("vector", "4 lanes, 128-bit", "DOC (update p.7-8)"),
                        ("tensor", "4x4 INT8 MAC", "DOC (update p.8)"),
                        ("external memory", "none (code/data on chip)" if no_dram else "DDR3-1600 x16",
                         "DOC (reduced-ASIC p.1)" if no_dram else "ASSUME"),
                        ("DMA / banking", "not specified; MemoryFlow defaults (4 banks x 64 b)", "ASSUME"),
                    ])


def all_baselines() -> list[Baseline]:
    return [silicaflux_v1(), silicaflux_25_tile(False), silicaflux_25_tile(True),
            silicaflux_v_documented(True), silicaflux_v_documented(False)]


def evaluate_baseline(b: Baseline, suite=None) -> DesignPoint:
    return evaluate(b.cfg, suite or default_suite(), b.budget)


def with_budget(b: Baseline, budget: Budget) -> Baseline:
    return replace(b, budget=budget, cfg=replace(b.cfg, node_nm=budget.node_nm))
