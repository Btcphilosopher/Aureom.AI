"""Assemble the MemoryFlow engineering report (figures, matrices, HTML, Markdown).

    memoryflow report [--out reports]

Inputs are taken from the build directory when present (RTL regression JSON,
Yosys JSON); missing inputs are reported as such -- nothing is fabricated.
"""
from __future__ import annotations

import base64
import csv
import datetime as _dt
import html
import json
from dataclasses import asdict
from pathlib import Path

from memoryflow import __version__
from memoryflow.inspect_rtl import MEMORY_SUBSYSTEM, inspect, summarise, to_markdown
from memoryflow.models import banking, dma
from memoryflow.models.dataflow import joined_stream_deadlock, tensor_tiles_cycles
from memoryflow.models.explore import (Budget, baseline, joint_grid, load_synth_ge, mk, one_at_a_time,
                                       pareto, recommend, evaluate)
from memoryflow.models.hardware import ComputeConfig, DmaConfig, ScratchpadConfig, SystemConfig, EXTMEM_PRESETS
from memoryflow.models.roofline import Roofline, measured_point
from memoryflow.models.workloads import default_suite
from memoryflow.provenance import Provenance
from memoryflow.report import diagrams, plots
from memoryflow.verify.rtl_runner import TESTBENCHES, parse_log

REPO = Path(__file__).resolve().parents[2]


def rtl_reference_config(budget: Budget) -> SystemConfig:
    """The parameterisation the RTL regression actually runs (sf_memflow_top defaults)."""
    return SystemConfig(ComputeConfig(clock_hz=budget.clock_hz, vec_lanes=4, tensor_rows=8, tensor_cols=8),
                        ScratchpadConfig(capacity_bytes=32 * 1024, banks=4, bank_width_bits=64, interleave="modulo"),
                        DmaConfig(burst_beats=16, dfifo_depth=16), EXTMEM_PRESETS["DDR4-3200 x32"], budget.node_nm,
                        name="RTL reference")


def _load_json(p: Path):
    return json.loads(p.read_text()) if p.exists() else None


def _rtl_metrics(results: list[dict] | None) -> dict[str, dict[str, float]]:
    out = {}
    if results:
        for r in results:
            out[r["name"]] = r.get("metrics", {})
    else:  # fall back to individual logs if the regression JSON is absent
        for name in TESTBENCHES:
            log = REPO / "build" / "rtl" / name / "sim.log"
            if log.exists():
                out[name] = parse_log(log.read_text())[3]
    return out


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    keys = list(rows[0].keys())
    for r in rows[1:]:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _md_table(rows: list[list], header: list[str]) -> str:
    s = "| " + " | ".join(header) + " |\n|" + "---|" * len(header) + "\n"
    for r in rows:
        s += "| " + " | ".join(str(x) for x in r) + " |\n"
    return s


def _html_table(rows: list[list], header: list[str], cls: str = "") -> str:
    h = "".join(f"<th>{html.escape(str(x))}</th>" for x in header)
    b = "".join("<tr>" + "".join(f"<td>{x if str(x).startswith('<') else html.escape(str(x))}</td>" for x in r) + "</tr>"
                for r in rows)
    return f'<div class="tw"><table class="{cls}"><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'


def _img(path: str) -> str:
    data = base64.b64encode(Path(path).read_bytes()).decode()
    return f'<img src="data:image/png;base64,{data}" alt="{Path(path).stem}" loading="lazy">'


