"""Command line: python -m floorplanlab <command> ...  (see `--help`)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ALL_STAGES = ["check", "synth", "floorplan", "pdn", "place", "timing", "route", "export"]
DEFAULT_STAGES = ["check", "synth", "floorplan", "pdn", "place", "route", "export"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="floorplanlab", description="SilicaFlux FloorplanLab")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run stages of one experiment config")
    r.add_argument("config")
    r.add_argument("--stages", default=",".join(DEFAULT_STAGES))

    c = sub.add_parser("check", help="validate configs, platform and design inputs (no tool runs)")
    c.add_argument("config")

    s = sub.add_parser("sweep", help="run an experiment set / parameter search")
    s.add_argument("sweep_config")
    s.add_argument("--jobs", type=int, default=2)
    s.add_argument("--dry-run", action="store_true")

    rp = sub.add_parser("report", help="build comparison + visual reports from results/")
    rp.add_argument("--runs", nargs="*", default=None)
    rp.add_argument("--baseline", default="A_baseline")

    pf = sub.add_parser("platforms", help="list platform profiles and their status")

    a = sub.add_parser("audit", help="repository + toolchain audit")
    a.add_argument("--out", default=None)

    rpc = sub.add_parser("repro", help="re-run the floorplan stage of a run and compare (GATE 14)")
    rpc.add_argument("config")

    g = sub.add_parser("gui", help="open a run's OpenROAD database in the OpenROAD GUI (ORFS gui_* targets)")
    g.add_argument("config")
    g.add_argument("--stage", choices=["floorplan", "place"], default="place")

    args = ap.parse_args(argv)
    if args.cmd == "run":
        from .pipeline import run_file
        stages = [x for x in args.stages.split(",") if x]
        bad = [x for x in stages if x not in ALL_STAGES]
        if bad:
            ap.error(f"unknown stages {bad}")
        rec = run_file(args.config, stages)
        print(json.dumps({"run_id": rec["run_id"], "status": rec["status"], "failure_reason": rec.get("failure_reason"),
                          "gates": {g: v["status"] for g, v in rec["gates"].items()}}, indent=1))
        return 0 if rec["status"] in ("completed",) else 1
    if args.cmd == "check":
        from .config import load_run
        from .pipeline import Run
        run = Run(load_run(args.config))
        ok = run.check()
        print(json.dumps({g: {"status": v["status"], "errors": [f["message"] for f in v["findings"] if f["severity"] == "error"],
                              "prechecks": [f["message"] for f in v.get("prechecks", []) if f["severity"] != "info"]}
                          for g, v in run.rec["gates"].items() if v["status"] != "NOT_RUN" or v.get("prechecks")}, indent=1))
        return 0 if ok else 1
    if args.cmd == "sweep":
        from .experiment_runner import run_sweep
        return run_sweep(args.sweep_config, jobs=args.jobs, dry_run=args.dry_run)
    if args.cmd == "report":
        from .report import build_reports
        return build_reports(args.runs, args.baseline)
    if args.cmd == "platforms":
        from .config import PROJECT, load_platform
        from .validate import check_platform, errors
        rc = 0
        for p in sorted((PROJECT / "platforms").iterdir()):
            if not (p / "profile.yaml").is_file():
                continue
            pf = load_platform(p.name)
            fs, _ = check_platform(pf)
            e = errors(fs)
            print(f"{pf.name:16s} {pf.status:9s} {'OK' if not e else f'{len(e)} error(s)'}"
                  + ("" if not e else ": " + "; ".join(x.message for x in e[:3])))
        return rc
    if args.cmd == "audit":
        from .audit import run_audit
        return run_audit(args.out)
    if args.cmd == "gui":
        import os
        from .config import load_run
        from .pipeline import Run
        run = Run(load_run(args.config))
        odb = run.ctx.results_dir / ("3_place.odb" if args.stage == "place" else "2_floorplan.odb")
        if not odb.is_file():
            print(f"no {odb.name} for run {run.spec.id}: run the {args.stage} stage first")
            return 1
        from .orfs import tools
        t = tools()
        cmd = (f"make -C {t['ORFS_FLOW']} DESIGN_CONFIG={run.ctx.config_mk} WORK_HOME={run.ctx.work_home} "
               f"FLOW_VARIANT=base OPENROAD_EXE={t['OPENROAD_EXE']} YOSYS_CMD={t['YOSYS_EXE']} gui_{args.stage}")
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            print("No display available: the OpenROAD GUI cannot be opened here (it would run offscreen and block).")
            print("On a workstation with a display, run:\n  " + cmd)
            print(f"Static views of this database: {run.dir / 'export'}/floorplan.png|svg")
            return 2
        return os.system(cmd) >> 8
    if args.cmd == "repro":
        from .experiment_runner import repro_check
        return repro_check(args.config)
    return 2


if __name__ == "__main__":
    sys.exit(main())
