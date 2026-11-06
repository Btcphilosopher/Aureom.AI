"""Repository + toolchain audit (PHASE 1).

Scans SilicaFlux-main/ including nested .zip / .tar.gz archives (read in
memory, nothing executed) and inventories: HDL files and declared modules,
.sf files (format), physical-design collateral (LEF/LIB/DEF/GDS/SDC), EDA
scripts (Yosys/OpenROAD/OpenSTA Tcl), memory-macro wrappers, and keywords for
the components the brief asks about.  Writes reports/audit/repository_audit.json
and REPOSITORY_INVENTORY.md.  The engineering interpretation is docs/AUDIT.md.
"""
from __future__ import annotations

import io
import json
import re
import tarfile
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from .config import PROJECT

ROOT = PROJECT.parent            # SilicaFlux-main
HDL = (".sv", ".v", ".svh", ".vh")
TEXT = HDL + (".sf", ".sfx", ".tcl", ".sdc", ".ys", ".py", ".md", ".yaml", ".yml", ".f", ".mk", ".sby", ".cfg", ".lef",
              ".lib", ".def", ".ts", ".json", ".sh", ".upf", ".lyp", ".lyt")
PHYS = (".lef", ".lib", ".def", ".gds", ".gds2", ".oas", ".sdc", ".spef", ".odb")
KEYWORDS = {"cpu": r"\bmodule\s+\w*(cpu|core|riscv|rv32)\w*", "vector": r"\bmodule\s+\w*vec\w*",
            "tensor": r"\bmodule\s+\w*(tensor|systolic|mac_array|matmul)\w*", "dma": r"\bmodule\s+\w*dma\w*",
            "interconnect": r"\bmodule\s+\w*(xbar|crossbar|noc|interconnect|fabric)\w*",
            "sram_wrapper": r"\bmodule\s+\w*sram\w*", "mcu_i": r"MCU[-_ ]?I\b"}


def _walk(name: str, data: bytes, prefix: str, out: list, depth: int = 0):
    if depth > 4:
        return
    low = name.lower()
    try:
        if low.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for m in zf.infolist():
                    if m.is_dir():
                        continue
                    sub = m.filename
                    if sub.lower().endswith((".zip", ".tar.gz", ".tgz")) or sub.lower().endswith(TEXT + PHYS):
                        _walk(sub, zf.read(m), f"{prefix}!{sub}", out, depth + 1)
                    else:
                        out.append((f"{prefix}!{sub}", m.file_size, None))
            return
        if low.endswith((".tar.gz", ".tgz")):
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
                for m in tf.getmembers():
                    if not m.isfile():
                        continue
                    f = tf.extractfile(m)
                    _walk(m.name, f.read() if f else b"", f"{prefix}!{m.name}", out, depth + 1)
            return
    except (zipfile.BadZipFile, tarfile.TarError, EOFError, OSError):
        out.append((prefix, len(data), b""))
        return
    out.append((prefix, len(data), data if low.endswith(TEXT + PHYS) else None))