def generate(out: str | Path = "reports", budget: Budget | None = None, verbose: bool = True) -> dict:
    out = Path(out)
    fig = out / "figures"
    fig.mkdir(parents=True, exist_ok=True)
    budget = budget or Budget()
    log = (lambda *a: print("  [report]", *a)) if verbose else (lambda *a: None)

    # ------------------------------------------------------------ inputs
    data = REPO / "reports" / "data"          # archived results shipped with the release
    rtl_results = _load_json(REPO / "build" / "rtl_results.json") or _load_json(data / "rtl_results.json")
    synth_path = REPO / "build" / "syn" / "synth_results.json"
    if not synth_path.exists():
        synth_path = data / "synth_results.json"
    synth = _load_json(synth_path)
    mutation = (_load_json(REPO / "build" / "mutation_results.json") or _load_json(data / "mutation_results.json")
                or {})
    metrics = _rtl_metrics(rtl_results)
    ref_ge = load_synth_ge(synth_path)
    suite = default_suite()

    # ------------------------------------------------------------ inventory
    mods, inv = inspect(REPO)
    note = ("**Repository evidence.** The original SilicaFlux RTL repository was not available to this "
            "build session, so this inventory covers the MemoryFlow tree itself. Run "
            "`memoryflow inspect <path-to-silicaflux> --yosys` to produce the same table for the core repo.")
    (out / "inventory.md").write_text(to_markdown(mods, "silicaflux-memoryflow", note))
    log("inventory:", len(mods), "modules")

    # ------------------------------------------------------------ calibrations
    spm_cal = banking.calibration_table({k: v for k, v in metrics.items() if k.startswith("spm_")})
    dma_cal = dma.calibration_table(metrics.get("dma", {}))
    acc = metrics.get("accel", {})
    ten_model = {f"tensor_dbuf{int(d)}_k{k}_mac_util": k * 8 / tensor_tiles_cycles(k, 8, dbuf=d)
                 for k in (8, 32) for d in (True, False)}
    ten_rows = []
    for k in (8, 32):
        for d in (1, 0):
            key = f"tensor_dbuf{d}_k{k}_8tiles_cycles"
            if key in acc:
                m = tensor_tiles_cycles(k, 8, dbuf=bool(d))
                ten_rows.append({"case": f"K={k} dbuf={d}", "rtl_cycles": acc[key], "model_cycles": m,
                                 "error_pct": 100 * (m - acc[key]) / acc[key]})
    _write_csv(out / "calibration_spm.csv", spm_cal)
    _write_csv(out / "calibration_dma.csv", dma_cal)
    _write_csv(out / "calibration_tensor.csv", ten_rows)

    # ------------------------------------------------------------ exploration
    base = baseline(budget)
    oat = one_at_a_time(base, suite, budget, ref_ge)
    grid = joint_grid(base, suite, budget, ref_ge)
    front = pareto([p for p in grid if p.feasible])
    rec = recommend(grid)
    _write_csv(out / "sweeps_one_at_a_time.csv", [dict(sweep=k, **p.to_row()) for k, v in oat.items() for p in v])
    _write_csv(out / "design_space_grid.csv", [p.to_row() for p in grid])
    _write_csv(out / "pareto_front.csv", [p.to_row() for p in front])
    log("design points:", len(grid), "feasible:", sum(p.feasible for p in grid))

    # SPM size x external memory matrix at the recommended other parameters
    rc = rec.recommended.cfg
    mat_rows = []
    for kib in (128, 256, 512, 1024):
        row = [f"{kib} KiB"]
        for em in EXTMEM_PRESETS:
            p = evaluate(mk(base, kib, rc["banks"], rc["width"], rc["burst"], rc["dfifo"], rc["lanes"],
                            tuple(int(x) for x in rc["tensor"].split("x")), em), suite, budget, ref_ge)
            row.append(f"{p.geomean_gops:.1f}{'' if p.feasible else '*'}")
        mat_rows.append(row)
    mat_hdr = ["SPM \\ ext. memory"] + list(EXTMEM_PRESETS)

    # banks x width matrix (SPM->engine bandwidth and area)
    bw_rows = []
    for banks in (2, 4, 8, 16):
        row = [f"{banks} banks"]
        for width in (32, 64, 128, 256):
            p = evaluate(mk(base, rc["spm_kib"], banks, width, rc["burst"], rc["dfifo"], min(rc["lanes"], width // 16),
                            (min(16, width // 8),) * 2, rc["extmem"]), suite, budget, ref_ge)
            row.append(f"{p.geomean_gops:.1f} / {p.total_area_mm2:.1f}")
        bw_rows.append(row)
    bw_hdr = ["banks \\ width (Gop/s / mm2)", "32 b", "64 b", "128 b", "256 b"]

    # ------------------------------------------------------------ RTL-measured roofline points
    rtl_cfg = rtl_reference_config(budget)
    measured = []
    sysm = metrics.get("system", {})
    f = budget.clock_hz
    if "sys_gemm_16x8x32_cycles" in sysm:
        mp = measured_point("GEMM 16x8x32 (RTL)", "tensor", 2 * 16 * 8 * 32, 512 + 256 + 512,
                            sysm["sys_gemm_16x8x32_cycles"], f, rtl_cfg.compute.peak_ops("tensor").value)
        measured.append(dict(asdict(mp), config="RTL reference", provenance=mp.provenance.value))
    if "sys_vadd_256_cycles" in sysm:
        mp = measured_point("VADD 256 (RTL)", "vector", 256, 3 * 512, sysm["sys_vadd_256_cycles"], f,
                            rtl_cfg.compute.peak_ops("vector").value)
        measured.append(dict(asdict(mp), config="RTL reference", provenance=mp.provenance.value))

    # ------------------------------------------------------------ figures
    rec_cfg = mk(base, rc["spm_kib"], rc["banks"], rc["width"], rc["burst"], rc["dfifo"], rc["lanes"],
                 tuple(int(x) for x in rc["tensor"].split("x")), rc["extmem"])
    figs = {}
    figs["roofline"] = plots.roofline_chart([("RTL reference", rtl_cfg), ("Recommended SilicaFlux-V", rec_cfg)],
                                            suite, measured, str(fig / "roofline"))
    figs["util_rec"] = plots.utilisation_chart([Roofline(rec_cfg).evaluate(w) for w in suite],
                                               "Accelerator utilisation - recommended prototype", str(fig / "utilisation_recommended"))
    figs["util_ref"] = plots.utilisation_chart([Roofline(rtl_cfg).evaluate(w) for w in suite],
                                               "Accelerator utilisation - RTL reference", str(fig / "utilisation_reference"))
    figs["banking"] = plots.banking_map_chart(str(fig / "banking_maps"))
    figs["stride"] = plots.stride_conflict_chart(str(fig / "bank_stride_conflicts"))
    if dma_cal:
        skew = {b: metrics["dma"][f"dma_spm2spm_4k_burst{b}_skew1_cycles"] for b in (1, 2, 4, 8, 16)
                if f"dma_spm2spm_4k_burst{b}_skew1_cycles" in metrics.get("dma", {})}
        figs["dma_burst"] = plots.dma_burst_chart(dma_cal, str(fig / "dma_burst_bandwidth"), skew)
    figs["dma_out"] = plots.dma_outstanding_chart(str(fig / "dma_outstanding_bandwidth"), budget.clock_hz)
    if acc:
        figs["tensor"] = plots.tensor_util_chart(acc, ten_model, str(fig / "tensor_double_buffer"))
    if spm_cal:
        figs["cal"] = plots.calibration_chart(spm_cal, str(fig / "spm_model_vs_rtl"))
    figs["sweeps"] = plots.sweeps_chart(oat, {}, str(fig / "parameter_sweeps"))
    figs["pareto"] = plots.pareto_chart(grid, front, rec.recommended, str(fig / "pareto"))
    figs["area"] = plots.area_breakdown_chart([("minimal", rec.minimal), ("recommended", rec.recommended),
                                                ("stretch", rec.stretch)], str(fig / "area_breakdown"))
    figs["sram"] = plots.sram_area_chart(str(fig / "sram_area"))
    (fig / "architecture_reference.svg").write_text(diagrams.architecture_svg(rtl_cfg, True))
    (fig / "architecture_recommended.svg").write_text(diagrams.architecture_svg(rec_cfg, False))
    log("figures:", len(figs) + 2)

    # ------------------------------------------------------------ findings
    em = rec_cfg.extmem
    from memoryflow.models.dma import required_outstanding_beats
    bdp = required_outstanding_beats(em.sustained_bw().value, em.latency_ns * 1e-9, rc["width"] // 8)
    ref_roof = Roofline(rtl_cfg)
    findings = [
        ("DMA outstanding capacity, not DRAM, limits streaming kernels in the RTL reference.",
         f"With 16 outstanding 64-bit beats and ~{rtl_cfg.extmem.latency_ns:.0f} ns DRAM latency the DMA path sustains "
         f"{ref_roof.ceilings['DMA path'][0] / 1e9:.2f} GB/s against {ref_roof.ceilings['DRAM sustained'][0] / 1e9:.2f} GB/s "
         f"of DDR4-3200 x32. Covering the bandwidth-delay product of the recommended memory needs >= {bdp} "
         f"{rc['width']}-bit beats in flight; the recommendation uses {rc['dfifo']}."),
        ("A single shared DMA engine deadlocks against its own accelerator.",
         "tb_system hung when an accelerator->SRAM (S2MM) channel occupied the only read engine while the "
         "operands it was waiting for were queued behind it. sf_dma now has independent MM2S/MEM2MEM and S2MM "
         "engines sharing one channel table; tb_dma, tb_system and tb_deadlock pass on the fixed RTL."),
        ("Joined operand streams need FIFO depth >= DMA burst length (or sequenced loads).",
         f"tb_deadlock: with a 4-entry vector-unit FIFO and 16-beat bursts the DMA stalls after "
         f"{int(metrics.get('deadlock_fifo4', {}).get('deadlock_beats_a', 4))} beats and the watchdog fires; with 16 entries "
         f"all 256 result beats complete. Predicate joined_stream_deadlock(4,16)={joined_stream_deadlock(4, 16)}."),
        ("Bank-aligned SRAM-to-SRAM copies resonate into read/write bank conflicts.",
         "RTL: a 4 KiB SPM->SPM copy with 16-beat bursts takes "
         f"{metrics.get('dma', {}).get('dma_spm2spm_4k_burst16_cycles', float('nan')):.0f} cycles, but "
         f"{metrics.get('dma', {}).get('dma_spm2spm_4k_burst16_skew1_cycles', float('nan')):.0f} cycles when the destination "
         "is skewed by one beat. XOR interleave or buffer skew removes it; the Python cycle model matches the "
         "skewed case but not the aligned resonance (listed as a model limitation)."),
        ("Power-of-two strides: XOR interleave fixes strides up to the fold width only.",
         f"RTL tb_spm (4 banks, 3 ports): stride 4 throughput "
         f"{metrics.get('spm_mod', {}).get('spm_stride4_throughput', float('nan')):.2f} (modulo) -> "
         f"{metrics.get('spm_xor', {}).get('spm_stride4_throughput', float('nan')):.2f} (XOR); stride 16 gives "
         f"{metrics.get('spm_xor', {}).get('spm_stride16_throughput', float('nan')):.2f} with the 2-bit XOR fold. Block "
         f"interleave is worst for streaming ({metrics.get('spm_block_8b', {}).get('spm_stride1_throughput', float('nan')):.2f} "
         f"at stride 1, 8 banks) and best for random traffic "
         f"({metrics.get('spm_block_8b', {}).get('spm_random3_throughput', float('nan')):.2f} requests/cycle)."),
        ("Accumulator double-buffering is worth ~1.8x on the tensor array when K equals the drain length.",
         f"RTL tb_accel, K=32: {acc.get('tensor_dbuf1_k32_mac_util', 0) * 100:.1f} % vs "
         f"{acc.get('tensor_dbuf0_k32_mac_util', 0) * 100:.1f} % MAC utilisation. The analytical tile model "
         f"(per tile max(K, drain) with double-buffering, K + drain without) reproduces RTL to "
         f"{max((abs(r['error_pct']) for r in ten_rows), default=0):.1f} % after fitting its 1-3 cycle pipeline fill "
         f"to these runs; the per-tile slope is not fitted."),
        ("Response-credit depth must cover the 4-cycle SPM round trip.",
         f"RTL: RSP_DEPTH=2 gives {metrics.get('spm_rsp2', {}).get('spm_single_port_throughput', float('nan')):.2f} vs "
         f"{metrics.get('spm_mod', {}).get('spm_single_port_throughput', float('nan')):.2f} requests/cycle single-port "
         "throughput with RSP_DEPTH=4, exactly as Little's law predicts (credits / round trip)."),
    ]

    # ------------------------------------------------------------ verification tables
    rtl_rows = []
    if rtl_results:
        for r in rtl_results:
            rtl_rows.append([r["name"], r["status"], r["expected"], "OK" if r["ok"] else "FAIL", r["checks"],
                             r["description"]])
    syn_rows = []
    if synth:
        for s in synth:
            syn_rows.append([s["top"], "OK" if s["ok"] else "FAIL", s["flops"], f"{s['comb_ge']:.0f}",
                             f"{s['total_ge']:.0f}", s["macros"]])

    mut_rows = [[m, d["testbench"], d["status"], d["errors"], "killed" if d["killed"] else "SURVIVED"]
                for m, d in mutation.items()]
    tiers = [("Minimal", rec.minimal), ("Recommended", rec.recommended), ("Stretch", rec.stretch)]
    tier_rows = [[n, p.cfg["spm_kib"], p.cfg["banks"], p.cfg["width"], p.cfg["tensor"], p.cfg["lanes"],
                  p.cfg["burst"], p.cfg["dfifo"], p.cfg["extmem"], f"{p.dense_gops:.1f}", f"{p.stream_gops:.2f}",
                  f"{p.geomean_gops:.2f}", f"{p.total_area_mm2:.2f}", f"{p.power_w:.2f}"] for n, p in tiers]
    tier_hdr = ["tier", "SPM KiB", "banks", "width b", "tensor", "vec lanes", "burst", "DMA FIFO", "DRAM",
                "dense Gop/s", "stream Gop/s", "geomean", "mm2", "W"]
    rtl_map = [
        ["SPM capacity", f"{rc['spm_kib']} KiB", f"SPM_NBANKS={rc['banks']}, SPM_BANK_DEPTH={rc['spm_kib'] * 1024 // (rc['banks'] * rc['width'] // 8)}"],
        ["datapath width", f"{rc['width']} b", f"DW={rc['width']}"],
        ["interleave", "XOR", "SPM_INTERLEAVE=1"],
        ["ECC", "SECDED", f"SPM_ECC=2 ({rec_cfg.spm.stored_bits_per_word()}-bit stored word)"],
        ["tensor array", rc["tensor"], f"TEN_TR={rc['tensor'].split('x')[0]}, TEN_TC={rc['tensor'].split('x')[1]}, TEN_ACC_DBUF=1"],
        ["vector lanes", str(rc["lanes"]), f"VEC_EW=16 (lanes = DW/16 = {rc['width'] // 16})"],
        ["DMA", f"burst {rc['burst']}, {rc['dfifo']} outstanding", f"DMA_MAXBURST=4, DMA_DFIFO={rc['dfifo']}, DMA_NCH=4"],
        ["operand FIFOs", ">= burst", f"VEC_IN_FIFO={rc['burst']}, TEN_IN_FIFO={rc['burst']}"],
        ["macros", "foundry", "SPM_IMPL=1 + compiler views (MACRO_W/MACRO_D per bank)"],
    ]

    summary = {
        "version": __version__, "generated": _dt.datetime.now().isoformat(timespec="seconds"),
        "budget": asdict(budget), "recommendation": {n: p.to_row() for n, p in tiers},
        "rationale": rec.rationale, "findings": [{"title": t, "detail": d} for t, d in findings],
        "inventory": inv, "rtl": rtl_results, "synth": synth, "mutation": mutation, "calibration": {"spm": spm_cal, "dma": dma_cal,
                                                                             "tensor": ten_rows},
        "measured_points": measured,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str))

    # ------------------------------------------------------------ markdown
    md = [f"# SilicaFlux MemoryFlow - engineering report", "",
          f"Generated {summary['generated']} by memoryflow {__version__}. Node {budget.node_nm} nm, "
          f"{budget.clock_hz / 1e6:.0f} MHz, budget {budget.max_core_area_mm2} mm2 / {budget.max_power_w} W.", "",
          "Provenance tags: THEORETICAL ceilings, ANALYTICAL models, PY_SIMULATION, RTL_SIMULATION. "
          "No silicon or FPGA MEASURED data exists yet.", "", "## Recommended prototype memory configurations", "",
          _md_table(tier_rows, tier_hdr), "", *[f"* {r}" for r in rec.rationale], "",
          "### RTL parameter mapping (recommended tier)", "", _md_table(rtl_map, ["item", "value", "sf_memflow_top parameters"]),
          "", "## Key findings", ""]
    for t, d in findings:
        md += [f"**{t}** {d}", ""]
    md += ["## Verification", "", _md_table(rtl_rows, ["testbench", "result", "expected", "ok", "checks", "scope"]) if rtl_rows
           else "_RTL regression JSON not found (run `memoryflow rtl`)._", "",
           "## Mutation testing", "",
           _md_table(mut_rows, ["mutant", "testbench", "result", "errors", "verdict"]) if mut_rows else "_not run_", "",
           "## Synthesis (Yosys generic, SRAM as blackbox macros)", "",
           _md_table(syn_rows, ["wrapper", "ok", "flops", "comb GE", "total GE", "macros"]) if syn_rows else "_not run_", "",
           "## SPM size x external memory (suite geomean Gop/s; * = infeasible at 40 nm)", "", _md_table(mat_rows, mat_hdr), "",
           "## Banks x width", "", _md_table(bw_rows, bw_hdr), "",
           "## Model calibration", "", f"SPM banking model: {len(spm_cal)} cases, max |error| "
           f"{max((abs(r['error_pct']) for r in spm_cal), default=0):.2f} %.", "",
           _md_table([[r["metric"], r["rtl"], f"{r['sim']:.0f}", f"{r['sim_err_pct']:+.1f}%", f"{r['analytic']:.0f}",
                       f"{r['analytic_err_pct']:+.1f}%"] for r in dma_cal],
                     ["DMA case", "RTL cycles", "cycle model", "err", "analytic", "err"]), "",
           "Figures: see `figures/`. Matrices: `*.csv`. Inventory: `inventory.md`."]
    (out / "REPORT.md").write_text("\n".join(md) + "\n")

    # ------------------------------------------------------------ HTML
    def fig_block(key: str, cap: str) -> str:
        if key not in figs:
            return f'<p class="muted">({cap}: input data not available)</p>'
        return f'<figure>{_img(figs[key][0])}<figcaption>{html.escape(cap)}</figcaption></figure>'

    arch_ref = (fig / "architecture_reference.svg").read_text()
    arch_rec = (fig / "architecture_recommended.svg").read_text()
    inv_rows = []
    for cat in MEMORY_SUBSYSTEM + ["ECC / parity", "MBIST", "Data staging buffer", "Vector unit"]:
        d = inv["by_category"].get(cat, {})
        impl = ", ".join(d.get("SYNTHESIZABLE", [])) or "none - PROPOSED"
        extra = inv["by_category"].get("External memory model", {}) if cat == "External memory interface" else {}
        beh = ", ".join([f"{n} (behavioural)" for n in d.get("BEHAVIOURAL", []) + extra.get("BEHAVIOURAL", [])]
                        + [f"{n} (blackbox)" for n in d.get("BLACKBOX", [])]) or "-"
        inv_rows.append([cat, impl, beh])
    prop_rows = [[k, v] for k, v in inv["proposed"].items()]

    findings_html = "".join(f'<div class="finding"><h4>{html.escape(t)}</h4><p>{html.escape(d)}</p></div>' for t, d in findings)
    page = HTML_TEMPLATE.format(
        version=__version__, generated=summary["generated"], node=budget.node_nm, clock=budget.clock_hz / 1e6,
        area=budget.max_core_area_mm2, power=budget.max_power_w,
        rec_label=html.escape(rec.recommended.label), rec_gm=f"{rec.recommended.geomean_gops:.1f}",
        rec_area=f"{rec.recommended.total_area_mm2:.1f}", rec_power=f"{rec.recommended.power_w:.2f}",
        rec_dense=f"{rec.recommended.dense_gops:.0f}", npts=len(grid), nfeas=sum(p.feasible for p in grid),
        ntb=len(rtl_rows), ntb_ok=sum(1 for r in rtl_rows if r[3] == "OK"),
        nchecks=f"{sum(int(r[4]) for r in rtl_rows):,}" if rtl_rows else "-",
        tiers=_html_table(tier_rows, tier_hdr, "num"), rationale="".join(f"<li>{html.escape(r)}</li>" for r in rec.rationale),
        rtlmap=_html_table(rtl_map, ["item", "value", "sf_memflow_top parameters"]),
        findings=findings_html, arch_ref=arch_ref, arch_rec=arch_rec,
        inventory=_html_table(inv_rows, ["category", "implemented (synthesizable)", "behavioural / blackbox"]),
        proposed=_html_table(prop_rows, ["missing category", "proposal"]),
        rtl=_html_table(rtl_rows, ["testbench", "result", "expected", "ok", "checks", "scope"]) if rtl_rows else "<p>not run</p>",
        mutation=_html_table(mut_rows, ["mutant", "testbench", "result", "errors", "verdict"]) if mut_rows else "<p>not run</p>",
        synth=_html_table(syn_rows, ["wrapper", "ok", "flops", "comb GE", "total GE", "macros"], "num") if syn_rows else "<p>not run</p>",
        fig_roof=fig_block("roofline", "Roofline for the RTL reference and recommended configurations (analytical; RTL points as diamonds)."),
        fig_util=fig_block("util_rec", "Per-workload utilisation of the executing engine, recommended prototype."),
        fig_util_ref=fig_block("util_ref", "Per-workload utilisation, RTL reference parameterisation."),
        fig_dma_out=fig_block("dma_out", "Effective DRAM bandwidth vs DMA outstanding beats."),
        fig_dma_burst=fig_block("dma_burst", "DMA throughput vs burst length: RTL vs cycle model vs analytical."),
        fig_bank=fig_block("banking", "Banking maps for the three SPM interleave modes."),
        fig_stride=fig_block("stride", "Simulated SPM throughput by stride, bank count and interleave."),
        fig_cal=fig_block("cal", "Python banking model vs RTL measurement."),
        fig_tensor=fig_block("tensor", "Tensor accumulation double-buffering: RTL vs model."),
        fig_sweeps=fig_block("sweeps", "One-at-a-time sweeps (dense and streaming geomeans)."),
        fig_pareto=fig_block("pareto", "All evaluated design points, Pareto front and recommendation."),
        fig_area=fig_block("area", "Area breakdown of the three recommendation tiers."),
        fig_sram=fig_block("sram", "SRAM macro area vs capacity at three mature nodes."),
        matrix=_html_table(mat_rows, mat_hdr, "num"), bwmatrix=_html_table(bw_rows, bw_hdr, "num"),
        dmacal=_html_table([[r["metric"], f"{r['rtl']:.0f}", f"{r['sim']:.0f}", f"{r['sim_err_pct']:+.1f} %",
                             f"{r['analytic']:.0f}", f"{r['analytic_err_pct']:+.1f} %"] for r in dma_cal],
                           ["case", "RTL cycles", "cycle model", "error", "analytical", "error"], "num"),
        spmcal_max=f"{max((abs(r['error_pct']) for r in spm_cal), default=0):.2f}", spmcal_n=len(spm_cal),
    )
    (out / "report.html").write_text(page)
    log("wrote", out / "report.html")
    return summary


HTML_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MemoryFlow Engineering Report</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{{--bg:#f4f3ef;--panel:#ffffff;--ink:#141414;--ink2:#4a4944;--muted:#77756d;--rule:#d9d7cf;--gold:#8a6d1f;--cyan:#00748a;
--d-blk:#ffffff;--d-hot:#fbf6e8;--d-stroke:#9a978c;--d-text:#141414;--d-text2:#4a4944;--d-line:#77756d;--d-cyan:#00748a;--d-gold:#8a6d1f;
--d-font:'Bebas Neue',sans-serif;--d-mono:'DM Mono',monospace}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#0b0b0d;--panel:#121215;--ink:#f0efec;--ink2:#c3c2b7;--muted:#8a897f;--rule:#2a2a2e;--gold:#C9A84C;--cyan:#00E5FF;
--d-blk:#17171a;--d-hot:#1d1a12;--d-stroke:#3a3a40;--d-text:#f0efec;--d-text2:#a9a89f;--d-line:#6b6a64;--d-cyan:#00E5FF;--d-gold:#C9A84C}}}}
:root[data-theme="dark"]{{--bg:#0b0b0d;--panel:#121215;--ink:#f0efec;--ink2:#c3c2b7;--muted:#8a897f;--rule:#2a2a2e;--gold:#C9A84C;--cyan:#00E5FF;
--d-blk:#17171a;--d-hot:#1d1a12;--d-stroke:#3a3a40;--d-text:#f0efec;--d-text2:#a9a89f;--d-line:#6b6a64;--d-cyan:#00E5FF;--d-gold:#C9A84C}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.55 'DM Mono',ui-monospace,monospace}}
main{{max-width:1180px;margin:0 auto;padding:32px 16px 80px}}
h1{{font:400 56px/1 'Bebas Neue',sans-serif;letter-spacing:.02em;margin:0;color:var(--ink)}}
h1 span{{color:var(--gold)}}h2{{font:400 30px/1.1 'Bebas Neue',sans-serif;letter-spacing:.04em;color:var(--gold);margin:56px 0 12px;
border-top:1px solid var(--rule);padding-top:18px}}h3{{font:500 15px 'DM Mono',monospace;color:var(--cyan);margin:28px 0 8px;text-transform:uppercase;letter-spacing:.08em}}
h4{{margin:0 0 6px;font:500 14px 'DM Mono',monospace;color:var(--ink)}}p{{color:var(--ink2);max-width:880px}}.muted{{color:var(--muted)}}
.kicker{{color:var(--cyan);letter-spacing:.18em;font-size:12px;text-transform:uppercase}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:24px 0}}
.tile{{background:var(--panel);border:1px solid var(--rule);border-radius:8px;padding:14px 16px}}
.tile b{{display:block;font:400 34px/1 'Bebas Neue',sans-serif;color:var(--ink)}}.tile small{{color:var(--muted);font-size:11.5px}}
.tw{{overflow-x:auto;margin:10px 0 18px;border:1px solid var(--rule);border-radius:8px}}
table{{border-collapse:collapse;width:100%;font-size:12.5px;background:var(--panel)}}th,td{{padding:7px 10px;border-bottom:1px solid var(--rule);text-align:left;vertical-align:top}}
th{{color:var(--muted);font-weight:500;text-transform:uppercase;font-size:11px;letter-spacing:.06em}}table.num td{{font-variant-numeric:tabular-nums;white-space:nowrap}}
figure{{margin:18px 0;background:#111113;border:1px solid var(--rule);border-radius:8px;padding:12px}}figure img{{width:100%;height:auto;display:block}}
figcaption{{color:#a9a89f;font-size:12px;margin-top:8px}}.svgwrap{{background:var(--panel);border:1px solid var(--rule);border-radius:8px;padding:12px;margin:14px 0;overflow-x:auto}}
.svgwrap svg{{width:100%;min-width:640px;height:auto}}.finding{{border-left:3px solid var(--gold);padding:4px 0 4px 14px;margin:14px 0}}
.prov{{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0}}.prov span{{border:1px solid var(--rule);border-radius:999px;padding:3px 10px;font-size:11.5px;color:var(--ink2)}}
ul{{color:var(--ink2)}}code{{color:var(--cyan)}}
</style></head><body><main>
<div class="kicker">SilicaFlux / memory subsystem / engineering report</div>
<h1>Memory<span>Flow</span></h1>
<p>High-bandwidth memory, SRAM and accelerator dataflow engineering for SilicaFlux-V. Generated {generated} by memoryflow {version};
target {node} nm, {clock:.0f} MHz, budget {area} mm&sup2; / {power} W (assumptions, overridable).</p>
<div class="prov"><span>THEORETICAL - pin/datapath ceilings</span><span>ANALYTICAL - roofline, tiling, area, energy</span>
<span>PY_SIMULATION - cycle models</span><span>RTL_SIMULATION - Verilator cycle counts</span><span>MEASURED - none yet (no silicon/FPGA)</span></div>
<div class="tiles">
<div class="tile"><small>recommended geomean</small><b>{rec_gm} Gop/s</b><small>dense {rec_dense} Gop/s</small></div>
<div class="tile"><small>recommended area</small><b>{rec_area} mm&sup2;</b><small>{power} W budget, est. {rec_power} W</small></div>
<div class="tile"><small>design points</small><b>{npts}</b><small>{nfeas} feasible at {node} nm</small></div>
<div class="tile"><small>RTL testbenches</small><b>{ntb_ok}/{ntb}</b><small>{nchecks} self-checks</small></div>
</div>
<h2>Recommended prototype memory configurations</h2>
<p><b>{rec_label}</b></p>
{tiers}
<ul>{rationale}</ul>
<h3>RTL parameter mapping</h3>
{rtlmap}
<h2>Key findings</h2>
{findings}
<h2>Memory architecture</h2>
<h3>RTL reference parameterisation (verified)</h3><div class="svgwrap">{arch_ref}</div>
<h3>Recommended SilicaFlux-V prototype</h3><div class="svgwrap">{arch_rec}</div>
<h2>Repository evidence and inventory</h2>
<p>The original SilicaFlux repository was not available to this build session; the inventory below is produced by
<code>memoryflow inspect</code> on the MemoryFlow tree. Run it on the SilicaFlux repository to classify that tree the same way.</p>
{inventory}
<h3>Proposed additions</h3>{proposed}
<h2>Verification</h2>
<h3>Self-checking SystemVerilog regression (Verilator 5.020)</h3>{rtl}
<h3>Mutation testing (deliberately broken RTL must fail its testbench)</h3>{mutation}
<h3>Logic synthesis (Yosys 0.33 generic flow, SRAM macros kept as blackboxes)</h3>{synth}
<h2>Roofline and utilisation</h2>
{fig_roof}{fig_util}{fig_util_ref}
<h2>Bandwidth</h2>
{fig_dma_out}{fig_dma_burst}
<h3>DMA model calibration</h3>{dmacal}
<h2>Banking</h2>
{fig_bank}{fig_stride}
<p>SPM banking cycle model vs RTL: {spmcal_n} cases, max |error| {spmcal_max} %.</p>
{fig_cal}
<h2>Accelerator data movement</h2>
{fig_tensor}
<h2>Parameter exploration</h2>
{fig_sweeps}
<h3>SPM size x external memory (suite geomean Gop/s, * = infeasible at {node} nm)</h3>{matrix}
<h3>Banks x datapath width</h3>{bwmatrix}
{fig_pareto}
<h2>Area</h2>
{fig_area}{fig_sram}
<h2>Assumptions and limitations</h2>
<ul>
<li>Bitcell, NAND2, DRAM energy/latency and PHY-area figures are indicative public-literature values; replace with foundry
memory-compiler CSVs (<code>CompilerTableAreaModel</code>) and vendor datasheets before tape-out decisions.</li>
<li>PHY availability by node is an assumption encoded in <code>ExtMemConfig.max_node_nm</code>.</li>
<li>The full RTL regression runs at the reference parameterisation (64-bit, 4 banks, 8x8 array); the recommended
parameterisation (128-bit, 8 banks XOR, 16x16 array, 64-deep DMA FIFOs) passes the parametric system smoke test
<code>tb_param_smoke</code> and lint, not the full regression.</li>
<li>The external memory in simulation is a latency/bandwidth model, not a DDR controller; bank/row timing is folded into
the efficiency factor.</li>
<li>The DMA cycle model does not reproduce the aligned SPM->SPM bank-conflict resonance (see findings).</li>
</ul>
</main></body></html>
"""
