"""Experiment manager: experiment lists, grid / random / annealing sweeps,
parallel execution and reproducibility re-runs.

Every generated run gets its own YAML (``results/sweeps/<sweep>/configs``) that
``extends:`` the base config, so each point is a traceable, re-runnable file.
Runs execute as separate processes (`python -m floorplanlab run ...`); each
writes results/<run_id>/run.json.  Failed runs stay in the index with their
failure reason -- they are never dropped from comparisons.
"""
from __future__ import annotations

import concurrent.futures as cf
import itertools
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

import yaml

from .config import PROJECT, ConfigError, deep_merge, load_run
from .orfs import RESULTS

PY = [sys.executable, "-m", "floorplanlab"]


def _set(d: dict, dotted: str, value) -> dict:
    cur = d
    keys = dotted.split(".")
    for k in keys[:-1]:
        cur = cur.setdefault(k, {})
    cur[keys[-1]] = value
    return d


def _sample(spec, rng: random.Random):
    if isinstance(spec, dict) and "uniform" in spec:
        lo, hi = spec["uniform"]
        return round(rng.uniform(lo, hi), 3)
    if isinstance(spec, dict) and "choice" in spec:
        return rng.choice(spec["choice"])
    if isinstance(spec, list):
        return rng.choice(spec)
    return spec


def expand(sweep_cfg: Path) -> tuple[dict, list[tuple[str, Path]]]:
    sweep_cfg = Path(sweep_cfg).resolve()
    cfg = yaml.safe_load(sweep_cfg.read_text())
    sid = cfg["id"]
    kind = cfg.get("kind", "list")
    outdir = RESULTS / "sweeps" / sid / "configs"
    runs: list[tuple[str, Path]] = []
    if kind == "list":
        for rel in cfg["runs"]:
            p = (sweep_cfg.parent / rel).resolve()
            runs.append((load_run(p).id, p))
        return cfg, runs
    outdir.mkdir(parents=True, exist_ok=True)
    base = (sweep_cfg.parent / cfg["base"]).resolve()
    points: list[dict] = []
    if kind == "grid":
        names = list(cfg["parameters"])
        for combo in itertools.product(*(cfg["parameters"][n] for n in names)):
            points.append(dict(zip(names, combo)))
    elif kind == "random":
        rng = random.Random(cfg.get("seed", 1))
        seen = set()
        while len(points) < cfg["samples"]:
            pt = {n: _sample(s, rng) for n, s in cfg["parameters"].items()}
            key = json.dumps(pt, sort_keys=True)
            if key not in seen:
                seen.add(key)
                points.append(pt)
    elif kind == "anneal":
        from .optimiser import anneal_candidates
        points = anneal_candidates(cfg, base)
    else:
        raise ConfigError(f"unknown sweep kind {kind}")
    prefix = cfg.get("id_prefix", sid)
    for i, pt in enumerate(points):
        rid = f"{prefix}_{i:02d}"
        doc = {"extends": str(base), "id": rid, "description": f"{sid} point {i}: {pt}", "tags": ["sweep", sid]}
        for k, v in pt.items():
            _set(doc, k, v)
        if any(k.startswith("macros.arrangement") for k in pt):
            _set(doc, "macros.placement", "manual")
        p = outdir / f"{rid}.yaml"
        p.write_text(yaml.safe_dump(doc, sort_keys=False))
        runs.append((rid, p))
    return cfg, runs


def _run_one(cfg_path: Path, stages: str, log: Path) -> dict:
    t0 = time.time()
    with open(log, "w") as fh:
        rc = subprocess.run(PY + ["run", str(cfg_path), "--stages", stages], cwd=PROJECT / "python",
                            stdout=fh, stderr=subprocess.STDOUT).returncode
    return {"rc": rc, "seconds": round(time.time() - t0, 1)}


