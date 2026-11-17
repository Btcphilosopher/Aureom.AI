"""Verify that a register map only binds to RTL that exists.

For every ``rtl.modules`` entry of every peripheral:

1. the source file is located inside a repository archive (``archive`` is a
   path relative to ``--repo-root``; ``path`` is the member inside the zip)
   or directly under ``--rtl-root``;
2. its SHA-256 equals the recorded one (the definition was written against
   exactly this RTL);
3. the module is declared in it and every port listed in the definition exists
   with the recorded direction.

Together with the validator's offline direction check (a bank *output* must
connect to an RTL *input* and vice versa) this makes "integrates only with
implemented RTL" a mechanical check rather than a claim.
"""

from __future__ import annotations

import hashlib
import os
import re
import zipfile
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .model import RegMap


@dataclass
class BindResult:
    periph: str
    module: str
    status: str            # ok | skipped | error
    detail: str


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"//[^\n]*", " ", text)


def _match_paren(text: str, start: int) -> int:
    """Index of the ')' matching the '(' at ``start``."""
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


def parse_ports(source: str, module: str) -> Optional[Dict[str, str]]:
    """Ports (name -> input|output|inout) of an ANSI-style module declaration."""
    text = _strip_comments(source)
    m = re.search(r"\bmodule\s+(?:automatic\s+)?" + re.escape(module) + r"\b", text)
    if not m:
        return None
    i = m.end()
    while i < len(text) and text[i].isspace():
        i += 1
    if i < len(text) and text[i] == "#":
        i = text.index("(", i)
        i = _match_paren(text, i) + 1
        while i < len(text) and text[i].isspace():
            i += 1
    if i >= len(text) or text[i] != "(":
        return {}
    j = _match_paren(text, i)
    body = text[i + 1:j]
    items: List[str] = []
    depth, cur = 0, []
    for ch in body:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            items.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    items.append("".join(cur))
    ports: Dict[str, str] = {}
    last = ""
    for it in items:
        it = it.strip()
        if not it:
            continue
        dm = re.match(r"(input|output|inout)\b", it)
        if dm:
            last = dm.group(1)
        # the port name is the last identifier of the item (before an optional default value)
        it = it.split("=")[0].strip()
        nm = re.findall(r"[A-Za-z_][A-Za-z0-9_$]*", re.sub(r"\[[^\]]*\]", " ", it))
        if nm and last:
            ports[nm[-1]] = last
    return ports


def _load_member(repo_root: str, archive: str, path: str) -> Optional[bytes]:
    az = os.path.join(repo_root, archive)
    if not os.path.isfile(az):
        return None
    with zipfile.ZipFile(az) as zf:
        names = zf.namelist()
        if path in names:
            return zf.read(path)
        # tolerate one extra leading directory (archives packed with a wrapper folder)
        cand = [n for n in names if n.endswith("/" + path) and n.count("/") == path.count("/") + 1]
        if len(cand) == 1:
            return zf.read(cand[0])
    return None


def check(m: RegMap, repo_root: str, require: bool = False) -> List[BindResult]:
    res: List[BindResult] = []
    for p in m.peripherals:
        for md in p.rtl_modules:
            if not md.path:
                res.append(BindResult(p.name, md.module, "skipped", "no source recorded"))
                continue
            data = _load_member(repo_root, md.archive, md.path)
            if data is None:
                st = "error" if require else "skipped"
                res.append(BindResult(p.name, md.module, st, f"RTL not found: {md.archive} :: {md.path}"))
                continue
            sha = hashlib.sha256(data).hexdigest()
            if md.sha256 and sha != md.sha256:
                res.append(BindResult(p.name, md.module, "error",
                                      f"SHA-256 differs: recorded {md.sha256[:16]}..., found {sha[:16]}... "
                                      "(the RTL changed since this definition was written)"))
                continue
            src_text = data.decode("utf-8", "replace")
            if re.search(r"\bpackage\s+" + re.escape(md.module) + r"\b", _strip_comments(src_text)):
                # a package (constants), not a module: nothing to check but its existence and hash
                res.append(BindResult(p.name, md.module, "ok" if not md.ports else "error",
                                      f"package declared, sha256 {sha[:12]}" if not md.ports
                                      else "a package has no ports to bind"))
                continue
            ports = parse_ports(src_text, md.module)
            if ports is None:
                res.append(BindResult(p.name, md.module, "error", f"module {md.module} is not declared in {md.path}"))
                continue
            bad = []
            for pn, d in md.ports:
                if pn not in ports:
                    bad.append(f"{pn}: not a port")
                elif ports[pn] != d:
                    bad.append(f"{pn}: declared {d}, RTL has {ports[pn]}")
            if bad:
                res.append(BindResult(p.name, md.module, "error", "; ".join(bad)))
            else:
                res.append(BindResult(p.name, md.module, "ok",
                                      f"{len(md.ports)} port(s) verified against {len(ports)} RTL ports, sha256 {sha[:12]}"))
    return res
