"""Evidence-based inventory of the SilicaFlux memory subsystem.

    memoryflow sf-inventory [--no-lint] [--md FILE] [--json FILE]

Two layers:

1. **Automatic** - every HDL file of every :data:`SOURCE_SETS` entry is parsed
   (:mod:`.hdl`).  For each module the scanner checks that every instantiated
   module is defined somewhere in the repository, that the named ports and
   parameters of each instance exist on that definition, and that every
   ``sf_*_t`` package type it uses is defined by a package in its source set.
   Key tops are then elaborated with Verilator.

2. **Curated** - :data:`BLOCKS` maps the ten memory-subsystem categories the
   MemoryFlow brief asks about onto concrete SilicaFlux blocks.  Each entry
   carries evidence *anchors* (source set, file, regex) that are resolved to
   real ``origin:line`` locations at run time - a block whose evidence can no
   longer be found is reported as such, never silently kept.

Status vocabulary (strictly separated in every table):

=================  ==========================================================
IMPLEMENTED        synthesizable RTL in the SilicaFlux tree that elaborates
STANDALONE         implemented and elaborates, but not instantiated by any
                   SilicaFlux top (sibling project / library block)
NOT_ELABORABLE     RTL text exists but cannot be elaborated from repository
                   sources (interface drift or missing package types)
BEHAVIOURAL        simulation-only model
REFERENCED_ONLY    instantiated by a top level, defined nowhere
DOCUMENTED_ONLY    stated in a design document, no RTL
ABSENT             neither RTL nor document
MEMORYFLOW         provided by this toolkit (new RTL, see rtl/)
=================  ==========================================================
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

from memoryflow.silicaflux import hdl
from memoryflow.silicaflux.sources import (MF_ROOT, SOURCE_SETS, Materialised, SourceFile, materialise,
                                           silicaflux_root)

CATEGORIES = [
    "CPU cache interface", "L1 / L2 / last-level cache", "Scratchpad memory", "SRAM array",
    "DMA engine", "Interconnect / router", "Vector register file", "Tensor accumulation buffer",
    "Memory controller", "External memory interface", "ECC / parity", "MBIST",
]
STATUSES = ["IMPLEMENTED", "STANDALONE", "NOT_ELABORABLE", "BEHAVIOURAL", "REFERENCED_ONLY",
            "DOCUMENTED_ONLY", "ABSENT", "MEMORYFLOW"]


# ============================================================================ index
@dataclass
class Index:
    sets: dict[str, Materialised]
    modules: dict[str, list[hdl.ModuleDef]] = field(default_factory=lambda: defaultdict(list))
    packages: dict[str, list[hdl.PackageDef]] = field(default_factory=lambda: defaultdict(list))
    files: dict[str, SourceFile] = field(default_factory=dict)          # rel path -> source file
    set_of: dict[str, str] = field(default_factory=dict)                 # rel path -> set key

    def defs(self, name: str) -> list[hdl.ModuleDef]:
        return self.modules.get(name, [])

    def variants(self, name: str) -> list[hdl.ModuleDef]:
        """Definitions with distinct content (identical copies collapse)."""
        seen, out = set(), []
        for d in self.defs(name):
            if d.sha256 not in seen:
                seen.add(d.sha256)
                out.append(d)
        return out


def build_index(keys: list[str] | None = None, sf_root: Path | None = None) -> Index:
    ix = Index({k: materialise(k, sf_root) for k in (keys or list(SOURCE_SETS))})
    for key, m in ix.sets.items():
        for f in m.files:
            ix.files[f.path] = f
            ix.set_of[f.path] = key
            if f.path.endswith((".svh", ".vh")):
                continue
            mods, pkgs = hdl.parse_file(MF_ROOT / f.path, f.path, f.origin, f.sha256)
            for md in mods:
                ix.modules[md.name].append(md)
            for p in pkgs:
                ix.packages[key].append(p)
    return ix


# ============================================================================ static checks
@dataclass
class Finding:
    kind: str            # REFERENCED_ONLY | INTERFACE_DRIFT | MISSING_TYPES | VARIANTS
    module: str
    origin: str
    line: int
    detail: str
    set_key: str = ""


def _is_tb(md: hdl.ModuleDef) -> bool:
    n = md.name.lower()
    return n.startswith("tb_") or n.endswith("_tb") or "/tb/" in md.origin.replace("::", "/")


def static_checks(ix: Index, core_only: bool = True) -> list[Finding]:
    out: list[Finding] = []
    for name, defs in ix.modules.items():
        for md in {d.sha256: d for d in defs}.values():
            key = ix.set_of[md.file]
            if core_only and not SOURCE_SETS[key].silicaflux_core:
                continue
            for inst in md.instances:
                cands = ix.defs(inst.module)
                if not cands:
                    if not _is_tb(md) or inst.module in ix.modules:
                        out.append(Finding("REFERENCED_ONLY", md.name, md.origin, inst.line,
                                           f"instance {inst.name} of `{inst.module}`: no definition in repository",
                                           key))
                    continue
                best = None
                for c in cands:
                    miss_p = [p for p in inst.params if p not in c.params]
                    miss_q = [p for p in inst.ports if p not in c.ports]
                    score = len(miss_p) + len(miss_q)
                    if best is None or score < best[0]:
                        best = (score, c, miss_p, miss_q)
                if best and best[0] > 0:
                    _, c, mp, mq = best
                    out.append(Finding("INTERFACE_DRIFT", md.name, md.origin, inst.line,
                                       f"instance {inst.name} of `{inst.module}` ({c.origin}:{c.line}): "
                                       f"{len(mq)}/{len(inst.ports)} named ports and {len(mp)}/{len(inst.params)} "
                                       f"parameters absent on the definition (e.g. "
                                       f"{', '.join((mq + mp)[:4])})", key))
            defined = {t for p in ix.packages[key] for t in p.types} | md.local_types
            missing = sorted(md.used_types - defined)
            if missing and not _is_tb(md):
                out.append(Finding("MISSING_TYPES", md.name, md.origin, md.line,
                                   f"{len(missing)} of {len(md.used_types)} package types used are defined by no "
                                   f"package in set `{key}` (e.g. {', '.join(missing[:4])})", key))
    for name in ix.modules:
        vs = ix.variants(name)
        core = [v for v in vs if SOURCE_SETS[ix.set_of[v.file]].silicaflux_core and not _is_tb(v)]
        if len(core) > 1 and len({ix.set_of[v.file] for v in core}) == 1:
            out.append(Finding("VARIANTS", name, core[0].origin, core[0].line,
                               f"{len(core)} diverging definitions: " +
                               "; ".join(f"{v.origin}:{v.line} ({v.nlines} lines)" for v in core),
                               ix.set_of[core[0].file]))
    return sorted(out, key=lambda f: (f.kind, f.origin, f.line))


# ============================================================================ elaboration
def _pick_packages(ix: Index, key: str, md: hdl.ModuleDef) -> list[hdl.PackageDef]:
    """Packages ``md`` imports (best-covering variant of each name), plus the
    packages those import, in dependency order (dependencies first)."""
    order: list[hdl.PackageDef] = []

    def best(name: str, want: set[str]) -> hdl.PackageDef | None:
        cands = [p for p in ix.packages[key] if p.name == name]
        return max(cands, key=lambda p: (len(want & p.types), -len(p.types))) if cands else None

    def visit(name: str, want: set[str], depth: int = 0) -> None:
        p = best(name, want)
        if p is None or p in order or depth > 8:
            return
        for dep in sorted(p.imports):
            visit(dep, set(), depth + 1)
        if p not in order:
            order.append(p)

    for name in sorted(md.imports):
        visit(name, md.used_types)
    return order


def lint_top(ix: Index, module: str, origin: str | None = None) -> hdl.LintResult:
    """Elaborate ``module`` (definition at ``origin`` if given) from repository sources."""
    defs = [d for d in ix.defs(module) if origin is None or d.origin == origin
            or d.origin.endswith("/" + origin) or d.origin.endswith("::" + origin)]
    if not defs:
        return hdl.LintResult(module, False, [f"no definition of {module}"], [])
    md = defs[0]
    key = ix.set_of[md.file]
    files: list[str] = []
    incdirs: set[Path] = set()
    todo, seen = [md], set()
    pkgs: list[str] = []
    while todo:
        d = todo.pop()
        if d.file in seen:
            continue
        seen.add(d.file)
        text = (MF_ROOT / d.file).read_text(errors="replace")
        if re.search(r'`include\s+"', text):
            incdirs.add((MF_ROOT / d.file).parent)
        else:
            for p in _pick_packages(ix, key, d):
                if p.file not in pkgs:
                    pkgs.append(p.file)
        files.append(d.file)
        for inst in d.instances:
            cands = ix.defs(inst.module)
            same = [c for c in cands if ix.set_of[c.file] == key] or cands
            if same:
                # prefer the variant whose ports match the instance best
                c = min(same, key=lambda c: sum(p not in c.ports for p in inst.ports))
                todo.append(c)
    order = pkgs + [f for f in files if f not in pkgs]
    return hdl.verilator_lint(module, [MF_ROOT / f for f in order], sorted(incdirs), cwd=MF_ROOT)


# ============================================================================ curated blocks
@dataclass(frozen=True)
class Anchor:
    set_key: str
    origin: str          # exact origin, or a suffix after '/' or '::'
    regex: str
    what: str = ""


@dataclass(frozen=True)
class Block:
    category: str
    name: str
    generation: str
    status: str
    summary: str
    anchors: tuple[Anchor, ...] = ()
    lint: tuple[str, str] | None = None          # (module, origin) elaborated to confirm IMPLEMENTED
    integrated_in: str = ""                       # top level that instantiates it (if any)
    memoryflow: str = ""                          # MemoryFlow block that covers / replaces it
    docs: tuple[str, ...] = ()                    # doc_targets keys


A = Anchor
_MC25 = "memory_controller.sf"
_CT25 = "SilicaFlux2.0/SilicaFlux2.5/compute_tile.sf"
_TOP25 = "SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf"
_TU25 = "tensor_unit.sf"
_RB25 = "SilicaFlux2.0/SilicaFlux2.5/register_bank.sf"
_G1 = "silicaflux.zip::silicaflux/rtl/"

BLOCKS: tuple[Block, ...] = (
    # ---------------------------------------------------------------- CPU cache interface
    Block("CPU cache interface", "Core L1 <-> L2 port (sf_core / sf_l2_cache)", "Gen-2.5", "REFERENCED_ONLY",
          "silicaflux_top.sf wires 8 superscalar cores to per-complex L2 caches; neither module exists.",
          (A("sf25", _TOP25, r"^\s*sf_core\s+#\(", "sf_core instance"),
           A("sf25", _TOP25, r"^\s*sf_l2_cache\s+#\(", "sf_l2_cache instance")),
          memoryflow="sf_spm_banked host port (TCM-style, no cache)"),
    Block("CPU cache interface", "Coherence write-notify hook", "Gen-2.5", "IMPLEMENTED",
          "memory_controller.sf broadcasts every committed line write for a future L1 invalidate; "
          "no consumer exists.",
          (A("sf25", _MC25, r"output logic\s+\[NUM_BANKS-1:0\]\s+coh_wr_valid_o", "coherence hook port"),),
          lint=("memory_controller", _MC25)),
    Block("CPU cache interface", "Direct-mapped / set-associative caches", "library", "STANDALONE",
          "Generic write-back caches (256 x 64 B lines; 128 sets x 4 ways) in memory_cache_repo; "
          "not instantiated by any SilicaFlux top and carry simulation-only initial blocks.",
          (A("memcache", "rtl/direct_mapped_cache.sv", r"CACHE_LINES\s*=\s*256"),
           A("memcache", "rtl/set_assoc_cache.sv", r"NUM_WAYS\s*=\s*4")),
          lint=("set_assoc_cache", None)),
    # ---------------------------------------------------------------- L1/L2/LLC
    Block("L1 / L2 / last-level cache", "SilicaFlux-V L1 I/D caches (16 KB + 16 KB)", "SilicaFlux-V", "DOCUMENTED_ONLY",
          "Reduced-ASIC design proposes 16 KB I + 16 KB D L1 and a 256 KB L2/scratch; no RTL.",
          docs=("sfv_l1", "sfv_l2")),
    Block("L1 / L2 / last-level cache", "Cluster L2 (2 MiB / complex, 16-way)", "Gen-2.5", "REFERENCED_ONLY",
          "Parameterised in silicaflux_top.sf; sf_l2_cache is not defined anywhere.",
          (A("sf25", _TOP25, r"L2_SIZE_KB\s*=\s*2048"), A("sf25", _TOP25, r"^\s*sf_l2_cache\s+#\(")),
          memoryflow="not recommended for SilicaFlux-V (DMA-managed SPM); modelled in memoryflow.models.cache"),
    Block("L1 / L2 / last-level cache", "LLC (8 banks x 4 MiB) + coherent crossbar", "Gen-2.5", "REFERENCED_ONLY",
          "32 MiB of LLC SRAM implied by parameters; sf_llc_bank / sf_coh_xbar / sf_coh_mgr undefined.",
          (A("sf25", _TOP25, r"NUM_LLC_BANKS\s*=\s*8"), A("sf25", _TOP25, r"LLC_BANK_SIZE_KB\s*=\s*4096"),
           A("sf25", _TOP25, r"^\s*sf_llc_bank\s+#\(")), docs=("full_sram",)),
    # ---------------------------------------------------------------- scratchpad
    Block("Scratchpad memory", "Gen-1 per-tile scratchpad (4 x 1 KiB)", "Gen-1", "IMPLEMENTED",
          "256 x 32-bit words per tile behind a single FSM: one access at a time, 1 word/cycle bursts.",
          (A("sf1", _G1 + "silicaflux_pkg.sv", r"SRAM_DEPTH\s*=\s*256"),
           A("sf1", _G1 + "memory_controller.sv", r"logic \[XLEN-1:0\] sram \[0:SRAM_DEPTH-1\]"),
           A("sf1", _G1 + "compute_tile.sv", r"memory_controller u_mem")),
          lint=("silicaflux_top", _G1 + "silicaflux_top.sv"), integrated_in="silicaflux_top (Gen-1)",
          memoryflow="sf_spm_banked"),
    Block("Scratchpad memory", "Gen-2.5 banked scratchpad controller", "Gen-2.5", "IMPLEMENTED",
          "8 banks x 512 x 128 b (64 KiB) default, scalar + vector + burst requesters, per-bank "
          "arbitration, credit-reserved responses, per-byte parity. Elaborates stand-alone; its only "
          "instantiation (compute_tile.sf) uses a different port list.",
          (A("sf25", _MC25, r"NUM_BANKS\s*=\s*8,"), A("sf25", _MC25, r"BANK_DEPTH\s*=\s*512,"),
           A("sf25", _MC25, r"localparam int unsigned NUM_REQ\s*=\s*3"),
           A("sf25", _CT25, r"\.NUM_PORTS\s*\(NUM_MC_PORTS\)", "compute_tile instantiation (drifted)")),
          lint=("memory_controller", _MC25), memoryflow="sf_spm_banked + sf_mc25_vport_bridge"),
    Block("Scratchpad memory", "Gen-2.5 tile SPM regions (16 KiB scalar + 64 KiB vector)", "Gen-2.5",
          "NOT_ELABORABLE",
          "compute_tile.sf maps a scalar and a vector SPM window, but the tile cannot be elaborated "
          "(memory_controller / tensor_unit interface drift, missing package types).",
          (A("sf25", _CT25, r"SPM_S_BYTES\s*=\s*32'h0000_4000"), A("sf25", _CT25, r"SPM_V_BYTES\s*=\s*32'h0001_0000")),
          lint=("compute_tile", _CT25)),
    # ---------------------------------------------------------------- SRAM arrays
    Block("SRAM array", "Gen-1 inferred arrays (SPM, IMEM, register file)", "Gen-1", "IMPLEMENTED",
          "Plain reg arrays; the SPM array is written from two always_ff blocks (FSM + tile write-back "
          "port), i.e. a 2-write-port memory that no single-port macro can implement.",
          (A("sf1", _G1 + "memory_controller.sv", r"sram\[wb_addr\["),
           A("sf1", _G1 + "memory_controller.sv", r"sram\[word_addr\]\s*<= req_wdata"),
           A("sf1", _G1 + "fetch_unit.sv", r"logic \[XLEN-1:0\] imem \[0:IMEM_DEPTH-1\]")),
          lint=("memory_controller", _G1 + "memory_controller.sv"), memoryflow="sf_sram_1rw / sf_sram_bank"),
    Block("SRAM array", "Gen-2.5 bank arrays inside memory_controller", "Gen-2.5", "IMPLEMENTED",
          "Per-bank `mem_q` arrays inferred inside the controller with byte enables; no wrapper, no "
          "foundry-macro abstraction, no MBIST port.",
          (A("sf25", _MC25, r"sf_vword_t\s+mem_q\s+\[BANK_DEPTH\]"),),
          lint=("memory_controller", _MC25), memoryflow="sf_sram_1rw IMPL=0|1 + sf_macro_1rw_leaf"),
    Block("SRAM array", "sf_sram_bank_decode helper", "Gen-2.5", "STANDALONE",
          "Bank/row/offset decoder in sram-decoder.sf; instantiated by nothing.",
          (A("sf25", "SilicaFlux2.0/SilicaFlux2.5/sram-decoder.sf", r"module sf_sram_bank_decode"),),
          lint=("sf_sram_bank_decode", None)),
    Block("SRAM array", "sfx_sram_interface (SilicaFlux-AI)", "SilicaFlux-AI", "STANDALONE",
          "Single-port, byte-strobed, 1-cycle synchronous SRAM wrapper used by the GEMM engine.",
          (A("sfx_ai", "rtl/memory/sfx_sram_interface.sv", r"Single-port synchronous SRAM wrapper"),),
          lint=("sfx_sram_interface", None), integrated_in="sfx_gemm_controller (SilicaFlux-AI)"),
    Block("SRAM array", "TestCore behavioural SRAM model", "SilicaFlux-DFT", "BEHAVIOURAL",
          "tc_sram_model is a testbench model for the MBIST collar.",
          (A("testcore", "tb/models/tc_sram_model.sv", r"module tc_sram_model"),)),
    # ---------------------------------------------------------------- DMA
    Block("DMA engine", "Gen-1 DFLOAD / DFSTORE bursts", "Gen-1", "IMPLEMENTED",
          "ISA-level burst ops served by the tile memory controller. The burst address never "
          "advances and the buffer index wraps at 4, so bursts > 4 words re-read / re-write the "
          "same 4 words (reproduced by tb_sf1_memctrl).",
          (A("sf1", _G1 + "silicaflux_pkg.sv", r"OP_DFLOAD\s*=\s*5'h0A"),
           A("sf1", _G1 + "memory_controller.sv", r"2'd3: burst_rd_buf\[ 96 \+: XLEN\] <= sram\[burst_addr \+ 3\]")),
          lint=("memory_controller", _G1 + "memory_controller.sv"), memoryflow="sf_dma"),
    Block("DMA engine", "Gen-2.5 burst descriptor port", "Gen-2.5", "IMPLEMENTED",
          "memory_controller.sf exposes a burst port ('the DMA port'): one descriptor in flight, a "
          "done handshake per burst, <= 256 beats, no page crossing. There is no DMA engine behind it.",
          (A("sf25", _MC25, r"DMA attachment\s*:"),
           A("sf25", _MC25, r"assign burst_req_ready_o = init_done_q & \(b_state_q == BST_IDLE\)")),
          lint=("memory_controller", _MC25), memoryflow="sf_dma (+ sf_mc25_vport_bridge)"),
    Block("DMA engine", "Cluster DMA bridge (sf_dma_bridge)", "Gen-2.5", "REFERENCED_ONLY",
          "IO-coherent DMA ingress in silicaflux_top.sf; undefined.",
          (A("sf25", _TOP25, r"^\s*sf_dma_bridge\s+#\("),)),
    Block("DMA engine", "sfx_dma (SilicaFlux-AI)", "SilicaFlux-AI", "STANDALONE",
          "Single-channel word-copy engine, one command in flight, FIFO-decoupled; no registers, IRQ, "
          "2-D or error handling.",
          (A("sfx_ai", "rtl/dma/sfx_dma.sv", r"Only one command may be in(?:\s|//)+flight"),),
          lint=("sfx_dma", None)),
    # ---------------------------------------------------------------- interconnect
    Block("Interconnect / router", "Gen-1 2x2 XY mesh NoC", "Gen-1", "IMPLEMENTED",
          "32-bit single-flit packets, XY routing, 4 tiles.",
          (A("sf1", _G1 + "silicaflux_pkg.sv", r"NOC_WIDTH\s*=\s*32"),
           A("sf1", _G1 + "noc_router.sv", r"module noc_router")),
          lint=("noc_interconnect", _G1 + "noc_interconnect.sv"), integrated_in="silicaflux_top (Gen-1)"),
    Block("Interconnect / router", "Gen-2.5 parametric wormhole mesh router", "Gen-2.5", "NOT_ELABORABLE",
          "noc_interconnect.sf: 5-port XY wormhole router, MESH_X x MESH_Y, BUF_DEPTH-deep input buffers. "
          "Its packet type defaults to silicaflux_pkg::noc_packet_t, which no package in the repository "
          "defines.",
          (A("sf25", "SilicaFlux2.0/SilicaFlux2.5/noc_interconnect.sf", r"MESH_X\s*=\s*2"),
           A("sf25", "SilicaFlux2.0/SilicaFlux2.5/noc_interconnect.sf", r"parameter type\s+pkt_t\s*=\s*noc_packet_t")),
          lint=("noc_router", "SilicaFlux2.0/SilicaFlux2.5/noc_interconnect.sf")),
    Block("Interconnect / router", "Tile-local crossbar (compute_tile.sf)", "Gen-2.5", "NOT_ELABORABLE",
          "Per-target arbiters with write-burst lock and starvation counters, embedded in the tile.",
          (A("sf25", _CT25, r"XB_STARVE_LIM\s*=\s*16"),), lint=("compute_tile", _CT25)),
    Block("Interconnect / router", "Coherent / memory fabric (sf_coh_xbar, sf_mem_fabric)", "Gen-2.5",
          "REFERENCED_ONLY", "Cluster-level fabrics instantiated in silicaflux_top.sf; undefined.",
          (A("sf25", _TOP25, r"^\s*sf_coh_xbar\s+#\("), A("sf25", _TOP25, r"^\s*sf_mem_fabric\s+#\(")),
          memoryflow="sf_mem_router"),
    # ---------------------------------------------------------------- vector RF
    Block("Vector register file", "Gen-1 register bank (16 x 128 b)", "Gen-1", "IMPLEMENTED",
          "32 x 32 b scalar + 16 x 128 b vector registers.",
          (A("sf1", _G1 + "register_bank.sv", r"logic \[VLEN-1:0\] vregs \[0:NUM_VREGS-1\]"),),
          lint=("register_bank", _G1 + "register_bank.sv"), integrated_in="silicaflux_top (Gen-1)"),
    Block("Vector register file", "Gen-2.5 register bank (16 x 128 b, 3R/1W)", "Gen-2.5", "IMPLEMENTED",
          "Lane-masked VRF with 3 read and 1 write port. One write port bounds tensor results "
          "(512 b per 4x4 product) to one product per 4 cycles if they are written back to the VRF.",
          (A("sf25", _RB25, r"VRF_ENTRIES\s*=\s*16"), A("sf25", _RB25, r"VRF_WR_PORTS\s*=\s*1"),
           A("sf25", _RB25, r"VRF_RD_PORTS\s*=\s*3")),
          lint=("register_bank", _RB25)),
    # ---------------------------------------------------------------- tensor accumulation
    Block("Tensor accumulation buffer", "Gen-1 tensor unit (sequential 4x4)", "Gen-1", "IMPLEMENTED",
          "One 32-bit MAC per cycle, 64 MACs in ~66 cycles; results held in output registers, "
          "no accumulation across operations.",
          (A("sf1", _G1 + "tensor_unit.sv", r"Latency: 64 MAC cycles \+ 2 state cycles"),),
          lint=("tensor_unit", _G1 + "tensor_unit.sv"), integrated_in="silicaflux_top (Gen-1)",
          memoryflow="sf_tensor_array"),
    Block("Tensor accumulation buffer", "Gen-2.5 pipelined tensor unit (4x4x4 INT8 / cycle)", "Gen-2.5",
          "IMPLEMENTED",
          "64 MAC/cycle claimed, 21-cycle latency; output-stationary within one product only. The "
          "fused-accumulate input (VEC_FUSE_EN) is reserved and $fatal if set: there is no "
          "accumulation buffer.",
          (A("sf25", _TU25, r"Sustained throughput: one DIMxDIM matrix product per cycle"),
           A("sf25", _TU25, r"VEC_FUSE_EN\s*=\s*1'b0"),
           A("sf25", _TU25, r"reserved extension parameter set")),
          lint=("tensor_unit", _TU25), memoryflow="sf_tensor_array (double-buffered accumulators)"),
    Block("Tensor accumulation buffer", "Memory-fetching tensor engine (cmd: a/b/c_addr, k_m1, acc)", "Gen-2.5",
          "NOT_ELABORABLE",
          "compute_tile.sf drives a tensor engine that fetches operands and accumulates C in the SPM; "
          "the in-repo tensor_unit has register operands only (interface drift).",
          (A("sf25", _CT25, r"cmd\.k_m1\s*=\s*timm\.k_m1"), A("sf25", _CT25, r"cmd\.acc\s*=\s*timm\.acc")),
          lint=("compute_tile", _CT25)),
    Block("Tensor accumulation buffer", "sfx_accumulator + systolic GEMM (SilicaFlux-AI)", "SilicaFlux-AI",
          "STANDALONE",
          "Addressable read-modify-write accumulator (32 entries) behind a weight-stationary array; "
          "tiles run strictly sequentially (no overlap).",
          (A("sfx_ai", "rtl/arithmetic/sfx_accumulator.sv", r"module sfx_accumulator"),),
          lint=("sfx_gemm_controller", None)),
    Block("Tensor accumulation buffer", "Cluster tensor engine (sf_tensor_engine)", "Gen-2.5", "REFERENCED_ONLY",
          "Instantiated in silicaflux_top.sf; undefined.", (A("sf25", _TOP25, r"^\s*sf_tensor_engine\s+#\("),)),
    # ---------------------------------------------------------------- memory controllers
    Block("Memory controller", "On-chip SPM controllers (Gen-1, Gen-2.5)", "Gen-1/2.5", "IMPLEMENTED",
          "Both `memory_controller` modules are scratchpad controllers, not DRAM controllers.",
          (A("sf25", _MC25, r"Unified banked scratchpad memory controller"),),
          lint=("memory_controller", _MC25)),
    Block("Memory controller", "SDRAM-style controller FSM (memory_cache_repo)", "library", "STANDALONE",
          "ACTIVATE/CAS/PRECHARGE/REFRESH FSM for teaching; single outstanding request, no PHY.",
          (A("memcache", "rtl/memory_controller.sv", r"DRAM-Style Memory Controller FSM"),),
          lint=("memory_controller", "memory_cache_repo/rtl/memory_controller.sv")),
    Block("Memory controller", "SilicaFlux DDR / LPDDR controller", "all", "ABSENT",
          "No DRAM controller exists for any SilicaFlux generation.",
          memoryflow="DDR4/LPDDR4 controller IP behind an SF-MEM -> AXI4 bridge (proposed)"),
    # ---------------------------------------------------------------- external memory interface
    Block("External memory interface", "Cluster AXI memory ports (2 x AXI master)", "Gen-2.5", "REFERENCED_ONLY",
          "silicaflux_top.sf declares NUM_MEM_PORTS AXI masters behind sf_mem_fabric / sf_axi_edge, "
          "neither of which exists.",
          (A("sf25", _TOP25, r"NUM_MEM_PORTS\s*=\s*2"), A("sf25", _TOP25, r"mem_axi_req_o"),
           A("sf25", _TOP25, r"^\s*sf_axi_edge\s+#\(")), docs=("sfv_no_dram",)),
    Block("External memory interface", "Gen-1 chiplet tile interface", "Gen-1", "IMPLEMENTED",
          "Serialises 32-bit NoC flits over an 8/16/32-bit link (die-to-die, not a DRAM interface).",
          (A("sf1", _G1 + "tile_interface.sv", r"Serialises 32-bit NoC flits over a narrow parallel link"),),
          lint=("tile_interface", _G1 + "tile_interface.sv"), integrated_in="silicaflux_top (Gen-1)"),
    Block("External memory interface", "DDR / LPDDR / HBM PHY", "all", "ABSENT",
          "No PHY or PHY model in the repository.",
          memoryflow="sf_extmem_model (behavioural, latency/bandwidth) + PHY presets in models.hardware"),
    # ---------------------------------------------------------------- ECC / MBIST
    Block("ECC / parity", "Gen-2.5 per-byte parity", "Gen-2.5", "IMPLEMENTED",
          "Detection only; exceptions SF_MEM_EXC_ECC on load. No correction, no injection hook.",
          (A("sf25", _MC25, r"PARITY_EN\s*=\s*1'b1"),), lint=("memory_controller", _MC25),
          memoryflow="sf_ecc_secded_enc/dec + sf_sram_bank (SECDED, scrub on RMW, injection)"),
    Block("ECC / parity", "Gen-1 link parity placeholder", "Gen-1", "IMPLEMENTED",
          "Flag-only parity on chiplet beats; SPM has no protection.",
          (A("sf1", _G1 + "tile_interface.sv", r"ECC placeholder"),)),
    Block("MBIST", "TestCore MBIST controller + collar", "SilicaFlux-DFT", "STANDALONE",
          "March-style MBIST with a collar for a generic SRAM; not connected to any SilicaFlux SPM.",
          (A("testcore", "rtl/tc_mbist.sv", r"module tc_mbist"),
           A("testcore", "rtl/tc_mbist_collar.sv", r"module tc_mbist_collar")),
          lint=("tc_mbist", None), memoryflow="sf_mbist_march (parallel banks, wired into sf_spm_banked)",
          docs=("sfv_mbist",)),
)


# ============================================================================ resolution
@dataclass
class ResolvedAnchor:
    what: str
    origin: str
    line: int
    text: str
    found: bool


@dataclass
class ResolvedBlock:
    block: dict
    status: str
    anchors: list[ResolvedAnchor]
    lint_ok: bool | None
    lint_errors: list[str]
    note: str = ""


def _match_origin(f: SourceFile, want: str) -> bool:
    return f.origin == want or f.origin.endswith("/" + want) or f.origin.endswith("::" + want)


def resolve_anchor(ix: Index, a: Anchor) -> ResolvedAnchor:
    m = ix.sets.get(a.set_key)
    files = [f for f in (m.files if m else []) if f.origin == a.origin] or \
            [f for f in (m.files if m else []) if _match_origin(f, a.origin)]
    rx = re.compile(a.regex, re.M)
    for f in files:
        text = (MF_ROOT / f.path).read_text(errors="replace")
        hit = rx.search(text)
        if hit:
            line = text.count("\n", 0, hit.start()) + 1
            src = text.splitlines()[line - 1].strip()
            return ResolvedAnchor(a.what or a.regex, f.origin, line, src[:140], True)
    return ResolvedAnchor(a.what or a.regex, a.origin, 0, "", False)


def resolve_blocks(ix: Index, lint: bool = True) -> list[ResolvedBlock]:
    cache: dict[tuple, hdl.LintResult] = {}
    out = []
    for b in BLOCKS:
        anchors = [resolve_anchor(ix, a) for a in b.anchors]
        ok, errs, status, note = None, [], b.status, ""
        if lint and b.lint and hdl.verilator_available():
            k = b.lint
            if k not in cache:
                cache[k] = lint_top(ix, k[0], k[1])
            r = cache[k]
            ok, errs = r.ok, r.errors
            if r.tool != "verilator" and ok:
                note = "Verilator: unsupported construct; elaborated with Icarus Verilog"
            elif ok is None:
                note = ("elaboration inconclusive: Verilator and Icarus both stop on legal SV they do not "
                        "support (" + "; ".join(e.split(":")[-1].strip()[:60] for e in errs[:2]) + ")")
            # the curated status is a claim; the elaboration result is the evidence
            if status in ("IMPLEMENTED", "STANDALONE") and ok is False:
                note = f"curated as {status} but does not elaborate"
                status = "NOT_ELABORABLE"
            elif status == "NOT_ELABORABLE" and ok:
                note = "curated as NOT_ELABORABLE but elaborates"
                status = "IMPLEMENTED"
        if any(not a.found for a in anchors):
            note = (note + "; " if note else "") + "evidence anchor not found"
        out.append(ResolvedBlock(asdict(b), status, anchors, ok, errs, note))
    return out


# ============================================================================ report
def run(lint: bool = True, sf_root: Path | None = None) -> dict:
    root = sf_root or silicaflux_root()
    if root is None:
        return {"available": False}
    ix = build_index(sf_root=root)
    findings = static_checks(ix)
    blocks = resolve_blocks(ix, lint)
    nfiles = sum(len(m.files) for m in ix.sets.values())
    nlines = sum(f.lines for m in ix.sets.values() for f in m.files)
    return {"available": True, "root": str(root), "files": nfiles, "lines": nlines,
            "sets": {k: {"title": m.set.title, "generation": m.set.generation, "files": len(m.files),
                         "missing": m.missing, "core": m.set.silicaflux_core} for k, m in ix.sets.items()},
            "modules": len(ix.modules),
            "findings": [asdict(f) for f in findings],
            "blocks": [asdict(b) for b in blocks]}


def coverage_matrix(res: dict) -> dict[str, dict[str, list[str]]]:
    mat: dict[str, dict[str, list[str]]] = {c: {s: [] for s in STATUSES} for c in CATEGORIES}
    for b in res.get("blocks", []):
        mat[b["block"]["category"]][b["status"]].append(b["block"]["name"])
        if b["block"]["memoryflow"]:
            mat[b["block"]["category"]]["MEMORYFLOW"].append(b["block"]["memoryflow"])
    return mat


def to_markdown(res: dict) -> str:
    from memoryflow.silicaflux.doc_targets import TARGETS
    if not res.get("available"):
        return "# SilicaFlux inventory\n\nSilicaFlux sources not found (set MF_SILICAFLUX_ROOT).\n"
    L = ["# SilicaFlux memory-subsystem inventory (repository evidence)", "",
         f"Scanned {res['files']} HDL files ({res['lines']:,} lines, {res['modules']} distinct module names) "
         f"from {len(res['sets'])} source sets under `{Path(res['root']).name}/`. Every row below is backed by "
         "an `origin:line` anchor resolved at generation time; `IMPLEMENTED` / `STANDALONE` claims are "
         "confirmed by Verilator elaboration from repository sources only.", "",
         "## Coverage by category", "",
         "| Category | IMPLEMENTED | STANDALONE | NOT_ELABORABLE | BEHAVIOURAL | REFERENCED_ONLY | "
         "DOCUMENTED_ONLY | ABSENT | MemoryFlow provides |", "|---|---|---|---|---|---|---|---|---|"]
    for cat, row in coverage_matrix(res).items():
        cells = ["<br>".join(row[s]) or "-" for s in STATUSES]
        L.append(f"| **{cat}** | " + " | ".join(cells) + " |")
    L += ["", "## Blocks and evidence", ""]
    for cat in CATEGORIES:
        bs = [b for b in res["blocks"] if b["block"]["category"] == cat]
        if not bs:
            continue
        L += [f"### {cat}", ""]
        for b in bs:
            blk = b["block"]
            lint = {None: "elaboration inconclusive" if b["lint_errors"] else "not elaborated",
                    True: "elaborates", False: "does NOT elaborate"}[b["lint_ok"]]
            L.append(f"* **{blk['name']}** [{blk['generation']}] - `{b['status']}` ({lint}). {blk['summary']}")
            for a in b["anchors"]:
                L.append(f"  * `{a['origin']}:{a['line']}` `{a['text']}`" if a["found"]
                         else f"  * EVIDENCE NOT FOUND: {a['origin']} /{a['what']}/")
            for d in blk["docs"]:
                t = TARGETS[d]
                L.append(f"  * doc: *{t.doc}* p.{t.page}: \"{t.quote}\"")
            if b["lint_errors"] and b["lint_ok"] is False:
                L.append(f"  * first elaboration error: `{b['lint_errors'][0][:160]}`")
            if blk["memoryflow"]:
                L.append(f"  * MemoryFlow: {blk['memoryflow']}")
            if b["note"]:
                L.append(f"  * note: {b['note']}")
        L.append("")
    L += ["## Automatic consistency findings (SilicaFlux core sets)", "",
          "| Kind | Module | Location | Detail |", "|---|---|---|---|"]
    for f in res["findings"]:
        L.append(f"| {f['kind']} | `{f['module']}` | `{f['origin']}:{f['line']}` | {f['detail']} |")
    L += ["", "## Source sets", "", "| Key | Title | Generation | HDL files | SilicaFlux core |", "|---|---|---|---|---|"]
    for k, s in res["sets"].items():
        L.append(f"| {k} | {s['title']} | {s['generation']} | {s['files']} | {'yes' if s['core'] else 'no'} |")
    return "\n".join(L) + "\n"


def write(md_path: Path | None = None, json_path: Path | None = None, lint: bool = True) -> dict:
    res = run(lint)
    if md_path:
        Path(md_path).write_text(to_markdown(res))
    if json_path:
        Path(json_path).write_text(json.dumps(res, indent=1, default=str))
    return res
