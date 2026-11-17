"""Output assembly: one validated model -> every generated file, deterministically.

Determinism rules: no timestamps, host names or absolute paths in any output;
every list is emitted in address order; text is LF-terminated UTF-8; the
manifest is canonical JSON.  Running the generator twice, or on two machines,
yields byte-identical files (verified by the tests).
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Dict, List, Tuple

from . import GENERATOR_NAME, SCHEMA_VERSION, __version__
from . import emit_c, emit_doc, emit_rust, emit_sv, emit_tb
from .model import RegMap

MANIFEST = "MANIFEST.json"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_outputs(m: RegMap) -> Dict[str, str]:
    """Return {relative path: text} for everything the generator produces."""
    out: Dict[str, str] = {}
    for fn, txt in emit_sv.emit_all(m).items():
        out[f"rtl/{fn}"] = txt
    for fn, txt in emit_c.emit_all(m).items():
        out[f"fw/c/{fn}"] = txt
    for fn, txt in emit_rust.emit_all(m).items():
        out[f"fw/rust/{fn}"] = txt
    for fn, txt in emit_doc.emit_all(m).items():
        out[f"docs/{fn}"] = txt
    out["verif/tb_sf_reg_bank.sv"] = emit_tb.emit_tb(m)
    out["verif/tb_addr_dump.sv"] = emit_tb.emit_addr_dump(m)
    return out


def manifest_text(m: RegMap, outputs: Dict[str, str]) -> str:
    doc = {
        "generator": GENERATOR_NAME,
        "generator_version": __version__,
        "schema_version": SCHEMA_VERSION,
        "register_map": {"name": m.name, "version": f"{m.version[0]}.{m.version[1]}"},
        "semantic_hash": m.semantic_hash,
        "definition_hash": m.definition_hash,
        "inputs": {k: v for k, v in m.source_files},
        "outputs": {k: sha256_text(v) for k, v in sorted(outputs.items())},
    }
    return json.dumps(doc, indent=2, sort_keys=True) + "\n"


def write_outputs(m: RegMap, out_dir: str) -> List[str]:
    """Write all outputs and the manifest; remove files a previous manifest listed
    that are no longer generated.  Returns the written relative paths."""
    outputs = build_outputs(m)
    mf = manifest_text(m, outputs)
    old: List[str] = []
    mp = os.path.join(out_dir, MANIFEST)
    if os.path.exists(mp):
        try:
            with open(mp, "r", encoding="utf-8") as fh:
                old = sorted(json.load(fh).get("outputs", {}))
        except Exception:
            old = []
    for rel in old:
        if rel not in outputs:
            try:
                os.remove(os.path.join(out_dir, rel))
            except OSError:
                pass
    written = []
    for rel, text in sorted(outputs.items()):
        path = os.path.join(out_dir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        written.append(rel)
    with open(mp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(mf)
    written.append(MANIFEST)
    return written


def check_outputs(m: RegMap, out_dir: str) -> List[str]:
    """Compare freshly generated output with the files on disk.  Returns a list
    of problems (empty = up to date and nothing stale)."""
    outputs = build_outputs(m)
    outputs[MANIFEST] = manifest_text(m, {k: v for k, v in outputs.items()})
    problems: List[str] = []
    for rel, text in sorted(outputs.items()):
        path = os.path.join(out_dir, rel)
        if not os.path.exists(path):
            problems.append(f"missing: {rel}")
            continue
        with open(path, "r", encoding="utf-8", newline="") as fh:
            have = fh.read()
        if have != text:
            problems.append(f"stale (differs from the definition): {rel}")
    mp = os.path.join(out_dir, MANIFEST)
    if os.path.exists(mp):
        with open(mp, "r", encoding="utf-8") as fh:
            listed = set(json.load(fh).get("outputs", {}))
        for rel in sorted(listed - set(outputs)):
            if os.path.exists(os.path.join(out_dir, rel)):
                problems.append(f"stale file no longer generated: {rel}")
    return problems
