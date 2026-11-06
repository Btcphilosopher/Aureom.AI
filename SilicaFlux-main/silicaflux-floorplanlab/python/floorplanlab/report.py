"""Build the cross-run reports in reports/ from results/*/run.json.

reports/experiments/summary.md      tables (area, timing, congestion, gates, deltas, Pareto)
reports/experiments/ppa_table.csv   the flat PPA table (every run, valid or not)
reports/experiments/comparison.json deltas / Pareto / invalid runs
reports/experiments/index.html      interactive summary (Plotly) + images
reports/experiments/side_by_side.*  floorplans of every exported run
reports/runs/<id>/                  run.json, images, geometry/twinlab JSON, key reports
reports/logs/<id>/                  ORFS + FloorplanLab logs (gzip)
"""
from __future__ import annotations

import gzip
import html
import json
import shutil
from pathlib import Path

import pandas as pd

from .compare import compare, load_records, table
from .config import PROJECT
from .orfs import RESULTS

REPORTS = PROJECT / "reports"
SURF, INK, INK2, BLUE, GREY, CRIT = "#fcfcfb", "#0b0b0b", "#52514e", "#2a78d6", "#a8a7a1", "#d03b3b"


def _fmt(v, nd=3):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "n/a"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def md_table(df: pd.DataFrame, cols: list[str], nd=3) -> str:
    cols = [c for c in cols if c in df.columns]
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        out.append("| " + " | ".join(_fmt(r[c], nd) for c in cols) + " |")
    return "\n".join(out)


def curate_run(r: dict) -> None:
    rid = r["run_id"]
    src = RESULTS / rid
    dst = REPORTS / "runs" / rid
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / "run.json", dst / "run.json")
    for sub, names in (("export", ["floorplan.png", "floorplan.svg", "geometry.json", "connectivity.json",
                                   "twinlab_floorplan.json"]),
                       ("analysis", ["floorplan_metrics.json", "place_metrics.json", "pdn_checks.json",
                                     "route_metrics.json", "place_timing_setup.rpt", "place_timing_hold.rpt",
                                     "place_timing_endpoints.rpt", "place_drv.rpt", "place_power.rpt",
                                     "place_clocks.rpt", "place_timing_outputs.rpt", "grt_timing_setup.rpt",
                                     "grt_congestion.rpt", "grt_wirelength.rpt", "place_check_placement.rpt"])):
        for n in names:
            p = src / sub / n
            if p.is_file():
                if p.stat().st_size > 2_000_000:
                    with open(p, "rb") as fi, gzip.open(dst / (n + ".gz"), "wb") as fo:
                        shutil.copyfileobj(fi, fo)
                else:
                    shutil.copy2(p, dst / n)
    # OpenROAD-rendered views, downscaled, for the experiment set only (size)
    tags = set((r.get("spec") or {}).get("tags") or [])
    if tags & {"experiment", "locality", "baseline"}:
        try:
            from PIL import Image
            for n in ("or_placement_density.png", "or_pdn.png", "or_placement.png"):
                p = src / "export" / n
                if p.is_file():
                    im = Image.open(p)
                    im.thumbnail((700, 700))
                    im.save(dst / n, optimize=True)
        except Exception as e:  # pragma: no cover
            print(f"note: OpenROAD image curation skipped for {rid}: {e}")
    for p in (src / "orfs" / "inputs").glob("*"):
        if p.suffix in (".mk", ".tcl", ".sdc", ".svh"):
            (dst / "inputs").mkdir(exist_ok=True)
            shutil.copy2(p, dst / "inputs" / p.name)
    logs = REPORTS / "logs" / rid
    logs.mkdir(parents=True, exist_ok=True)
    for d in (src / "orfs" / "logs", src / "orfs" / "flp_logs"):
        for p in d.rglob("*.log"):
            with open(p, "rb") as fi, gzip.open(logs / (p.name + ".gz"), "wb") as fo:
                shutil.copyfileobj(fi, fo)


