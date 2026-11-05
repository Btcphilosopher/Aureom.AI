"""memoryflow command-line interface.

  memoryflow sf-inventory [--no-lint] [--md FILE] [--json FILE]
                                              inventory of the SilicaFlux repository (evidence + elaboration)
  memoryflow sf-char [NAME ...]               self-checking testbenches on the unmodified SilicaFlux RTL
  memoryflow baselines [--budget B]           SilicaFlux as built / documented vs MemoryFlow recommendation
  memoryflow balance [--budget B]             compute / bandwidth balance of the recommended configuration
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
    """Named budget preset (default: the documented SilicaFlux-V 65 nm target), with per-field overrides."""
    from dataclasses import replace
    from memoryflow.models.explore import BUDGETS
    b = BUDGETS[a.budget]
    kw = {}
    if a.node is not None:
        kw["node_nm"] = a.node
    if a.clock_mhz is not None:
        kw["clock_hz"] = a.clock_mhz * 1e6
    if a.area is not None:
        kw["max_core_area_mm2"] = a.area
    if a.power is not None:
        kw["max_power_w"] = a.power
    if kw:
        b = replace(b, name=b.name + "+override", source="ASSUMPTION: command-line override of " + b.name, **kw)
    return b


def _recommended_cfg(b):
    from memoryflow.models.explore import baseline, joint_grid, recommend
    from memoryflow.report.sf_sections import _cfg_from_point
    return _cfg_from_point(baseline(b), recommend(joint_grid(baseline(b), budget=b)).recommended.cfg)


def cmd_sf_inventory(a) -> int:
    from memoryflow.silicaflux.inventory import write
    res = write(Path(a.md) if a.md else None, Path(a.json) if a.json else None, lint=not a.no_lint)
    if not res.get("available"):
        print("SilicaFlux sources not found (set MF_SILICAFLUX_ROOT)", file=sys.stderr)
        return 2
    from collections import Counter
    print(f"{res['files']} HDL files, {res['lines']:,} lines, {res['modules']} modules")
    for b in res["blocks"]:
        print(f"  {b['status']:<16} {b['block']['category']:<28} {b['block']['name']}")
    print("findings:", dict(Counter(f["kind"] for f in res["findings"])))
    return 0


def cmd_sf_char(a) -> int:
    from memoryflow.silicaflux.characterise import CHAR_TBS, available, run_all
    if not available():
        print("needs the SilicaFlux sources and verilator", file=sys.stderr)
        return 2
    res = run_all(a.tests or list(CHAR_TBS), out_json=REPO / "build" / "sf_char_results.json")
    bad = [r.name for r in res if not r.ok]
    print(f"{len(res) - len(bad)}/{len(res)} characterisations OK" + (f"; failing: {bad}" if bad else ""))
    return 1 if bad else 0


def cmd_baselines(a) -> int:
    from memoryflow.models.explore import evaluate
    from memoryflow.models.workloads import default_suite
    from memoryflow.silicaflux.baselines import all_baselines, evaluate_baseline
    b = _budget(a)
    rows = [(x.title, evaluate_baseline(x)) for x in all_baselines()]
    rows.append(("MemoryFlow recommended", evaluate(_recommended_cfg(b), default_suite(), b)))
    print(f"{'machine':<48} {'dense':>9} {'stream':>9} {'geomean':>9} {'mm2':>7} {'W':>6}")
    for t, p in rows:
        print(f"{t:<48} {p.dense_gops:9.3f} {p.stream_gops:9.3f} {p.geomean_gops:9.3f} {p.total_area_mm2:7.2f} "
              f"{p.power_w:6.2f}")
    return 0


def cmd_balance(a) -> int:
    from memoryflow.models.balance import cpu_orchestration, machine_balance
    from memoryflow.models.workloads import default_suite
    b = _budget(a)
    cfg = _recommended_cfg(b)
    mb = machine_balance(cfg, default_suite())
    print(cfg.label())
    for k in mb.kernels:
        cl = cpu_orchestration(cfg, next(w for w in default_suite() if w.name == k.name))
        print(f"  {k.name:<40} bound={k.bound:<8} headroom x{k.headroom:6.2f} (next {k.next_bound:<7}) "
              f"cpu {cl.cpu_busy * 100:5.1f} %")
    print("bound share:", {k: round(v, 2) for k, v in mb.bound_share.items()},
          f"geomean headroom x{mb.geomean_headroom:.2f}")
    return 0


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
        cfg = _recommended_cfg(b)
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
    from memoryflow.silicaflux.characterise import available
    if available():
        rc |= cmd_sf_char(argparse.Namespace(tests=None))
    cmd_synth(argparse.Namespace(tops=None))
    cmd_report(a)
    return rc


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="memoryflow", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def budget_args(sp):
        from memoryflow.models.explore import BUDGETS
        sp.add_argument("--budget", choices=list(BUDGETS), default="silicaflux-v-65",
                        help="named envelope (default: documented SilicaFlux-V target)")
        sp.add_argument("--node", type=int, default=None, help="override: process node (nm)")
        sp.add_argument("--clock-mhz", type=float, default=None, help="override: clock (MHz)")
        sp.add_argument("--area", type=float, default=None, help="override: core area budget (mm2)")
        sp.add_argument("--power", type=float, default=None, help="override: power budget (W)")

    s = sub.add_parser("sf-inventory")
    s.add_argument("--no-lint", action="store_true")
    s.add_argument("--md")
    s.add_argument("--json")
    s.set_defaults(fn=cmd_sf_inventory)
    s = sub.add_parser("sf-char")
    s.add_argument("tests", nargs="*")
    s.set_defaults(fn=cmd_sf_char)
    s = sub.add_parser("baselines")
    budget_args(s)
    s.set_defaults(fn=cmd_baselines)
    s = sub.add_parser("balance")
    budget_args(s)
    s.set_defaults(fn=cmd_balance)
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
