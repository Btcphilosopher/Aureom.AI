"""Light-weight SystemVerilog structure extraction (no full parser).

Extracts, per module: header parameters and ports, instances with their
named parameter / port connections, and the package types (``sf_*_t`` /
``sf_*_e``) it uses.  This is enough to detect, statically and with exact
line numbers,

* instances of modules that are defined nowhere            (REFERENCED_ONLY)
* instances whose named ports/parameters do not exist on   (INTERFACE_DRIFT)
  the definition that the repository does contain
* package types that no package in the repository defines  (MISSING_TYPES)

Authoritative elaboration is done separately with Verilator
(:func:`verilator_lint`); these static checks explain *why* it fails.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from memoryflow.inspect_rtl import _BEHAV, _KEYWORDS, _strip

_KW = set(_KEYWORDS) | {"unique", "priority", "unique0", "automatic", "static", "virtual", "extern",
                        "localparam", "parameter", "covergroup", "sequence", "endsequence", "cover",
                        "assume", "restrict", "wait", "disable", "return", "break", "continue", "do",
                        "casez", "casex", "endcase", "endfunction", "endtask", "endgenerate", "endmodule",
                        "package", "endpackage", "interface", "endinterface", "modport", "clocking",
                        "program", "class", "endclass", "final", "always_latch", "tri", "supply0",
                        "supply1", "wand", "wor", "signed", "unsigned", "var", "const", "ref", "type",
                        "posedge", "negedge", "or", "and", "not", "else", "foreach", "inside", "with"}

_MOD_RX = re.compile(r"\bmodule\s+(?:automatic\s+|static\s+)?([A-Za-z_]\w*)")
_PKG_RX = re.compile(r"\bpackage\s+([A-Za-z_]\w*)\s*;(.*?)\bendpackage\b", re.S)
_TYPEDEF_RX = re.compile(r"\btypedef\b(?:[^;{}]|\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})*?\b([A-Za-z_]\w*)\s*(?:\[[^\]]*\]\s*)*;", re.S)
_SFTYPE_RX = re.compile(r"\b(sf_\w+?_[te])\b")
# package-qualified types and type-parameter defaults (e.g. ``parameter type pkt_t = noc_packet_t``)
_QTYPE_RX = re.compile(r"\b[A-Za-z_]\w*_pkg::([A-Za-z_]\w*_[te])\b")
_TPARAM_RX = re.compile(r"\bparameter\s+type\s+\w+\s*=\s*([A-Za-z_]\w*)")


@dataclass
class Instance:
    module: str
    name: str
    line: int
    params: list[str] = field(default_factory=list)
    ports: list[str] = field(default_factory=list)


@dataclass
class ModuleDef:
    name: str
    file: str                     # path relative to MemoryFlow root (extracted copy)
    origin: str                   # repository origin of the file
    line: int
    params: list[str] = field(default_factory=list)
    ports: list[str] = field(default_factory=list)
    instances: list[Instance] = field(default_factory=list)
    used_types: set[str] = field(default_factory=set)
    local_types: set[str] = field(default_factory=set)
    imports: set[str] = field(default_factory=set)
    behavioural: list[str] = field(default_factory=list)
    nlines: int = 0
    sha256: str = ""


@dataclass
class PackageDef:
    name: str
    file: str
    origin: str
    line: int
    types: set[str]
    sha256: str = ""
    imports: set[str] = field(default_factory=set)


def match_paren(text: str, open_idx: int) -> int:
    """Index of the parenthesis closing the one at ``open_idx`` (-1 if none)."""
    depth = 0
    for i in range(open_idx, len(text)):
        c = text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


def split_top(text: str, sep: str = ",") -> list[str]:
    """Split on ``sep`` at bracket depth 0."""
    out, depth, cur = [], 0, []
    for c in text:
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        if c == sep and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(c)
    if "".join(cur).strip():
        out.append("".join(cur))
    return out


def _strip_dims(s: str) -> str:
    s = s.strip()
    while s.endswith("]"):
        depth, i = 0, len(s) - 1
        while i >= 0:
            if s[i] == "]":
                depth += 1
            elif s[i] == "[":
                depth -= 1
                if depth == 0:
                    break
            i -= 1
        s = s[:i].rstrip()
    return s


def _param_names(plist: str) -> list[str]:
    names = []
    for chunk in split_top(plist):
        lhs = split_top(chunk, "=")[0] if "=" in chunk else chunk
        lhs = _strip_dims(lhs)
        m = re.search(r"([A-Za-z_]\w*)\s*$", lhs)
        if m and m.group(1) not in _KW:
            names.append(m.group(1))
    return names


def _port_names(plist: str) -> list[str]:
    names = []
    for chunk in split_top(plist):
        c = _strip_dims(chunk.split("=")[0])
        m = re.search(r"([A-Za-z_]\w*)\s*$", c)
        if m and m.group(1) not in _KW:
            names.append(m.group(1))
    return names


def _named(conns: str) -> list[str]:
    return [m.group(1) for chunk in split_top(conns)
            for m in [re.match(r"\s*\.\s*([A-Za-z_]\w*)", chunk)] if m]


def _line_of(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


# NB: the head must not consume trailing whitespace, otherwise a skipped
# keyword line would swallow the next line's indentation and its ^ anchor.
_INST_HEAD = re.compile(r"(?m)^[ \t]*([A-Za-z_]\w*)\b")
_INST_PAR = re.compile(r"\s*#\s*\(")
_INST_NAME = re.compile(r"\s*([A-Za-z_]\w*)\s*((?:\[[^\]]*\]\s*)*)\(")


def parse_instances(body: str, body_offset: int, full: str, self_name: str) -> list[Instance]:
    out = []
    for m in _INST_HEAD.finditer(body):
        typ = m.group(1)
        if typ in _KW or typ == self_name:
            continue
        pos, params = m.end(), []
        mp = _INST_PAR.match(body, pos)
        if mp:
            close = match_paren(body, mp.end() - 1)
            if close < 0:
                continue
            params = _named(body[mp.end():close])
            pos = close + 1
        mi = _INST_NAME.match(body, pos)
        if not mi or mi.group(1) in _KW:
            continue
        popen = mi.end() - 1
        pclose = match_paren(body, popen)
        if pclose < 0:
            continue
        after = body[pclose + 1:pclose + 40].lstrip()
        if not after.startswith(";"):
            continue                                # function call / expression, not an instance
        out.append(Instance(typ, mi.group(1), _line_of(full, body_offset + m.start(1)), params,
                            _named(body[popen + 1:pclose])))
    return out


def parse_file(path: Path, rel: str, origin: str, sha: str = "") -> tuple[list[ModuleDef], list[PackageDef]]:
    raw = path.read_text(errors="replace")
    text = _strip(raw)
    mods, pkgs = [], []
    for pm in _PKG_RX.finditer(text):
        types = {t.group(1) for t in _TYPEDEF_RX.finditer(pm.group(2))}
        # explicit imports and package-qualified references (pkg::NAME) are both dependencies
        imps = (set(re.findall(r"\bimport\s+([A-Za-z_]\w*)\s*::", pm.group(2))) |
                set(re.findall(r"\b([A-Za-z_]\w*)\s*::\s*[A-Za-z_*]", pm.group(2)))) - {pm.group(1)}
        pkgs.append(PackageDef(pm.group(1), rel, origin, _line_of(text, pm.start()), types, sha, imps))
    starts = list(_MOD_RX.finditer(text))
    for i, m in enumerate(starts):
        name = m.group(1)
        end = text.find("endmodule", m.end())
        end = end if end > 0 else len(text)
        seg = text[m.end():end]
        k = 0
        params: list[str] = []
        imports = (set(re.findall(r"\bimport\s+([A-Za-z_]\w*)\s*::", seg[:2000])) |
                   set(re.findall(r"\b([A-Za-z_]\w*_pkg)\s*::", seg)))
        hdr_par = re.match(r"(?:\s*import\s+[\w:*,\s]+;)*\s*#\s*\(", seg)
        if hdr_par:
            close = match_paren(seg, hdr_par.end() - 1)
            params = _param_names(seg[hdr_par.end():close])
            k = close + 1
        ports: list[str] = []
        po = re.compile(r"\s*\(").match(seg, k)
        body_start = k
        if po:
            close = match_paren(seg, po.end() - 1)
            ports = _port_names(seg[po.end():close])
            body_start = close + 1
        body = seg[body_start:]
        params += [p for p in re.findall(r"(?m)^\s*parameter\b[^;=]*?\b([A-Za-z_]\w*)\s*(?:\[[^\]]*\]\s*)*=", body)
                   if p not in params]
        off = m.end() + body_start
        md = ModuleDef(name, rel, origin, _line_of(text, m.start()), params, ports,
                       parse_instances(body, off, text, name),
                       set(_SFTYPE_RX.findall(seg)) | set(_TPARAM_RX.findall(seg)) |
                       set(_QTYPE_RX.findall(seg)),
                       {t.group(1) for t in _TYPEDEF_RX.finditer(seg)},
                       imports,
                       sorted({why for rx, why in _BEHAV if rx.search(body)}),
                       text.count("\n", m.start(), end) + 1, sha)
        mods.append(md)
    return mods, pkgs


def verilator_available() -> bool:
    return shutil.which("verilator") is not None


@dataclass
class LintResult:
    top: str
    ok: bool | None          # None = inconclusive (simulator limitations on legal SV)
    errors: list[str]
    files: list[str]
    cmd: str = ""
    tool: str = "verilator"


def verilator_lint(top: str, files: list[Path], incdirs: list[Path] | None = None,
                   cwd: Path | None = None, timeout: int = 300) -> LintResult:
    """Elaborate ``top`` with Verilator (lint only).  ``.sf`` is SystemVerilog.

    If Verilator rejects the design *only* with "Unsupported" errors (a tool
    limitation, not a design defect) the elaboration is retried with Icarus
    Verilog and the result says which tool decided."""
    if not verilator_available():
        return LintResult(top, False, ["verilator not available"], [str(f) for f in files])
    cmd = ["verilator", "--lint-only", "-Wno-fatal", "-Wno-lint", "-Wno-style", "--timing",
           "+systemverilogext+sf", "--top-module", top]
    cmd += [f"-I{d}" for d in (incdirs or [])]
    cmd += [str(f) for f in files]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
    errs = [ln.strip() for ln in (r.stdout + r.stderr).splitlines() if ln.startswith("%Error")]
    ok = r.returncode == 0 and not errs
    hard = [e for e in errs if "Unsupported" not in e and "Exiting due to" not in e]
    if not ok and errs and not hard and shutil.which("iverilog"):
        icmd = ["iverilog", "-g2012", "-o", "/dev/null", "-s", top] + [f"-I{d}" for d in (incdirs or [])]
        icmd += [str(f) for f in files]
        ri = subprocess.run(icmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        ierr = [ln.strip() for ln in (ri.stdout + ri.stderr).splitlines() if "error" in ln.lower()]
        if ri.returncode == 0:
            return LintResult(top, True, [], [str(f) for f in files], " ".join(icmd), tool="iverilog")
        # both tools stopped on constructs they do not support: inconclusive, not a design defect
        return LintResult(top, None, errs[:3] + ierr[:3], [str(f) for f in files], " ".join(icmd),
                          tool="verilator+iverilog (inconclusive)")
    return LintResult(top, ok, errs[:12], [str(f) for f in files], " ".join(cmd))