def synthesis_report(rec: dict) -> Path | None:
    """reports/synthesis/: SYNTHESIS_REPORT.md + raw Yosys stat/check + log (from the shared synthesis)."""
    syn = rec.get("synthesis")
    if not syn:
        return None
    out = REPORTS / "synthesis"
    out.mkdir(parents=True, exist_ok=True)
    stat = Path(syn["stat_report"])
    for f in (stat, stat.parent / "synth_check.txt", stat.parent / "synth_hier_stat.txt"):
        if f.is_file():
            shutil.copy2(f, out / f.name)
    log = stat.parents[3] / "logs" / stat.parts[-3] / stat.parts[-2] / stat.parts[-1] / "1_1_yosys.log"
    if log.is_file():
        with open(log, "rb") as fi, gzip.open(out / "1_1_yosys.log.gz", "wb") as fo:
            shutil.copyfileobj(fi, fo)
    tools = rec.get("tools", {})
    lines = ["# SilicaFlux-V synthesis report (ORFS / Yosys)", "",
             f"* Design: `{rec['design']['top']}` ({rec['design']['description']})",
             f"* Platform: {rec['platform']['name']} ({rec['platform']['process']}), corner: typical",
             f"* Tools: Yosys `{tools.get('yosys')}`, OpenROAD `{tools.get('openroad')}`, ORFS `{tools.get('orfs')}`",
             f"* Netlist: sha256 `{rec.get('netlist_sha256')}` (synthesis key `{rec.get('synth_key')}`)",
             "* Flow: ORFS `synth` target, `SYNTH_HIERARCHICAL=1` (`MAX_UNGROUP_SIZE=1000`), ABC speed script, "
             "clock period 20 ns from the SDC; defines `SYNTHESIS` (Yosys) + `SFV_SRAM_MACRO`; top parameters "
             "`PERF=0 ARB_MODE=1 DMA_ENGINE=0 SRAM_IMPL=0`", "",
             "## Required figures", "",
             "| Item | Value | Source |", "|---|---|---|",
             f"| Total mapped cells (incl. macros) | {syn['total_cells']:,} | synth_stat.txt |",
             f"| Standard cells | {syn['std_cells']:,} | stat minus hard macros |",
             f"| Sequential cells (flip-flops) | {syn['sequential_cells']:,} (all async-reset: {syn['async_reset_flops']:,}) | Liberty `ff` groups |",
             f"| Latch cells | {syn['latch_cells']} | Liberty `latch` groups |",
             f"| Integrated clock-gating cells | {syn['icg_cells']} | Liberty `clock_gating_integrated_cell` |",
             f"| Combinational cells | {syn['combinational_cells']:,} | remainder |",
             f"| of which buffers/inverters/delay | {syn['buffer_inverter_cells']:,} | ABC buffering; ORFS `remove_buffers` drops most at floorplan |",
             f"| Tie cells | {syn['tie_cells']} | hilomap |",
             f"| Std-cell area (synthesis) | {syn['std_cell_area_um2']:,.0f} um2 = {syn['std_cell_area_um2']/1e6:.3f} mm2 | chip area - macro Liberty area |",
             f"| Sequential area | {syn['sequential_area_um2']:,.0f} um2 | stat |",
             f"| Hard-macro area (Liberty) | {syn['macro_area_um2']:,.0f} um2 = {syn['macro_area_um2']/1e6:.3f} mm2 | macro `area` |",
             f"| Identified macro instances | {sum(syn['macros'].values())}: " + ", ".join(f"{n} x {m}" for m, n in syn['macros'].items()) + " | netlist |",
             f"| Unresolved black boxes | {len(syn['unresolved_modules'])} {syn['unresolved_modules'] or ''} | netlist scan |",
             f"| Unknown cell types | {len(syn['unknown_cell_types'])} | netlist vs Liberty |",
             f"| Yosys `check` problems | {syn['check_problems']} | synth_check.txt |", "",
             "## Macro instances", ""]
    lines += [f"* `{m['name']}` -> `{m['master']}`" for m in syn["macro_instances"]]
    lines += ["", "## Synthesis warnings", ""]
    lines += [f"* {w['count']}x {w['message']}" for w in syn["warnings"]] or ["* none"]
    lines += ["", "Interpretation: the `\\dout` memory conversion is the 2-entry 64-bit read-mux array inside the IHP "
              "macro wrapper (not a RAM); the Liberty expression warning concerns `sg13g2_sdfbbp_1`, a scan flop the "
              "design does not use.", "",
              "## Clock and reset observations", "",
              f"* {syn['clock_reset_observations']['note']}",
              f"* flip-flops {syn['sequential_cells']}, all with asynchronous reset/set; ICG instances "
              f"{syn['icg_cells']} (`u_tile/u_cg_ve`, `u_tile/u_cg_te`, `sg13g2_slgcp_1`, kept although the platform "
              "lists it dont_use -- explicit instances are not remapped)",
              "* high-fanout nets after floorplan (OpenDB): `clk` and `sys_rst_n` (thousands of sinks) -> buffered by "
              "`repair_design` at placement; a balanced clock/reset tree is a CTS task (not done here)", "",
              "## Std-cell area by top-level instance (hierarchy kept above 1000 um2)", "",
              "| instance | module | std-cell area um2 | macro area um2 |", "|---|---|---|---|"]
    lines += [f"| `{a['instance']}` | `{a['module'][:60]}` | {a['std_cell_area_um2']:,.0f} | {a['macro_area_um2']:,.0f} |"
              for a in syn["area_by_instance"]]
    lines += [f"| (top-level glue) | `{rec['design']['top']}` | {syn['top_glue_area_um2']:,.0f} | 0 |"]
    p = out / "SYNTHESIS_REPORT.md"
    p.write_text("\n".join(lines) + "\n")
    (out / "synthesis_summary.json").write_text(json.dumps(syn, indent=1) + "\n")
    return p


