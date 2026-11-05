"""Architecture inventory: scan an RTL repository and classify every module.

    memoryflow inspect <repo> [--yosys] [--json out.json] [--md out.md]

For each SystemVerilog/Verilog module the scanner reports
  * category        CPU cache, L1/L2/LLC, scratchpad, SRAM array, DMA,
                    interconnect, vector RF, tensor accumulation, memory
                    controller, external memory interface, ECC, MBIST, ...
  * classification  SYNTHESIZABLE | BEHAVIOURAL | BLACKBOX | TESTBENCH
  * evidence        the constructs that decided the classification
  * children        instantiated modules
and then lists the memory-subsystem categories that have NO implementation
(-> PROPOSED additions).  Classification is static evidence; with --yosys
each SYNTHESIZABLE module is additionally elaborated by Yosys to confirm it.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

CATEGORIES: list[tuple[str, tuple[str, ...]]] = [
    ("testbench", ("tb_", "_tb", "testbench")),
    ("Synthesis wrapper", ("syn_",)),
    ("Subsystem integration", ("_top", "top_", "soc")),
    ("External memory model", ("extmem_model", "dram_model", "ddr_model")),
    ("L2 / last-level cache", ("l2", "llc", "l3")),
    ("CPU cache interface", ("cache_if", "icache", "dcache", "l1", "cache")),
    ("Scratchpad memory", ("spm", "scratchpad", "tcm")),
    ("SRAM array / macro", ("sram", "_ram", "ram_", "macro", "bram", "regfile_mem")),
    ("DMA engine", ("dma",)),
    ("Interconnect / router", ("router", "xbar", "crossbar", "noc", "interconnect", "arbiter", "mux_tree")),
    ("Vector register file", ("vrf", "vreg", "vec_rf", "regfile", "register_file")),
    ("Tensor accumulation / MAC array", ("tensor", "systolic", "mac_array", "accum", "gemm")),
    ("Vector unit", ("vec", "simd", "vector")),
    ("Memory controller", ("memctrl", "mem_ctrl", "ddr_ctrl", "dram_ctrl", "_mc", "controller")),
    ("External memory interface", ("ddr", "lpddr", "hbm", "phy", "extmem", "axi")),
    ("ECC / parity", ("ecc", "secded", "parity", "hamming")),
    ("MBIST", ("mbist", "bist", "march")),
    ("Data staging buffer", ("reuse", "pingpong", "ping_pong", "double_buf")),
    ("FIFO / flow control", ("fifo", "skid", "credit")),
    ("CPU core", ("core", "pipeline", "rv32", "alu", "decode", "hazard", "cpu")),
    ("Control / registers", ("regs", "csr", "apb", "ctrl")),
]

MEMORY_SUBSYSTEM = ["CPU cache interface", "L2 / last-level cache", "Scratchpad memory",
                    "SRAM array / macro", "DMA engine", "Interconnect / router",
                    "Vector register file", "Tensor accumulation / MAC array",
                    "Memory controller", "External memory interface"]

PROPOSAL_NOTES = {
    "CPU cache interface": "SilicaFlux core L1 <-> SPM host port adapter (SF-MEM valid/ready); "
                           "MemoryFlow provides the TCM-style host port on sf_spm_banked port 2.",
    "L2 / last-level cache": "Not recommended for SilicaFlux-V first silicon: DMA-managed SPM "
                             "gives deterministic bandwidth; revisit for multi-core variants.",
    "Vector register file": "Vector RF of the SilicaFlux vector pipeline (if separate from the "
                            "streaming sf_vec_unit) -- 2R1W, 32 x VLEN, sf_sram_1r1w-based.",
    "Memory controller": "Licensed DDR4/LPDDR4 controller IP behind an SF-MEM->AXI4 bridge "
                         "(bridge is a proposed MemoryFlow addition).",
    "External memory interface": "DDR4 x32 PHY hard IP (mature node); HBM only for future "
                                 "advanced-node variants.",
}

_MOD = re.compile(r"^\s*(?:\(\*[^)]*\*\)\s*)?module\s+(\w+)", re.M)
_INST = re.compile(r"^\s*(\w+)\s*(?:#\s*\(.*?\))?\s+(\w+)\s*\(", re.M | re.S)
_KEYWORDS = {"module", "if", "else", "for", "while", "case", "assign", "always", "always_ff", "always_comb",
             "initial", "function", "task", "begin", "end", "return", "generate", "typedef", "wire", "logic",
             "reg", "input", "output", "inout", "localparam", "parameter", "genvar", "int", "integer",
             "foreach", "repeat", "forever", "fork", "join", "assert", "property", "bit", "byte", "struct",
             "enum", "union", "import", "export", "default"}

_BEHAV = [
    (re.compile(r"#\s*\d+(\.\d+)?\s*(ns|ps|us|ms)?\b(?!\s*\()"), "delay control (#N)"),
    (re.compile(r"\binitial\b"), "initial block"),
    (re.compile(r"\$(urandom|random|display|finish|readmem[hb]|fopen|time)\b"), "simulation system task"),
    (re.compile(r"\bfork\b"), "fork/join"),
    (re.compile(r"\[\s*\$\s*\]"), "queue type"),
    (re.compile(r"\bclass\b"), "class"),
    (re.compile(r"\bforce\b"), "force"),
    (re.compile(r"\bstring\b"), "string type"),
    (re.compile(r"\breal\b"), "real type"),
]


@dataclass
class ModuleInfo:
    name: str
    file: str
    line: int
    category: str
    classification: str
    evidence: list[str] = field(default_factory=list)
    children: list[str] = field(default_factory=list)
    yosys_ok: bool | None = None


def _strip(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    text = re.sub(r"//[^\n]*", "", text)
    # drop simulation-only regions
    text = re.sub(r"`ifndef\s+SYNTHESIS.*?`endif", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    text = re.sub(r"translate_off.*?translate_on", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    return text


def categorise(name: str, path: str) -> str:
    n = name.lower()
    if n.startswith("tb_") or n.endswith("_tb"):
        return "testbench"
    for cat, keys in CATEGORIES[1:]:
        if any(k in n for k in keys):
            return cat
    return "other"


def _empty_body(body: str) -> bool:
    """True if nothing but the header (parameter + port lists) is present."""
    i = body.find("module")
    j = i + len("module")
    depth, k, n = 0, j, len(body)
    seen_ports = False
    while k < n:
        ch = body[k]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                rest = body[k + 1:].lstrip()
                if rest.startswith(";"):
                    seen_ports = True
                    return seen_ports and rest[1:].strip() == ""
        k += 1
    return False


def scan_file(path: Path, root: Path) -> list[ModuleInfo]:
    raw = path.read_text(errors="replace")
    text = _strip(raw)
    out = []
    rel = str(path.relative_to(root))
    under_tb = rel.replace("\\", "/").startswith("tb/") or "/tb/" in "/" + rel.replace("\\", "/")
    raw_starts = [m.start() for m in _MOD.finditer(raw)]
    for i, m in enumerate(_MOD.finditer(text)):
        pos, name = m.start(), m.group(1)
        end = text.find("endmodule", pos)
        body = text[pos:end if end > 0 else len(text)]
        cat = categorise(name, "/" + rel)
        ev: list[str] = []
        rpos = raw_starts[i] if i < len(raw_starts) else 0
        prev_end = raw.rfind("endmodule", 0, rpos)
        header = raw[prev_end + 9 if prev_end >= 0 else 0:rpos + 120]
        tag = re.search(r"Classification:\s*([^\n]+)", header)
        is_bb_attr = re.search(r"\(\*\s*blackbox\s*\*\)", header) is not None
        if cat == "testbench" or (under_tb and "$finish" in body):
            cls = "TESTBENCH"
        elif is_bb_attr or _empty_body(body):
            cls = "BLACKBOX"
            ev.append("(* blackbox *) attribute" if is_bb_attr else "empty body")
        else:
            for rx, why in _BEHAV:
                if rx.search(body):
                    ev.append(why)
            cls = "BEHAVIOURAL" if ev or under_tb else "SYNTHESIZABLE"
            if under_tb and not ev:
                ev.append("located in tb/ (simulation model)")
        if tag:
            t = tag.group(1).strip()
            ev.append(f"header: {t}")
            if "BEHAVIOURAL" in t.upper() and cls == "SYNTHESIZABLE":
                cls = "BEHAVIOURAL"
        children = sorted({c.group(1) for c in _INST.finditer(body)
                           if c.group(1) not in _KEYWORDS and not c.group(1).startswith("$")
                           and c.group(1) != name})
        out.append(ModuleInfo(name, rel, raw[:rpos].count("\n") + 1, cat, cls, ev, children))
    return out


def scan_repo(root: str | Path, exts: tuple[str, ...] = (".sv", ".v")) -> list[ModuleInfo]:
    root = Path(root).resolve()
    mods: list[ModuleInfo] = []
    for p in sorted(root.rglob("*")):
        if p.suffix in exts and "build" not in p.parts and ".git" not in p.parts:
            mods.extend(scan_file(p, root))
    known = {m.name for m in mods}
    for m in mods:
        m.children = [c for c in m.children if c in known]
    return mods


def yosys_check(root: Path, mods: list[ModuleInfo], incdirs: list[str] | None = None) -> None:
    """Elaborate every SYNTHESIZABLE module with Yosys (static confirmation)."""
    if not shutil.which("yosys"):
        return
    files = sorted({str(root / m.file) for m in mods if m.classification in ("SYNTHESIZABLE", "BLACKBOX")})
    inc = " ".join(f"-I{root / d}" for d in (incdirs or []))
    for m in mods:
        if m.classification != "SYNTHESIZABLE":
            continue
        script = f"read_verilog -sv {inc} {' '.join(files)}; hierarchy -top {m.name}; proc"
        r = subprocess.run(["yosys", "-q", "-p", script], capture_output=True, text=True, timeout=600)
        m.yosys_ok = r.returncode == 0


def summarise(mods: list[ModuleInfo]) -> dict:
    by_cat: dict[str, dict[str, list[str]]] = {}
    for m in mods:
        by_cat.setdefault(m.category, {}).setdefault(m.classification, []).append(m.name)
    missing = [c for c in MEMORY_SUBSYSTEM if not by_cat.get(c, {}).get("SYNTHESIZABLE")]
    return {"by_category": by_cat, "proposed": {c: PROPOSAL_NOTES.get(c, "MemoryFlow provides a reference block.")
                                                for c in missing}}


def to_markdown(mods: list[ModuleInfo], root: str, note: str = "") -> str:
    s = summarise(mods)
    lines = [f"# Architecture inventory: `{root}`", ""]
    if note:
        lines += [note, ""]
    lines += ["## Memory-subsystem coverage", "", "| Category | Implemented (synthesizable) | Behavioural / blackbox |",
              "|---|---|---|"]
    for cat in MEMORY_SUBSYSTEM + ["ECC / parity", "MBIST", "Data staging buffer", "Vector unit", "FIFO / flow control"]:
        d = s["by_category"].get(cat, {})
        impl = ", ".join(f"`{n}`" for n in d.get("SYNTHESIZABLE", [])) or "**none -> PROPOSED**"
        beh = ", ".join(f"`{n}` ({k.lower()})" for k in ("BEHAVIOURAL", "BLACKBOX") for n in d.get(k, [])) or "-"
        lines.append(f"| {cat} | {impl} | {beh} |")
    lines += ["", "## Proposed additions", ""]
    for c, why in s["proposed"].items():
        lines.append(f"* **{c}** -- {why}")
    lines += ["", "## All modules", "", "| Module | File | Category | Class | Evidence | Yosys |", "|---|---|---|---|---|---|"]
    for m in sorted(mods, key=lambda m: (m.classification, m.category, m.name)):
        y = "-" if m.yosys_ok is None else ("ok" if m.yosys_ok else "FAIL")
        lines.append(f"| `{m.name}` | {m.file}:{m.line} | {m.category} | {m.classification} | "
                     f"{'; '.join(m.evidence) or '-'} | {y} |")
    return "\n".join(lines) + "\n"


def inspect(root: str | Path, use_yosys: bool = False, incdirs: list[str] | None = None) -> tuple[list[ModuleInfo], dict]:
    root = Path(root).resolve()
    mods = scan_repo(root)
    if use_yosys:
        yosys_check(root, mods, incdirs)
    return mods, summarise(mods)


def dump_json(mods: list[ModuleInfo], path: str | Path) -> None:
    Path(path).write_text(json.dumps([asdict(m) for m in mods], indent=2))
