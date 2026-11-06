"""PPA comparison of runs: flat table, deltas vs. a baseline, Pareto front.

Fairness rule: runs are only compared when they share the netlist hash, the
tool versions, the platform revision and the clock period; others are listed
but flagged `comparable=False`.  Invalid / failed runs stay in the table with
their failure reasons and are never eligible for the Pareto front or for
"best" selection.  Vectorless power is shown for information only and is not
an objective.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .optimiser import pareto_front
from .orfs import RESULTS

OBJECTIVES = [("die_area_mm2", "min"), ("reg2reg_delay_ns", "min"), ("grt_overflow", "min"),
              ("grt_wirelength_mm", "min")]


def load_records(run_ids: list[str] | None = None) -> list[dict]:
    recs = []
    for p in sorted(RESULTS.glob("*/run.json")):
        if p.parent.name.startswith(("_", "synth", "sweeps")) or p.parent.name.endswith("__repro"):
            continue
        r = json.loads(p.read_text())
        if run_ids and r["run_id"] not in run_ids:
            continue
        recs.append(r)
    return recs


def flatten(r: dict) -> dict:
    m = r.get("metrics", {})
    fp = m.get("floorplan") or {}
    pl = m.get("place") or {}
    t = m.get("timing_preroute") or {}
    rt = m.get("route") or {}
    pw = (m.get("power_vectorless") or {}).get("groups", {}).get("total") or {}
    geo = r.get("geometry") or {}
    conn = m.get("connectivity") or {}
    tot = rt.get("total") or {}
    spec = r.get("spec", {})
    gates = {g: v["status"] for g, v in r.get("gates", {}).items()}
    row = {
        "run_id": r["run_id"], "description": spec.get("description", ""),
        "status": r.get("status"), "failure_reason": r.get("failure_reason"),
        "failed_gates": ",".join(r.get("failed_gates") or []),
        "physically_valid": bool(r.get("physically_valid")),
        "netlist_sha256": (r.get("netlist_sha256") or "")[:12],
        "tools": (r.get("tools") or {}).get("openroad"), "orfs": ((r.get("tools") or {}).get("orfs") or "")[:10],
        "clock_period_ns": t.get("clock_period_ns") or spec.get("clock_period_ns") or 20.0,
        "macro_placement": (spec.get("macros") or {}).get("placement"),
        "arrangement": (spec.get("macros") or {}).get("arrangement") or "auto (macro_placement)",
        "target_util": (spec.get("floorplan") or {}).get("target_util"),
        "aspect_ratio": (spec.get("floorplan") or {}).get("aspect_ratio"),
        "die_w_um": geo.get("die_w_um"), "die_h_um": geo.get("die_h_um"),
        "core_w_um": geo.get("core_w_um"), "core_h_um": geo.get("core_h_um"),
        "die_area_mm2": geo.get("die_area_mm2"), "core_area_mm2": geo.get("core_area_mm2"),
        "std_cell_area_floorplan_um2": fp.get("std_cell_area_um2"),
        "std_cell_area_placed_um2": pl.get("std_cell_area_um2"),
        "macro_area_um2": pl.get("macro_area_um2") or fp.get("macro_area_um2"),
        "std_cell_util_of_rows": pl.get("std_cell_util_of_rows"),
        "core_util_incl_macros": pl.get("core_util_incl_macros"),
        "placed_hpwl_mm": round(pl["hpwl_um"] / 1000, 2) if pl.get("hpwl_um") else None,
        "wns_ns": t.get("wns_ns"), "tns_ns": t.get("tns_ns"), "whs_ns": t.get("whs_ns"),
        "clk_worst_slack_ns": t.get("clk_group_worst_slack_ns"),
        "clk_path_delay_ns": t.get("clk_critical_path_delay_ns"),
        "reg2reg_slack_ns": t.get("reg2reg_worst_slack_ns"),
        "reg2reg_delay_ns": t.get("reg2reg_path_delay_ns"),
        "reg2reg_start": ((t.get("reg2reg_critical_paths") or [{}])[0].get("startpoint") or "")[:40],
        "reg2reg_end": ((t.get("reg2reg_critical_paths") or [{}])[0].get("endpoint") or "")[:40],
        "grt_hotspot_near_macro_frac": ((rt.get("hotspots") or {}).get("near_macro_fraction")),
        "grt_completed": rt.get("completed"),
        "grt_overflow": tot.get("overflow_total"),
        "grt_wirelength_mm": round(rt["routed_wirelength_um"] / 1000, 2) if rt.get("routed_wirelength_um") else None,
        "grt_wns_ns": (rt.get("timing") or {}).get("wns_ns") if isinstance(rt.get("timing"), dict) else None,
        "inter_group_hpwl_mm": round(conn["inter_group_hpwl_um"] / 1000, 2) if conn.get("inter_group_hpwl_um") else None,
        "pdn_connected": gates.get("9") == "PASS",
        "power_vectorless_mw": round(pw["total_w"] * 1000, 2) if pw.get("total_w") is not None else None,
    }
    for g, s in gates.items():
        row[f"gate{g}"] = s
    return row


def table(run_ids: list[str] | None = None) -> pd.DataFrame:
    return pd.DataFrame([flatten(r) for r in load_records(run_ids)])


def compare(df: pd.DataFrame, baseline: str) -> dict:
    if df.empty:
        return {"rows": [], "pareto": [], "notes": ["no runs"]}
    base = df[df.run_id == baseline]
    notes = []
    keys = ["netlist_sha256", "tools", "orfs", "clock_period_ns"]
    if base.empty:
        notes.append(f"baseline {baseline} not found")
        ref = None
    else:
        ref = base.iloc[0]
    df = df.copy()
    df["comparable"] = [all(row[k] == ref[k] for k in keys) if ref is not None else False for _, row in df.iterrows()]
    deltas = []
    metrics = ["die_area_mm2", "core_area_mm2", "std_cell_area_placed_um2", "placed_hpwl_mm", "wns_ns",
               "reg2reg_delay_ns", "grt_overflow", "grt_wirelength_mm", "grt_wns_ns", "inter_group_hpwl_mm"]
    for _, row in df.iterrows():
        d = {"run_id": row.run_id}
        for m in metrics:
            if ref is not None and pd.notna(row.get(m)) and pd.notna(ref.get(m)) and ref.get(m) not in (0, None):
                d[f"d_{m}_pct"] = round(100.0 * (row[m] - ref[m]) / abs(ref[m]), 2)
            else:
                d[f"d_{m}_pct"] = None
        deltas.append(d)
    eligible = df[(df.physically_valid) & (df.comparable) & (df.grt_completed == 1)]
    pf = pareto_front(eligible.to_dict("records"), OBJECTIVES)
    invalid = df[~df.physically_valid][["run_id", "status", "failure_reason", "failed_gates"]].to_dict("records")
    return {"baseline": baseline, "objectives": OBJECTIVES, "pareto": pf, "eligible": list(eligible.run_id),
            "invalid_runs": invalid, "deltas": deltas, "notes": notes,
            "rule": "only physically valid, comparable runs with a completed global route are ranked; "
                    "Pareto over die area, register-to-register critical-path delay (pre-route), GRT overflow, GRT wirelength"}