def run_sweep(sweep_config: str, jobs: int = 2, dry_run: bool = False) -> int:
    cfg, runs = expand(Path(sweep_config))
    stages = ",".join(cfg.get("stages", ["check", "synth", "floorplan", "pdn", "place", "route", "export"]))
    sdir = RESULTS / "sweeps" / cfg["id"]
    sdir.mkdir(parents=True, exist_ok=True)
    print(f"sweep {cfg['id']} ({cfg.get('kind', 'list')}): {len(runs)} runs, stages {stages}, jobs {jobs}")
    for rid, p in runs:
        print(f"  {rid}: {p}")
    if dry_run:
        return 0
    # synthesis is shared: run it once before fanning out (avoids duplicate synth races)
    first = runs[0][1]
    subprocess.run(PY + ["run", str(first), "--stages", "check,synth"], cwd=PROJECT / "python",
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    results = {}
    with cf.ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        fut = {ex.submit(_run_one, p, stages, sdir / f"{rid}.log"): rid for rid, p in runs}
        for f in cf.as_completed(fut):
            rid = fut[f]
            results[rid] = f.result()
            rec = RESULTS / rid / "run.json"
            st = json.loads(rec.read_text())["status"] if rec.is_file() else "no run.json"
            print(f"  done {rid}: {st} ({results[rid]['seconds']} s)")
    index = []
    for rid, p in runs:
        rec_p = RESULTS / rid / "run.json"
        rec = json.loads(rec_p.read_text()) if rec_p.is_file() else {}
        index.append({"run_id": rid, "config": str(p), "status": rec.get("status", "missing"),
                      "failure_reason": rec.get("failure_reason"), "failed_gates": rec.get("failed_gates"),
                      "physically_valid": rec.get("physically_valid"), **results.get(rid, {})})
    (sdir / "index.json").write_text(json.dumps({"sweep": cfg, "runs": index}, indent=2) + "\n")
    print(f"index: {sdir / 'index.json'}")
    return 0


def repro_check(config: str) -> int:
    """GATE 14: re-run check..pdn of a run under a new id and compare results."""
    spec = load_run(config)
    orig = RESULTS / spec.id / "run.json"
    if not orig.is_file():
        print(f"no completed run {spec.id}")
        return 1
    rid = f"{spec.id}__repro"
    p = RESULTS / "sweeps" / "repro" / f"{rid}.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump({"extends": str(Path(config).resolve()), "id": rid}, sort_keys=False))
    subprocess.run(PY + ["run", str(p), "--stages", "check,synth,floorplan,pdn"], cwd=PROJECT / "python",
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    a = json.loads(orig.read_text())
    b = json.loads((RESULTS / rid / "run.json").read_text())
    diffs = []
    compared = []
    for key in ("netlist_sha256",):
        compared.append(key)
        if a.get(key) != b.get(key):
            diffs.append(key)
    fa, fb = a["metrics"].get("floorplan", {}), b["metrics"].get("floorplan", {})
    for key in ("die_um", "core_um", "std_cell_area_um2", "macro_area_um2", "instances", "hpwl_um", "macros"):
        compared.append(f"floorplan.{key}")
        if fa.get(key) != fb.get(key):
            diffs.append(f"floorplan.{key}")
    for key in ("9",):
        compared.append(f"gate{key}")
        if a["gates"][key]["status"] != b["gates"][key]["status"]:
            diffs.append(f"gate{key}")
    a["repro_check"] = {"rerun_id": rid, "identical": not diffs, "differences": diffs, "compared": compared,
                        "stages": "check,synth,floorplan,pdn"}
    from .metrics import repro_findings
    from .validate import Finding  # noqa: F401

    class _R:  # minimal shim for repro_findings
        rec = a
    fs = repro_findings(_R)
    errs = [f for f in fs if f.severity == "error"]
    a["gates"]["14"]["findings"] = [f.to_dict() for f in fs]
    a["gates"]["14"]["status"] = "FAIL" if errs else "PASS"
    orig.write_text(json.dumps(a, indent=2, default=str) + "\n")
    print(json.dumps(a["repro_check"], indent=1))
    return 0 if not diffs else 1