def curate_history() -> None:
    """reports/experiment_log/: evidence of failed first attempts (logs, records; no ODB)."""
    src = RESULTS / "_history"
    if not src.is_dir():
        return
    dst = REPORTS / "experiment_log"
    for d in sorted(p for p in src.iterdir() if p.is_dir()):
        out = dst / d.name
        out.mkdir(parents=True, exist_ok=True)
        for f in d.rglob("*"):
            if not f.is_file() or f.suffix == ".odb":
                continue
            rel = f.relative_to(d)
            (out / rel).parent.mkdir(parents=True, exist_ok=True)
            if f.suffix in (".log", ".rpt") and f.stat().st_size > 200_000:
                with open(f, "rb") as fi, gzip.open(out / (str(rel) + ".gz"), "wb") as fo:
                    shutil.copyfileobj(fi, fo)
            else:
                shutil.copy2(f, out / rel)


def build_reports(run_ids=None, baseline: str = "A_baseline") -> int:
    out = REPORTS / "experiments"
    out.mkdir(parents=True, exist_ok=True)
    recs = load_records(run_ids)
    if not recs:
        print("no runs in results/")
        return 1
    df = table([r["run_id"] for r in recs])
    df = df.sort_values("run_id")
    cmp = compare(df, baseline)
    df.to_csv(out / "ppa_table.csv", index=False)
    (out / "comparison.json").write_text(json.dumps(cmp, indent=2, default=str) + "\n")
    for r in recs:
        if (RESULTS / r["run_id"] / "run.json").is_file():
            curate_run(r)
    synthesis_report(next((r for r in recs if r.get("synthesis")), recs[0]))
    curate_history()
    # side-by-side floorplans
    from .visualise import side_by_side
    geos = []
    for r in sorted(recs, key=lambda x: x["run_id"]):
        g = RESULTS / r["run_id"] / "export" / "geometry.json"
        if g.is_file():
            geos.append((r["run_id"], json.loads(g.read_text())))
    if geos:
        side_by_side(geos, out / "side_by_side")
    # ---------------------------------------------------------- markdown
    md = ["# SilicaFlux-V floorplan experiments -- measured results",
          "",
          "All numbers are read from Yosys / OpenROAD / OpenSTA outputs of the runs listed (see `reports/runs/<id>/run.json`",
          "for per-run provenance: git revision, tool versions, ORFS revision, netlist hash, config hash).",
          "Timing is **PRE-ROUTE** (placement parasitics, ideal clocks, typical corner) -- not an achieved frequency.",
          "Global routing is **PRELIMINARY** (FastRoute, pre-CTS). Power is a **vectorless estimate** and is not ranked.",
          "",
          f"Baseline for deltas: `{baseline}`.  Comparable = same netlist hash, tools, ORFS revision and clock period.",
          "",
          "## Runs and status", "",
          md_table(df, ["run_id", "status", "physically_valid", "arrangement", "target_util", "failed_gates", "failure_reason"]),
          "", "## Area", "",
          md_table(df, ["run_id", "die_w_um", "die_h_um", "die_area_mm2", "core_area_mm2", "std_cell_area_placed_um2",
                        "macro_area_um2", "std_cell_util_of_rows", "core_util_incl_macros"]),
          "", "## Performance (pre-route) and routability (preliminary)", "",
          md_table(df, ["run_id", "wns_ns", "tns_ns", "whs_ns", "reg2reg_slack_ns", "reg2reg_delay_ns", "placed_hpwl_mm",
                        "inter_group_hpwl_mm", "grt_completed", "grt_overflow", "grt_hotspot_near_macro_frac",
                        "grt_wirelength_mm", "grt_wns_ns"]),
          "", "Worst register-to-register path per run (pre-route):", "",
          md_table(df, ["run_id", "reg2reg_start", "reg2reg_end", "reg2reg_slack_ns"]),
          "", "## Power (information only)", "",
          md_table(df, ["run_id", "pdn_connected", "power_vectorless_mw"]),
          "", "Power = OpenSTA `report_power` with **no switching-activity file** (input activity 0.1); IHP SRAM",
          "Liberty power data are included as provided by the macro library; clock tree not built. Not used for ranking.",
          "", "## Quality gates", "",
          md_table(df, ["run_id"] + [f"gate{i}" for i in range(1, 16)]),
          "", "## Deltas vs baseline (%)", ""]
    dd = pd.DataFrame(cmp["deltas"])
    if not dd.empty:
        md.append(md_table(dd, list(dd.columns), 2))
    # surrogate (annealing) vs measured: was the proposer any good?
    alog = RESULTS / "sweeps" / "anneal" / "anneal_log.yaml"
    if alog.is_file():
        import yaml as _y
        al = _y.safe_load(alog.read_text())
        md += ["", "## Annealing proposer vs measured results", "",
               f"Surrogate evaluations: {al.get('evaluated')}. The surrogate (optimiser.py) only proposes candidates;",
               "the rows below are the measured outcomes of the proposed runs (SA_*) next to comparable manual runs.", ""]
        sa = df[df.run_id.str.startswith("SA_") | df.run_id.isin(["C_sram_near_compute", "D_logic_consolidated",
                                                                    "L_periphery_rows", "L_west_east_columns"])]
        md.append(md_table(sa, ["run_id", "arrangement", "target_util", "die_area_mm2", "reg2reg_delay_ns",
                                "grt_overflow", "grt_wirelength_mm", "physically_valid"]))
    md += ["", "## Pareto analysis", "", f"Rule: {cmp['rule']}.", "",
           f"Eligible runs: {', '.join(cmp['eligible']) or 'none'}", "",
           f"Non-dominated (Pareto) set: **{', '.join(cmp['pareto']) or 'none'}**", "",
           "Invalid / failed runs (kept, never ranked):", ""]
    for x in cmp["invalid_runs"]:
        md.append(f"- `{x['run_id']}`: {x['status']} -- gates failed: {x['failed_gates'] or 'none'}; {x['failure_reason'] or ''}")
    (out / "summary.md").write_text("\n".join(md) + "\n")
    # ---------------------------------------------------------- html
    _html(df, cmp, out)
    print(f"reports written to {out}")
    return 0


