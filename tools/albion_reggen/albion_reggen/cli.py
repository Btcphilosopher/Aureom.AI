"""Command line: ``python -m albion_reggen <command> ...``

validate   check a definition and print a summary (exit 1 on any error)
generate   write RTL, C, Rust and documentation + MANIFEST.json
check      regenerate in memory and compare with an output directory
bindcheck  verify RTL bindings against the repository's RTL archives
alpcheck   verify the generator's ALP constants against sf_albion_pkg.sv
vectors    write model-driven test vectors for the generated testbench
simulate   build the generated RTL with Verilator and check it against the reference model
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional

from . import __version__, alpcheck as _alpcheck, bindcheck as _bindcheck, generate as _gen
from .errors import RegDefError
from .loader import load
from .validate import validate


def _load(path: str):
    try:
        return validate(load(path))
    except RegDefError as e:
        print(f"{path}: invalid register definition ({len(e.diagnostics)} problem(s))", file=sys.stderr)
        for d in e.diagnostics:
            print(f"  {d}", file=sys.stderr)
        sys.exit(1)


def _summary(m) -> str:
    return (f"{m.name} v{m.version[0]}.{m.version[1]}: {len(m.peripherals)} peripherals, "
            f"{len(m.instances)} registers, {len(m.hw_ports)} hardware ports\n"
            f"  semantic hash   {m.semantic_hash}\n  definition hash {m.definition_hash}")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="albion_reggen", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"albion_reggen {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("validate"); p.add_argument("definition")
    p = sub.add_parser("generate"); p.add_argument("definition"); p.add_argument("--out", required=True)
    p = sub.add_parser("check"); p.add_argument("definition"); p.add_argument("--out", required=True)
    p = sub.add_parser("bindcheck"); p.add_argument("definition")
    p.add_argument("--repo-root", required=True, help="directory that contains the RTL archives named in the definition")
    p.add_argument("--require", action="store_true", help="treat missing RTL as an error instead of skipping")
    p = sub.add_parser("alpcheck"); p.add_argument("definition", nargs="?")
    p.add_argument("--pkg", default=_alpcheck.DEFAULT_PKG)
    p = sub.add_parser("vectors"); p.add_argument("definition"); p.add_argument("--out", required=True)
    p.add_argument("--seed", type=int, default=1); p.add_argument("--cycles", type=int, default=4000)

    p = sub.add_parser("simulate"); p.add_argument("definition"); p.add_argument("--work", required=True)
    p.add_argument("--seed", type=int, default=1); p.add_argument("--cycles", type=int, default=4000)

    a = ap.parse_args(argv)

    if a.cmd == "validate":
        print(_summary(_load(a.definition)))
        return 0
    if a.cmd == "generate":
        m = _load(a.definition)
        written = _gen.write_outputs(m, a.out)
        print(_summary(m))
        print(f"wrote {len(written)} files to {a.out}")
        return 0
    if a.cmd == "check":
        m = _load(a.definition)
        probs = _gen.check_outputs(m, a.out)
        if probs:
            for x in probs:
                print(f"  {x}", file=sys.stderr)
            print(f"{a.out}: NOT up to date ({len(probs)} problem(s)); run 'generate'", file=sys.stderr)
            return 1
        print(f"{a.out}: up to date with {a.definition} (definition hash {m.definition_hash[:16]}...)")
        return 0
    if a.cmd == "bindcheck":
        m = _load(a.definition)
        res = _bindcheck.check(m, a.repo_root, a.require)
        rc = 0
        for r in res:
            print(f"  [{r.status:7}] {r.periph}.{r.module}: {r.detail}")
            if r.status == "error":
                rc = 1
        print("bindcheck:", "FAILED" if rc else "ok")
        return rc
    if a.cmd == "alpcheck":
        m = _load(a.definition) if a.definition else None
        bad = _alpcheck.check(m, a.pkg)
        for b in bad:
            print(f"  {b}", file=sys.stderr)
        print("alpcheck:", "FAILED" if bad else "ok (generator constants equal sf_albion_pkg.sv)")
        return 1 if bad else 0
    if a.cmd == "vectors":
        from . import emit_tb
        m = _load(a.definition)
        g = emit_tb.generate_vectors(m, a.seed, a.cycles)
        os.makedirs(a.out, exist_ok=True)
        for fn, txt in g.files().items():
            with open(os.path.join(a.out, fn), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(txt)
        print(f"wrote {g.cycles} cycles of vectors to {a.out}")
        return 0
    if a.cmd == "simulate":
        from . import simflow
        m = _load(a.definition)
        if not simflow.have_verilator():
            print("verilator is not installed", file=sys.stderr)
            return 2
        r = simflow.simulate(m, a.work, a.seed, a.cycles)
        print(f"simulate: {'PASS' if r.passed else 'FAIL'}  cycles={r.cycles} checked-bits={r.checks} "
              f"coverage-missing={len(r.missing)}")
        for x in r.missing[:20]:
            print(f"  not covered: {x}")
        if not r.passed:
            print(r.log, file=sys.stderr)
        return 0 if r.ok else 1
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
