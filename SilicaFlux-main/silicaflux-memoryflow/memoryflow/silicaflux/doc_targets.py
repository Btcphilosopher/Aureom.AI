"""Targets stated in the SilicaFlux design documents (with page citations).

These are the *documented* requirements MemoryFlow is asked to balance
against.  They are inputs (provenance DOCUMENTED), not results.  Where two
documents disagree, both are recorded and the conflict is reported instead
of silently picking one.

:func:`verify_quotes` re-reads the PDFs with ``pdftotext`` (when installed)
and checks that every quote really is on the cited page.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from memoryflow.silicaflux.sources import silicaflux_root

REDUCED = "SilicaFlux-V_ Reduced-ASIC Prototype Design.pdf"
UPDATE = "SilicaFlux2.0/SilicaFlux2.5/SilicaFlux_Update 03-11-26.pdf"
NODES = "Process Node Comparison for SilicaFlux‑V.pdf"
RESEARCH = "SilicaFlux2.0/SilicaFlux2.5/SilicaFlux Codebase Research Report.pdf"


@dataclass(frozen=True)
class Target:
    key: str
    doc: str
    page: int
    quote: str               # verbatim (whitespace-normalised) text on that page
    value: object = None
    unit: str = ""
    applies_to: str = "SilicaFlux-V"


TARGETS: dict[str, Target] = {t.key: t for t in [
    Target("sfv_perf", REDUCED, 1, "~20 MIPS at 100 MHz", 100e6, "Hz"),
    Target("sfv_die", REDUCED, 1, "<10 mm² die", 10.0, "mm2"),
    Target("sfv_power", REDUCED, 1, "<1 W)", 1.0, "W"),
    Target("sfv_cores", REDUCED, 1, "Reduce from 8 cores to 1 core", 1, "cores"),
    Target("sfv_l1", REDUCED, 1, "16 KB I + 16 KB D L1 caches", 16 * 1024, "B per cache"),
    Target("sfv_l2", REDUCED, 1, "256 KB L2 block (acting as a scratchpad)", 256 * 1024, "B"),
    Target("sfv_no_dram", REDUCED, 1, "we suggest no external DRAM", None, ""),
    Target("sfv_no_vector", REDUCED, 1, "no vector unit", None, ""),
    Target("sfv_node", REDUCED, 3, "We lean toward 65 nm as a sweet spot; 130 nm is a fallback", 65, "nm"),
    Target("sfv_l2_macro", REDUCED, 7, "32K * 64 * bitcell_area (~0.12 µm² each at 65 nm) ≈ 0.5 mm²",
           0.5, "mm2"),
    Target("sfv_mbist", REDUCED, 9, "For each SRAM macro, include a built-in self-test (BIST)", None, ""),
    Target("full_sram", REDUCED, 3, "36 Mb (full SilicaFlux)", 36 * 2**20 // 8, "B", "full SilicaFlux"),
    Target("upd_params", UPDATE, 7, "4 lanes, 128-bit width, 200 MHz", 200e6, "Hz"),
    Target("upd_soc", UPDATE, 8, "four-vector lane SIMD unit, 4×4 INT8 MAC tensor unit, and ~256 KiB of on-chip SRAM",
           256 * 1024, "B"),
    Target("upd_clock", UPDATE, 9, "200 MHz CPU clock", 200e6, "Hz"),
    Target("node_65", NODES, 3, "65 nm emerges as the best compromise for SilicaFlux‑V", 65, "nm"),
    Target("node_130", NODES, 3, "130 nm is a solid fallback", 130, "nm"),
    Target("research_tensor_lat", RESEARCH, 1, "documented latency in source is about 66 cycles", 66, "cycles",
           "Gen-1"),
]}

#: Documented disagreements the reports must surface.
CONFLICTS = [
    ("vector/tensor units", "sfv_no_vector", "upd_soc",
     "The reduced-ASIC plan drops vector/tensor units for first silicon; the 03-11-26 update specifies a "
     "4-lane SIMD unit and a 4x4 INT8 tensor unit. MemoryFlow evaluates both and recommends the latter "
     "only where the memory system can feed it."),
    ("clock", "sfv_perf", "upd_params",
     "100 MHz (reduced-ASIC) vs 200 MHz (update). MemoryFlow uses 200 MHz at 65 nm and 100 MHz at 130 nm."),
    ("SRAM density", "sfv_l2_macro", None,
     "The 0.12 um^2 / 65 nm bitcell (0.5 mm^2 for 256 KB) is ~4x denser than published 65 nm high-density "
     "6T cells (~0.5 um^2); MemoryFlow's area model uses the published value, so 256 KiB costs ~1.5 mm^2 "
     "at 65 nm including macro periphery (about 3x the documented estimate)."),
]


def _norm(s: str) -> str:
    s = s.replace("‑", "-").replace("×", "x").replace("≈", "~")
    return re.sub(r"\s+", " ", s).strip()


def verify_quotes(root: Path | None = None) -> dict[str, bool | None]:
    """key -> True (found on page) / False (not found) / None (pdf or tool unavailable)."""
    root = root or silicaflux_root()
    out: dict[str, bool | None] = {}
    if root is None or not shutil.which("pdftotext"):
        return {k: None for k in TARGETS}
    pages: dict[tuple[str, int], str] = {}
    for k, t in TARGETS.items():
        pdf = root / t.doc
        if not pdf.exists():
            out[k] = None
            continue
        key = (t.doc, t.page)
        if key not in pages:
            r = subprocess.run(["pdftotext", "-f", str(t.page), "-l", str(t.page), "-layout", str(pdf), "-"],
                               capture_output=True, text=True)
            pages[key] = _norm(r.stdout)
        out[k] = _norm(t.quote) in pages[key]
    return out