def scan() -> dict:
    entries: list = []
    for p in sorted(ROOT.rglob("*")):
        if not p.is_file() or "silicaflux-floorplanlab" in p.parts:
            continue
        rel = str(p.relative_to(ROOT.parent))
        low = p.name.lower()
        if low.endswith((".zip", ".tar.gz", ".tgz")) or low.endswith(TEXT + PHYS):
            _walk(p.name, p.read_bytes(), rel, entries)
        else:
            entries.append((rel, p.stat().st_size, None))
    ext = Counter()
    hdl, sf, phys, scripts, modules = [], [], [], [], defaultdict(list)
    hits = defaultdict(list)
    sf_format = Counter()
    for path, size, data in entries:
        leaf = path.split("!")[-1]
        e = "." + leaf.rsplit(".", 1)[-1].lower() if "." in leaf else ""
        if leaf.lower().endswith(".tar.gz"):
            e = ".tar.gz"
        ext[e] += 1
        text = data.decode("utf-8", "replace") if data else ""
        if e in HDL or e == ".sf":
            (sf if e == ".sf" else hdl).append(path)
            for m in re.findall(r"^\s*module\s+(\w+)", text, re.M):
                modules[m].append(path)
            if e == ".sf":
                sf_format["systemverilog" if re.search(r"^\s*(module|package|interface)\b", text, re.M) else "other"] += 1
        if e in PHYS:
            phys.append({"path": path, "size": size})
        if e in (".tcl", ".ys", ".sdc", ".sby", ".mk") or (e == ".sh" and re.search(r"yosys|openroad|sta\b", text)):
            if re.search(r"openroad|yosys|read_liberty|create_clock|pdngen|place_|global_route|synth\b", text, re.I):
                scripts.append(path)
        for k, rx in KEYWORDS.items():
            if text and re.search(rx, text, re.I):
                hits[k].append(path)
    return {
        "root": str(ROOT.relative_to(ROOT.parent)),
        "files_scanned": len(entries),
        "by_extension": dict(ext.most_common(40)),
        "hdl_files": len(hdl), "sf_files": len(sf), "sf_format": dict(sf_format),
        "physical_collateral": phys,
        "eda_scripts": scripts,
        "modules_declared": len(modules),
        "module_index": {m: v[:6] for m, v in sorted(modules.items())},
        "component_hits": {k: sorted(set(v))[:60] for k, v in hits.items()},
        "mcu_i_found": bool(hits.get("mcu_i")),
        "top_candidates": {m: modules[m][:6] for m in ("sfv_soc", "sfv_soc_df", "silicaflux_top", "sfv_ulx3s_top",
                                                     "silicaflux_ml_top", "miner_top") if m in modules},
    }


def toolchain() -> dict:
    from .orfs import tool_versions
    return tool_versions()


def run_audit(out: str | None = None) -> int:
    dst = Path(out) if out else PROJECT / "reports" / "audit"
    dst.mkdir(parents=True, exist_ok=True)
    s = scan()
    s["toolchain"] = toolchain()
    (dst / "repository_audit.json").write_text(json.dumps(s, indent=1) + "\n")
    md = ["# Repository inventory (generated by `python -m floorplanlab audit`)", "",
          f"Scanned **{s['files_scanned']}** files under `{s['root']}` including nested archives "
          "(paths use `archive!member`).", "",
          f"* HDL files (.sv/.v/.svh/.vh): **{s['hdl_files']}**; `.sf` files: **{s['sf_files']}** "
          f"(format: {s['sf_format']}); modules declared: **{s['modules_declared']}**",
          f"* MCU-I implementation found: **{s['mcu_i_found']}**", "",
          "## Top-level candidates", ""]
    for m, paths in s["top_candidates"].items():
        md.append(f"* `{m}`: " + "; ".join(f"`{p}`" for p in paths[:3]))
    md += ["", "## Physical-design collateral (LEF/LIB/DEF/GDS/SDC/...)", ""]
    for p in s["physical_collateral"][:80]:
        md.append(f"* `{p['path']}` ({p['size']} B)")
    md += ["", "## EDA scripts (Yosys / OpenROAD / OpenSTA / SymbiYosys)", ""]
    md += [f"* `{p}`" for p in s["eda_scripts"][:120]]
    md += ["", "## Component keyword hits (module declarations)", ""]
    for k, v in s["component_hits"].items():
        md.append(f"### {k} ({len(v)})")
        md += [f"* `{p}`" for p in v[:25]]
        md.append("")
    md += ["## Toolchain", "", "```", json.dumps(s["toolchain"], indent=1), "```"]
    (dst / "REPOSITORY_INVENTORY.md").write_text("\n".join(md) + "\n")
    print(f"audit written to {dst}")
    return 0
