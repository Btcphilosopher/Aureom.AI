"""memoryflow command-line interface.

  memoryflow inspect <repo> [--yosys] [--md FILE] [--json FILE]
  memoryflow golden <outdir>
  memoryflow rtl [TB ...] [--seed N]          self-checking SV regression (Verilator)
  memoryflow synth [TOP ...]                  Yosys synthesis of the wrappers
  memoryflow roofline [--config reference|recommended|baseline]
  memoryflow explore [--top N]                design-space exploration + recommendation
  memoryflow report [--out DIR]               figures, matrices, HTML + Markdown report
  memoryflow all [--out DIR]                  rtl + synth + report
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _budget(a):
    from memoryflow.models.explore import Budget
    return Budget(node_nm=a.node, clock_hz=a.clock_mhz * 1e6, max_core_area_mm2=a.area, max_power_w=a.power)


def cmd_inspect(a) -> int:
    from memoryflow.inspect_rtl import dump_json, inspect, to_markdown
    mods, summ = inspect(a.repo, a.yosys, a.incdir)
    md = to_markdown(mods, a.repo)
    if a.md:
        Path(a.md).write_text(md)
    if a.json:
        dump_json(mods, a.json)
    print(md if not a.md else f"wrote {a.md}")
    return 0


def cmd_golden(a) -> int:
    from memoryflow.verify.golden import write_vector_set
    counts = write_vector_set(a.outdir)
    print(json.dumps(counts, indent=2))
    return 0


def cmd_rtl(a) -> int:
    from memoryflow.verify.rtl_runner import TESTBENCHES, run_all, verilator_available
    if not verilator_available():
        print("verilator not found", file=sys.stderr)
        return 2
    names = a.tests or list(TESTBENCHES)
    res = run_all(names, out_json=REPO / "build" / "rtl_results.json")
    bad = [r.name for r in res if not r.ok]
    print(f"{len(res) - len(bad)}/{len(res)} testbenches OK" + (f"; failing: {bad}" if bad else ""))
    return 1 if bad else 0


def cmd_synth(a) -> int:
    from memoryflow.verify.synth import synth_all, yosys_available
    if not yosys_available():
        print("yosys not found", file=sys.stderr)
        return 2
    res = synth_all(a.tops or None, REPO / "build" / "syn" / "synth_results.json")
    return 0 if all(r.ok for r in res) else 1


def cmd_roofline(a) -> int:
    from memoryflow.models.explore import baseline, joint_grid, mk, recommend
    from memoryflow.models.roofline import Roofline
    from memoryflow.models.workloads import default_suite
    from memoryflow.report.build import rtl_reference_config
    b = _budget(a)
    if a.config == "reference":
        cfg = rtl_reference_config(b)
    elif a.config == "recommended":
        rc = recommend(joint_grid(baseline(b), budget=b)).recommended.cfg
        cfg = mk(baseline(b), rc["spm_kib"], rc["banks"], rc["width"], rc["burst"], rc["dfifo"], rc["lanes"],
                 tuple(int(x) for x in rc["tensor"].split("x")), rc["extmem"])
    else:
        cfg = baseline(b)
    r = Roofline(cfg)
    print(cfg.label())
    for k, (v, p) in r.ceilings.items():
        print(f"  ceiling {k:<15} {v / 1e9:8.2f} GB/s  [{p.value}]")
    for u in ("cpu", "vector", "tensor"):
        print(f"  peak {u:<8} {r.peak(u) / 1e9:8.2f} Gop/s  ridge {r.peak(u) / r.effective_dram_bw():7.2f} op/B")
    for w in default_suite():
        pt = r.evaluate(w)
        print(f"  {w.name:<40} AI {pt.ai:8.2f}  {pt.perf / 1e9:8.2f} Gop/s  {pt.utilisation * 100:5.1f} %  {pt.bound}")
    return 0


def cmd_explore(a) -> int:
    from memoryflow.models.explore import baseline, joint_grid, pareto, recommend
    b = _budget(a)
    pts = joint_grid(baseline(b), budget=b)
    rec = recommend(pts)
    for line in rec.rationale:
        print(line)
    for n, p in (("minimal", rec.minimal), ("recommended", rec.recommended), ("stretch", rec.stretch)):
        print(f"{n:<12} {p.label:<60} {p.geomean_gops:7.2f} Gop/s {p.total_area_mm2:6.2f} mm2 {p.power_w:5.2f} W")
    print(f"Pareto front ({a.top} smallest):")
    for p in pareto([p for p in pts if p.feasible])[: a.top]:
        print(f"  {p.label:<60} {p.geomean_gops:7.2f} Gop/s {p.total_area_mm2:6.2f} mm2")
    return 0


def cmd_report(a) -> int:
    from memoryflow.report.build import generate
    generate(a.out, _budget(a))
    print(f"report written to {a.out}/report.html")
    return 0


def cmd_all(a) -> int:
    rc = cmd_rtl(argparse.Namespace(tests=None))
    cmd_synth(argparse.Namespace(tops=None))
    cmd_report(a)
    return rc


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="memoryflow", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def budget_args(sp):
        sp.add_argument("--node", type=int, default=40, help="process node (nm)")
        sp.add_argument("--clock-mhz", type=float, default=500.0)
        sp.add_argument("--area", type=float, default=12.0, help="core area budget (mm2)")
        sp.add_argument("--power", type=float, default=1.5, help="power budget (W)")

    s = sub.add_parser("inspect")
    s.add_argument("repo")
    s.add_argument("--yosys", action="store_true")
    s.add_argument("--incdir", action="append", default=[])
    s.add_argument("--md")
    s.add_argument("--json")
    s.set_defaults(fn=cmd_inspect)
    s = sub.add_parser("golden")
    s.add_argument("outdir")
    s.set_defaults(fn=cmd_golden)
    s = sub.add_parser("rtl")
    s.add_argument("tests", nargs="*")
    s.set_defaults(fn=cmd_rtl)
    s = sub.add_parser("synth")
    s.add_argument("tops", nargs="*")
    s.set_defaults(fn=cmd_synth)
    s = sub.add_parser("roofline")
    s.add_argument("--config", choices=["reference", "baseline", "recommended"], default="recommended")
    budget_args(s)
    s.set_defaults(fn=cmd_roofline)
    s = sub.add_parser("explore")
    s.add_argument("--top", type=int, default=12)
    budget_args(s)
    s.set_defaults(fn=cmd_explore)
    s = sub.add_parser("report")
    s.add_argument("--out", default=str(REPO / "reports"))
    budget_args(s)
    s.set_defaults(fn=cmd_report)
    s = sub.add_parser("all")
    s.add_argument("--out", default=str(REPO / "reports"))
    budget_args(s)
    s.set_defaults(fn=cmd_all)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