def _html(df: pd.DataFrame, cmp: dict, out: Path) -> None:
    import plotly.graph_objects as go
    figs = []
    valid = df[df.physically_valid]
    par = set(cmp["pareto"])
    f = go.Figure()
    for sel, name, color, sym in ((df.run_id.isin(par), "Pareto (non-dominated)", BLUE, "circle"),
                                  (df.physically_valid & ~df.run_id.isin(par), "valid, dominated", GREY, "circle"),
                                  (~df.physically_valid, "invalid (gate failure) - not ranked", CRIT, "x-open")):
        d = df[sel & df.die_area_mm2.notna() & df.reg2reg_delay_ns.notna()]
        if d.empty:
            continue
        f.add_trace(go.Scatter(x=d.die_area_mm2, y=d.reg2reg_delay_ns, mode="markers+text", name=name, text=d.run_id,
                               textposition="top center", marker=dict(size=11, color=color, symbol=sym,
                                                                      line=dict(width=2, color=SURF)),
                               hovertemplate="%{text}<br>die %{x:.3f} mm2<br>reg-to-reg path %{y:.3f} ns<extra></extra>"))
    f.update_layout(title="Die area vs pre-route register-to-register path delay (lower-left is better)",
                    xaxis_title="die area (mm2)", yaxis_title="reg-to-reg critical-path delay, pre-route (ns)")
    figs.append(f)
    for metric, title in (("grt_overflow", "Global-route overflow (preliminary)"),
                          ("grt_wirelength_mm", "Global-route wirelength (mm)"),
                          ("inter_group_hpwl_mm", "Inter-group HPWL after placement (mm)"),
                          ("wns_ns", "Pre-route WNS (ns)")):
        d = df[df[metric].notna()]
        if d.empty:
            continue
        g = go.Figure(go.Bar(x=d.run_id, y=d[metric], marker=dict(color=[BLUE if v else GREY for v in d.physically_valid]),
                             hovertemplate="%{x}: %{y}<extra></extra>"))
        g.update_layout(title=title + " -- grey = invalid run", yaxis_title=metric)
        figs.append(g)
    for g in figs:
        g.update_layout(template="plotly_white", paper_bgcolor=SURF, plot_bgcolor=SURF, font=dict(color=INK, size=12),
                        margin=dict(l=60, r=20, t=60, b=60), height=420)
    parts = [f.to_html(full_html=False, include_plotlyjs=("cdn" if i == 0 else False)) for i, f in enumerate(figs)]
    rows = "".join("<tr>" + "".join(f"<td>{html.escape(_fmt(r[c]))}</td>" for c in
                                    ("run_id", "status", "die_area_mm2", "wns_ns", "reg2reg_delay_ns", "grt_overflow",
                                     "grt_wirelength_mm", "failed_gates")) + "</tr>" for _, r in df.iterrows())
    imgs = "".join(f'<figure><img src="../runs/{html.escape(r)}/floorplan.png" alt="floorplan {html.escape(r)}">'
                   f"<figcaption>{html.escape(r)}</figcaption></figure>"
                   for r in df.run_id if (REPORTS / "runs" / r / "floorplan.png").is_file())
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>FloorplanLab Results</title>
<style>:root{{--s:{SURF};--t:{INK};--t2:{INK2}}}body{{background:var(--s);color:var(--t);font:14px/1.45 system-ui,sans-serif;margin:0 auto;max-width:1200px;padding:16px}}
table{{border-collapse:collapse;width:100%;overflow-x:auto;display:block}}td,th{{border-bottom:1px solid #e3e2dc;padding:4px 8px;text-align:left;white-space:nowrap}}
figure{{display:inline-block;margin:6px;width:360px;max-width:100%}}img{{width:100%}}figcaption{{color:var(--t2);font-size:12px}}
.note{{color:var(--t2)}}</style></head><body>
<h1>SilicaFlux-V FloorplanLab -- experiment summary</h1>
<p class="note">Measured OpenROAD/OpenSTA results. Timing is pre-route (placement parasitics, ideal clocks); routing is a
preliminary global route; nothing here is signoff. Invalid runs are shown in red/grey and never ranked.
Pareto set: <b>{html.escape(', '.join(cmp['pareto']) or 'none')}</b>.</p>
<table><tr><th>run</th><th>status</th><th>die mm2</th><th>WNS ns</th><th>reg2reg ns</th><th>GRT overflow</th><th>GRT WL mm</th><th>failed gates</th></tr>{rows}</table>
{''.join(parts)}
<h2>Floorplans (OpenDB data)</h2>{imgs}
</body></html>"""
    (out / "index.html").write_text(doc)
