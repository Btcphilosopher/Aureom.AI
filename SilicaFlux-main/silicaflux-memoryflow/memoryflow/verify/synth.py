"""Yosys logic synthesis of the MemoryFlow RTL (synthesizability + gate counts).

Each wrapper in ``syn/syn_wrappers.sv`` is synthesised with the generic Yosys
flow (``synth -flatten``) against the foundry-macro BLACKBOX, so the reported
cells are logic only.  Generic cells are converted to NAND2-equivalent gates
(GE) with conventional weights; :mod:`memoryflow.models.area` turns GE into
mm^2 for a chosen node.  This is an ANALYTICAL estimate (no timing-driven
mapping, no placement) -- good to +/-30 % for comparing configurations, not a
sign-off number.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

from memoryflow.provenance import Provenance

REPO = Path(__file__).resolve().parents[2]

# NAND2-equivalent weights for Yosys internal gate-level cells
GE_WEIGHTS: dict[str, float] = {
    "$_NOT_": 0.67, "$_BUF_": 1.0, "$_AND_": 1.33, "$_NAND_": 1.0, "$_OR_": 1.33,
    "$_NOR_": 1.0, "$_XOR_": 2.33, "$_XNOR_": 2.33, "$_ANDNOT_": 1.33, "$_ORNOT_": 1.33,
    "$_MUX_": 2.33, "$_NMUX_": 2.33, "$_AOI3_": 1.33, "$_OAI3_": 1.33, "$_AOI4_": 1.67,
    "$_OAI4_": 1.67,
}
FF_GE = 5.33          # D flip-flop (with reset ~ 6); flops counted separately
FF_PREFIXES = ("$_DFF", "$_SDFF", "$_DFFE", "$_SDFFE", "$_ALDFF", "$_DLATCH", "$_SR", "$_DFFSR")

WRAPPERS = ["syn_ecc64", "syn_router2", "syn_vec4x16", "syn_tensor_8x8", "syn_dma",
            "syn_spm_256k", "syn_memflow_top"]


@dataclass
class SynthResult:
    top: str
    ok: bool
    cells: dict[str, int] = field(default_factory=dict)
    flops: int = 0
    comb_ge: float = 0.0
    total_ge: float = 0.0
    macros: int = 0
    log: str = ""
    provenance: str = Provenance.ANALYTICAL.value

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("log")
        return d


def yosys_available() -> bool:
    return shutil.which("yosys") is not None


def _rtl_files() -> list[str]:
    files = []
    for line in (REPO / "sim" / "rtl_files.f").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("+"):
            files.append(str(REPO / line))
    files.append(str(REPO / "syn/syn_wrappers.sv"))
    return files


def parse_stat(text: str) -> tuple[dict[str, int], int]:
    """Parse the last ``stat`` block: cell histogram and number of cells."""
    cells: dict[str, int] = {}
    blocks = text.split("Number of cells:")
    if len(blocks) < 2:
        return cells, 0
    last = blocks[-1]
    for m in re.finditer(r"^\s+(\$?\\?[\w$]+)\s+(\d+)\s*$", last, re.M):
        name, n = m.group(1), int(m.group(2))
        cells[name.lstrip("\\")] = cells.get(name.lstrip("\\"), 0) + n
    total = int(blocks[-1].split()[0])
    return cells, total


def ge_of(cells: dict[str, int]) -> tuple[int, float, int]:
    flops = sum(n for c, n in cells.items() if c.startswith(FF_PREFIXES))
    comb = sum(GE_WEIGHTS.get(c, 1.5) * n for c, n in cells.items()
               if c.startswith("$_") and not c.startswith(FF_PREFIXES))
    macros = sum(n for c, n in cells.items() if "sf_macro_1rw_leaf" in c)
    return flops, comb, macros


def synth(top: str, outdir: Path | None = None, timeout_s: int = 1800) -> SynthResult:
    outdir = Path(outdir or REPO / "build" / "syn")
    outdir.mkdir(parents=True, exist_ok=True)
    script = (
        f"read_verilog -sv -I{REPO / 'rtl/ecc'} " + " ".join(_rtl_files()) + "\n"
        f"read_verilog -sv -lib {REPO / 'rtl/macro_stubs/sf_macro_1rw_leaf_bb.sv'}\n"
        f"hierarchy -check -top {top}\n"
        "synth -flatten -top " + top + "\n"
        "opt_clean -purge\n"
        "tee -o " + str(outdir / f"{top}.stat") + " stat\n"
    )
    (outdir / f"{top}.ys").write_text(script)
    try:
        r = subprocess.run(["yosys", "-q", "-s", str(outdir / f"{top}.ys")], capture_output=True,
                           text=True, timeout=timeout_s)
        log = r.stdout + r.stderr
        ok = r.returncode == 0
    except subprocess.TimeoutExpired:
        return SynthResult(top, False, log="timeout")
    (outdir / f"{top}.log").write_text(log)
    stat_path = outdir / f"{top}.stat"
    if not ok or not stat_path.exists():
        return SynthResult(top, False, log=log[-4000:])
    cells, _ = parse_stat(stat_path.read_text())
    flops, comb, macros = ge_of(cells)
    return SynthResult(top, True, cells, flops, round(comb, 1), round(comb + FF_GE * flops, 1),
                       macros, log[-2000:])


def synth_all(tops: list[str] | None = None, out_json: Path | None = None) -> list[SynthResult]:
    res = []
    for t in tops or WRAPPERS:
        r = synth(t)
        res.append(r)
        print(f"  {t:<18} {'OK ' if r.ok else 'FAIL'} flops={r.flops:<7} comb_GE={r.comb_ge:<10} "
              f"total_GE={r.total_ge:<10} macros={r.macros}")
    if out_json:
        Path(out_json).parent.mkdir(parents=True, exist_ok=True)
        Path(out_json).write_text(json.dumps([r.to_dict() for r in res], indent=2))
    return res
