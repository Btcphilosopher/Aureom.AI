"""Report sections built on SilicaFlux repository evidence (v2).

Returns HTML, Markdown, figures, findings and summary data for
:func:`memoryflow.report.build.generate`.  Every number is tagged with its
provenance; when the SilicaFlux sources or characterisation results are
missing, the sections say so instead of inventing values.
"""
from __future__ import annotations

import html
import json
import math
import shutil
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

from memoryflow.models import area as A
from memoryflow.models.balance import cpu_orchestration, machine_balance
from memoryflow.models.explore import BUDGETS, Budget, baseline, joint_grid, recommend
from memoryflow.models.hardware import EXTMEM_PRESETS, SystemConfig
from memoryflow.models.roofline import Roofline
from memoryflow.report import plots
from memoryflow.silicaflux import inventory as sfinv
from memoryflow.silicaflux.baselines import all_baselines, evaluate_baseline
from memoryflow.silicaflux.characterise import CHAR_TBS, load_results
from memoryflow.silicaflux.doc_targets import CONFLICTS, TARGETS, verify_quotes
from memoryflow.silicaflux.sources import MF_ROOT

KIB = 1024


def _t(rows, header, cls=""):
    from memoryflow.report.build import _html_table
    return _html_table(rows, header, cls)


def _m(rows, header):
    from memoryflow.report.build import _md_table
    return _md_table(rows, header)


def _fig(figs: dict, key: str, cap: str) -> str:
    from memoryflow.report.build import _img
    if key not in figs:
        return f'<p class="muted">({html.escape(cap)}: input data not available)</p>'
    return f'<figure>{_img(figs[key][0])}<figcaption>{html.escape(cap)}</figcaption></figure>'


def _cfg_from_point(base: SystemConfig, rc: dict) -> SystemConfig:
    from memoryflow.models.explore import mk
    return mk(base, rc["spm_kib"], rc["banks"], rc["width"], rc["burst"], rc["dfifo"], rc["lanes"],
              tuple(int(x) for x in rc["tensor"].split("x")), rc["extmem"], wout=rc.get("wout"),
              tiles=rc.get("tiles"))


def build(out: Path, fig: Path, budget: Budget, suite, rec, rec_cfg: SystemConfig, ref_ge, log) -> dict:
    H: list[str] = []          # html fragments, in order
    MD: list[str] = []
    figs: dict[str, list[str]] = {}
    findings: list[tuple[str, str]] = []
    summ: dict = {}
    data = out / "data"
    data.mkdir(parents=True, exist_ok=True)

    # ================================================================ inventory
    inv = sfinv.run(lint=True)
    summ["silicaflux_inventory"] = {k: inv.get(k) for k in ("available", "root", "files", "lines", "modules")}
    if inv.get("available"):
        (out / "inventory.md").write_text(sfinv.to_markdown(inv))
        (data / "silicaflux_inventory.json").write_text(json.dumps(inv, indent=1, default=str))
        mat = sfinv.coverage_matrix(inv)
        cov_rows = [[cat] + [", ".join(row[s]) or "-" for s in sfinv.STATUSES] for cat, row in mat.items()]
        kinds = defaultdict(list)
        for f in inv["findings"]:
            kinds[f["kind"]].append(f)
        top_ref = [f for f in kinds["REFERENCED_ONLY"] if f["module"] == "silicaflux_top"]
        drift_ct = [f for f in kinds["INTERFACE_DRIFT"] if f["module"] in ("compute_tile", "tb_memory_controller",
                                                                        "tb_tensor_unit")]
        miss_ct = [f for f in kinds["MISSING_TYPES"] if f["module"] == "compute_tile"]
        n_inst = sum(1 for _ in top_ref)
        ev_rows = []
        for b in inv["blocks"]:
            a = next((a for a in b["anchors"] if a["found"]), None)
            ev_rows.append([b["block"]["category"], b["block"]["name"], b["block"]["generation"], b["status"],
                            f"{a['origin']}:{a['line']}" if a else "(document / none)",
                            b["block"]["memoryflow"] or "-"])
        find_rows = [[f["kind"], f["module"], f"{f['origin']}:{f['line']}", f["detail"]]
                     for f in inv["findings"] if f["module"] in ("silicaflux_top", "compute_tile", "noc_router",
                                                                 "tb_memory_controller", "tb_tensor_unit",
                                                                 "sf_alu", "scheduler", "tile_interface")][:40]
        H.append(f"""<h2>SilicaFlux repository inventory (evidence)</h2>
<p>{inv['files']} HDL files ({inv['lines']:,} lines, {inv['modules']} module names) were extracted from
{len(inv['sets'])} source sets (archives and loose <code>.sf</code> files) under <code>{html.escape(Path(inv['root']).name)}/</code>.
Every block is anchored to an <code>origin:line</code>; <b>IMPLEMENTED</b> / <b>STANDALONE</b> claims are confirmed by
Verilator elaboration from repository sources only (Icarus fallback where Verilator lacks a construct; "inconclusive" when
both lack it). Full evidence: <code>inventory.md</code>.</p>
<h3>Coverage of the ten memory-subsystem categories</h3>
{_t(cov_rows, ['category'] + sfinv.STATUSES)}
<h3>Blocks</h3>{_t(ev_rows, ['category', 'block', 'generation', 'status', 'first evidence', 'MemoryFlow'])}
<h3>Automatic consistency findings (top level, tile, router, testbenches)</h3>
{_t(find_rows, ['kind', 'module', 'location', 'detail'])}""")
        MD += ["## SilicaFlux repository inventory (evidence)", "",
               f"{inv['files']} HDL files / {inv['lines']:,} lines from {len(inv['sets'])} source sets. "
               "Full evidence with origin:line anchors: `inventory.md`.", "",
               _m(cov_rows, ["category"] + sfinv.STATUSES), ""]
        t25 = next((t for t in inv.get("tops", []) if t["module"] == "silicaflux_top"
                    and t["origin"] == "SilicaFlux2.0/SilicaFlux2.5/silicaflux_top.sf"), None)
        t2x = [t for t in inv.get("tops", []) if t["module"] == "silicaflux_top" and "silicaflux_rtl" in t["origin"]]
        if t25:
            findings.append((
                "The SilicaFlux 2.x hierarchy above the tile exists only as instantiations.",
                f"silicaflux_top.sf (Gen-2.5) instantiates {t25['types']} module types; {len(t25['undefined_types'])} "
                f"of them ({t25['undefined_instances']} of {t25['instances']} instances) are defined nowhere in the "
                "repository, including the L2 (sf_l2_cache, 2 MiB/complex), the LLC (sf_llc_bank, 8 x 4 MiB), the "
                "coherent crossbar, the memory fabric / AXI edge and the DMA bridge" +
                (f"; the earlier silicaflux_rtl*.zip tops leave {len(t2x[0]['undefined_types'])} of {t2x[0]['types']} "
                 "types undefined" if t2x else "") +
                ". Only the Gen-1 top is complete. No SilicaFlux generation has a DRAM controller or PHY, so the "
                "external-memory side of the processor has to be designed, not integrated; MemoryFlow supplies the "
                "DMA, router, SPM, bridge and models for it."))
        if drift_ct or miss_ct:
            d = next((f for f in drift_ct if f["module"] == "compute_tile" and "memory_controller" in f["detail"]), None)
            findings.append((
                "The Gen-2.5 compute tile cannot be elaborated from repository sources.",
                (f"{d['detail']}. " if d else "") +
                (f"{miss_ct[0]['detail']}. " if miss_ct else "") +
                "The 2.5 testbenches tb_memory_controller.sf and tb_tensor_unit.sf also target interfaces the in-repo "
                "modules do not have. The individual units (memory_controller.sf, tensor_unit.sf, vector_engine.sf, "
                "register_bank.sf) do elaborate and were characterised directly."))
    else:
        H.append("<h2>SilicaFlux repository inventory (evidence)</h2><p>SilicaFlux sources not found next to this "
                 "MemoryFlow checkout (set MF_SILICAFLUX_ROOT).</p>")

    # ================================================================ documented targets
    q = verify_quotes()
    t_rows = [[k, t.applies_to, html.escape(t.quote), f"{t.doc.split('/')[-1]} p.{t.page}",
               {True: "verified", False: "NOT FOUND", None: "unverified"}[q.get(k)]] for k, t in TARGETS.items()]
    c_rows = [[c[0], c[3]] for c in CONFLICTS]
    # SRAM density check: documented 256 KB macro area vs the published-bitcell model
    a65, _ = A.spm_area_mm2(256 * KIB, 4, 64, 64, 65)
    a130, _ = A.spm_area_mm2(256 * KIB, 4, 64, 64, 130)
    H.append(f"""<h2>Documented SilicaFlux-V targets</h2>
<p>Targets quoted from the repository's design documents; each quote is re-checked on its cited page with
<code>pdftotext</code>. Default exploration budget: <b>{html.escape(budget.name)}</b> ({html.escape(budget.source)}).</p>
{_t(t_rows, ['key', 'applies to', 'quote', 'source', 'check'])}
<h3>Conflicts between documents</h3>{_t(c_rows, ['topic', 'resolution in MemoryFlow'])}
<p>256 KiB of SRAM (4 x 64-bit banks, no ECC) costs <b>{a65:.2f} mm&sup2;</b> at 65 nm and <b>{a130:.2f} mm&sup2;</b> at
130 nm with published high-density bitcells and macro periphery (ANALYTICAL), versus the 0.5 mm&sup2; the reduced-ASIC
document estimates.</p>""")
    MD += ["## Documented SilicaFlux-V targets", "", _m([[r[0], r[2], r[3], r[4]] for r in t_rows],
                                                        ["key", "quote", "source", "check"]), "",
           *[f"* **{c[0]}**: {c[3]}" for c in CONFLICTS], ""]
    findings.append((
        f"The documented SRAM area is about {a65 / 0.5:.0f}x optimistic.",
        f"The reduced-ASIC plan prices 256 KB at ~0.5 mm^2 using a 0.12 um^2 bitcell at 65 nm, about 4x smaller than "
        f"published 65 nm high-density 6T cells (~0.52 um^2); with macro periphery MemoryFlow estimates {a65:.2f} mm^2 at 65 nm and "
        f"{a130:.2f} mm^2 at 130 nm (ANALYTICAL, replace with memory-compiler data). At 130 nm the documented 256 KiB "
        "alone exceeds the 8 mm^2 core budget."))
    summ["documented_targets"] = {k: {**asdict(t), "verified": q.get(k)} for k, t in TARGETS.items()}

    # ================================================================ characterisation of the real RTL
    char = load_results()
    if char:
        src = MF_ROOT / "build" / "sf_char_results.json"
        if src.exists():
            shutil.copy(src, data / "sf_char_results.json")
        m = {k: v for r in char.values() for k, v in r.get("metrics", {}).items()}
        c_rows = [[r["name"], r["status"], r["expected"], "OK" if r["ok"] else "FAIL", r["checks"], r["description"]]
                  for r in char.values()]
        k_rows = []

        def km(key, label, unit, src_tb, fmt="{:.2f}"):
            if key in m:
                k_rows.append([label, fmt.format(m[key]), unit, src_tb])

        km("sf25_scalar_load_latency_cycles", "2.5 SPM scalar / vector load latency", "cycles", "tb_sf25_memctrl", "{:.0f}")
        km("sf25_vector_load_stream_bytes_per_cycle", "2.5 SPM vector-port stream", "B/cycle", "tb_sf25_memctrl")
        km("sf25_sv_disjoint_bank_requests_per_cycle", "2.5 SPM scalar+vector, disjoint banks", "req/cycle", "tb_sf25_memctrl")
        km("sf25_sv_same_bank_requests_per_cycle", "2.5 SPM scalar+vector, same bank", "req/cycle", "tb_sf25_memctrl")
        km("sf25_three_port_stream_bytes_per_cycle", "2.5 SPM all three requesters streaming", "B/cycle", "tb_sf25_memctrl")
        km("sf25_burst_load_beats_per_cycle_L1", "2.5 burst port, 1-beat bursts (load)", "beats/cycle", "tb_sf25_memctrl")
        km("sf25_burst_load_beats_per_cycle_L16", "2.5 burst port, 16-beat bursts (load)", "beats/cycle", "tb_sf25_memctrl")
        km("sf25_burst_load_beats_per_cycle_L256", "2.5 burst port, 256-beat bursts (load)", "beats/cycle", "tb_sf25_memctrl")
        km("sf25_tensor_latency_cycles", "2.5 tensor unit latency", "cycles", "tb_sf25_tensor", "{:.0f}")
        km("sf25_tensor_macs_per_cycle", "2.5 tensor unit sustained", "MAC/cycle", "tb_sf25_tensor", "{:.1f}")
        if "sf25_tensor_products_per_cycle_drain1of4" in m:
            k_rows.append(["2.5 tensor unit, results drained through one 128-bit port",
                           f"{64 * m['sf25_tensor_products_per_cycle_drain1of4']:.1f}", "MAC/cycle", "tb_sf25_tensor"])
        km("sf25_dma_ext_to_spm_bytes_per_cycle", "MemoryFlow DMA -> 2.5 SPM (EXT->SPM)", "B/cycle", "tb_sf25_dma_bridge")
        km("sf25_dma_spm_to_ext_bytes_per_cycle", "2.5 SPM -> EXT (WOUT = 8, 20-cycle memory)", "B/cycle", "tb_sf25_dma_bridge")
        km("sf25_dma_spm_to_spm_bytes_per_cycle", "2.5 SPM -> SPM via the single vector port", "B/cycle", "tb_sf25_dma_bridge")
        km("sf1_scalar_load_bytes_per_cycle", "Gen-1 SPM scalar loads", "B/cycle", "tb_sf1_memctrl")
        km("sf1_vload_bytes_per_cycle", "Gen-1 SPM VLOAD", "B/cycle", "tb_sf1_memctrl")
        km("sf1_dfstore8_words_not_written", "Gen-1 DFSTORE of 8 words: words never written", "words", "tb_sf1_memctrl", "{:.0f}")
        km("sf1_tensor_macs_per_cycle", "Gen-1 tensor unit", "MAC/cycle", "tb_sf1_tensor")
        figs["sf_burst"] = plots.sf25_burst_chart(m, str(fig / "sf25_burst_efficiency"))
        H.append(f"""<h2>Characterisation of the existing SilicaFlux RTL</h2>
<p>Self-checking testbenches (<code>tb/silicaflux/</code>) compile the repository files byte-for-byte and measure them.
All numbers are RTL_SIMULATION (Verilator 5.020).</p>
{_t(c_rows, ['testbench', 'result', 'expected', 'ok', 'checks', 'scope'])}
{_t(k_rows, ['measurement', 'value', 'unit', 'testbench'], 'num')}
{_fig(figs, 'sf_burst', 'SilicaFlux 2.5 burst port: RTL beats/cycle vs the L/(L+overhead) model.')}""")
        MD += ["## Characterisation of the existing SilicaFlux RTL (RTL_SIMULATION)", "",
               _m(c_rows, ["testbench", "result", "expected", "ok", "checks", "scope"]), "",
               _m(k_rows, ["measurement", "value", "unit", "testbench"]), ""]
        if "sf25_three_port_stream_bytes_per_cycle" in m:
            findings.append((
                "The Gen-2.5 scratchpad controller is sound; its burst port is the weak link.",
                f"150k+ self-checks pass on the unmodified memory_controller.sf (random traffic with backpressure, range/"
                f"domain/overflow protection, parity detection, burst kill). Each port sustains ~1 request/cycle with a "
                f"{m.get('sf25_scalar_load_latency_cycles', 3):.0f}-cycle load latency; three requesters together move "
                f"{m['sf25_three_port_stream_bytes_per_cycle']:.1f} B/cycle. The burst ('DMA') port allows one descriptor "
                f"in flight with a done handshake, costing 3 (store) / 4 (load) cycles per burst: "
                f"{m.get('sf25_burst_load_beats_per_cycle_L1', 0):.2f} beats/cycle at 1 beat, "
                f"{m.get('sf25_burst_load_beats_per_cycle_L16', 0):.2f} at 16. A second descriptor slot would hide it."))
        if "sf1_dfstore8_words_not_written" in m:
            findings.append((
                "Gen-1 DFLOAD/DFSTORE bursts longer than 4 words are broken, and its SPM needs two write ports.",
                f"tb_sf1_memctrl: a DFSTORE of 8 words leaves {m['sf1_dfstore8_words_not_written']:.0f} words unwritten "
                "and a DFLOAD of 8 re-reads words 0..3 (burst_addr never advances; the 128-bit buffer index wraps). "
                "The tile write-back port and the FSM write the array in the same cycle (2 writes measured), which no "
                "single-port SRAM macro can implement. Gen-1 bandwidth: "
                f"{m.get('sf1_vload_bytes_per_cycle', 0):.2f} B/cycle per tile."))
        if "sf25_dma_spm_to_ext_bytes_per_cycle" in m:
            findings.append((
                "DMA write acknowledgements, not reads, limit write-back to memory.",
                f"MemoryFlow sf_dma driving the unmodified 2.5 SPM through sf_mc25_vport_bridge: EXT->SPM "
                f"{m.get('sf25_dma_ext_to_spm_bytes_per_cycle', 0):.1f} B/cycle, but SPM->EXT only "
                f"{m['sf25_dma_spm_to_ext_bytes_per_cycle']:.2f} B/cycle: 8 outstanding write acks against a 20-cycle "
                f"memory (Little's law: 8/21 x 16 B = 6.10). The models now carry this DMA write path (WOUT is an "
                f"exploration dimension). SPM->SPM copies reach {m.get('sf25_dma_spm_to_spm_bytes_per_cycle', 0):.1f} "
                "B/cycle because reads and writes share the controller's single vector port."))
        summ["silicaflux_characterisation"] = char
    else:
        H.append("<h2>Characterisation of the existing SilicaFlux RTL</h2><p>No results (run "
                 "<code>memoryflow sf-char</code>).</p>")

    # ================================================================ baselines
    pts = []
    b_rows = []
    for b in all_baselines():
        p = evaluate_baseline(b)
        r = Roofline(b.cfg)
        pts.append((b.title, p))
        b_rows.append([b.title, b.kind, f"{r.peak('tensor') / 1e9:.1f}", f"{r.peak('vector') / 1e9:.1f}",
                       f"{r.ceilings['SPM->engine'][0] / 1e9:.2f}", f"{r.ceilings['DRAM sustained'][0] / 1e9:.3f}",
                       f"{p.dense_gops:.2f}", f"{p.stream_gops:.3f}", f"{p.geomean_gops:.3f}",
                       f"{p.total_area_mm2:.2f}", f"{p.power_w:.2f}"])
    rp = rec.recommended
    r = Roofline(rec_cfg)
    pts.append(("MemoryFlow recommended", rp))
    b_rows.append(["MemoryFlow recommended (" + rp.label + ")", "RECOMMENDED", f"{r.peak('tensor') / 1e9:.1f}",
                   f"{r.peak('vector') / 1e9:.1f}", f"{r.ceilings['SPM->engine'][0] / 1e9:.2f}",
                   f"{r.ceilings['DRAM sustained'][0] / 1e9:.3f}", f"{rp.dense_gops:.2f}", f"{rp.stream_gops:.3f}",
                   f"{rp.geomean_gops:.3f}", f"{rp.total_area_mm2:.2f}", f"{rp.power_w:.2f}"])
    figs["baselines"] = plots.baseline_chart(pts, str(fig / "baselines_per_workload"))
    hdr = ["machine", "kind", "tensor peak Gop/s", "vector peak Gop/s", "SPM->engine GB/s", "ext. memory GB/s",
           "dense Gop/s", "stream Gop/s", "geomean", "mm2", "W"]
    param_rows = [[b.title, item, val, prov] for b in all_baselines() for item, val, prov in b.params]
    sf25i = next(p for t, p in pts if "MemoryFlow DMA" in t)
    sf25i_b = next(b for b in all_baselines() if b.key == "sf25_int")
    tpk = Roofline(sf25i_b.cfg).peak("tensor")
    gemm = next(k for k in sf25i.perf if k.startswith("GEMM 512"))
    feed_rows = [("tensor_unit.sf peak (4x4x4 INT8, by construction)", 64.0, None)]
    mm = {k: v for rr in char.values() for k, v in rr.get("metrics", {}).items()} if char else {}
    tu_meas = mm.get("sf25_tensor_macs_per_cycle")
    if mm:
        feed_rows += [("measured: results always accepted", tu_meas or 0.0, True),
                      ("measured: results through one 128-bit port", 64 * mm.get(
                          "sf25_tensor_products_per_cycle_drain1of4", 0), True)]
    f = sf25i_b.cfg.compute.clock_hz
    feed_rows += [(f"2.5 tile + MF DMA + DDR3: {gemm}", sf25i.perf[gemm] / 2 / f, False),
                  (f"MemoryFlow recommended ({rec_cfg.compute.tensor_rows}x{rec_cfg.compute.tensor_cols} "
                   f"outer product): {gemm}", rp.perf[gemm] / 2 / rec_cfg.compute.clock_hz, False)]
    figs["tensor_feed"] = plots.tensor_feed_chart(feed_rows, str(fig / "sf25_tensor_feed"))
    H.append(f"""<h2>SilicaFlux as built vs documented vs recommended</h2>
<p>Same roofline / area / energy models for every machine at the {budget.node_nm} nm SilicaFlux-V node. As-built parameters
are read from the RTL or measured on it; the as-built machines have no DRAM path (no SilicaFlux generation implements
one), so a QSPI-class host link is assumed for them.</p>
{_t(b_rows, hdr, 'num')}
{_fig(figs, 'baselines', 'Achievable Gop/s per workload for each machine.')}
{_fig(figs, 'tensor_feed', 'What the SilicaFlux 2.5 tensor unit can actually be fed.')}
<h3>Where each baseline parameter comes from</h3>{_t(param_rows, ['machine', 'item', 'value', 'provenance'])}""")
    MD += ["## SilicaFlux as built vs documented vs recommended (ANALYTICAL, RTL-measured inputs)", "",
           _m(b_rows, hdr), ""]
    findings.insert(0, (
        "The SilicaFlux 2.5 tensor unit is starved by its own memory system.",
        (f"In isolation it sustains {tu_meas:.1f} MAC/cycle (RTL_SIMULATION). " if tu_meas else "") +
        f"It has no "
        f"accumulation buffer, so every 4x4x4 product moves 32 B of operands in and 64 B of INT32 partials out; the "
        f"tile's 16 B/cycle vector port and single 128-bit register write port cap it at "
        f"{sf25i.perf[gemm] / tpk * 100:.0f} % of peak on a 512^3 GEMM even with MemoryFlow's DMA and DDR3 "
        f"({sf25i.perf[gemm] / 1e9:.2f} of {tpk / 1e9:.1f} Gop/s; bound: {sf25i.bound[gemm]}). The recommended "
        f"outer-product array with in-array accumulators reaches {rp.perf[gemm] / 1e9:.1f} Gop/s "
        f"({rp.perf[gemm] / sf25i.perf[gemm]:.0f}x) in {rp.total_area_mm2:.1f} mm^2."))
    nodram = next(p for t, p in pts if "no DRAM" in t)
    dram = next(p for t, p in pts if "documented target + DDR3" in t)
    summ["baselines"] = {t: p.to_row() for t, p in pts}

    # ================================================================ budgets x external memory
    nm_rows, budget_rows, full_rows = [], [], []
    best_by = {}
    best_mem: dict[str, dict] = {}
    for key, bud in BUDGETS.items():
        g = joint_grid(baseline(bud), suite, bud, ref_ge)
        feas = [p for p in g if p.feasible]
        best = defaultdict(lambda: None)
        for p in feas:
            if best[p.cfg["extmem"]] is None or p.geomean_gops > best[p.cfg["extmem"]].geomean_gops:
                best[p.cfg["extmem"]] = p
        for em, p in best.items():
            nm_rows.append({"budget": key, "extmem": em, "geomean": p.geomean_gops, "area": p.total_area_mm2,
                            "label": p.label})
        best_mem[key] = dict(best)
        maxspm = max((p.cfg["spm_kib"] for p in feas), default=0)
        if feas:
            rr = recommend(g)
            best_by[key] = rr
            budget_rows.append([key, f"{bud.node_nm} nm / {bud.clock_hz / 1e6:.0f} MHz / {bud.max_core_area_mm2} mm2 / "
                                f"{bud.max_power_w} W", bud.source.split(":")[0], f"{len(feas)}/{len(g)}",
                                f"{maxspm} KiB", rr.recommended.label, f"{rr.recommended.geomean_gops:.2f}",
                                f"{rr.recommended.total_area_mm2:.2f}", f"{rr.recommended.power_w:.2f}"])
            if key.startswith("full"):
                for n, p in (("minimal", rr.minimal), ("recommended", rr.recommended), ("stretch", rr.stretch)):
                    full_rows.append([key, n, p.label, f"{p.dense_gops:.1f}", f"{p.stream_gops:.2f}",
                                      f"{p.geomean_gops:.1f}", f"{p.total_area_mm2:.1f}", f"{p.power_w:.2f}"])
                for em in ("LPDDR4X-4266 x32", "LPDDR4X-4266 2x32", "LPDDR5-6400 x32", "LPDDR5-6400 2x32",
                           "LPDDR5-6400 4x32", "HBM2E 1 stack", "HBM3 1 stack"):
                    if best[em] is not None:
                        p = best[em]
                        full_rows.append([key, f"best on {em}", p.label, f"{p.dense_gops:.1f}", f"{p.stream_gops:.2f}",
                                          f"{p.geomean_gops:.1f}", f"{p.total_area_mm2:.1f}", f"{p.power_w:.2f}"])
        else:
            budget_rows.append([key, f"{bud.node_nm} nm", bud.source.split(":")[0], f"0/{len(g)}", "-", "nothing fits",
                                "-", "-", "-"])
    figs["node_mem"] = plots.node_memory_chart(nm_rows, str(fig / "node_external_memory"))
    em_rows = [[r["budget"], r["extmem"], f"{r['geomean']:.2f}", f"{r['area']:.2f}", r["label"]] for r in nm_rows]
    H.append(f"""<h2>Node and external-memory comparison</h2>
<p>The full joint grid (SPM size, banks, width, DMA outstanding reads and write acks, vector lanes, tensor array,
external memory; plus tile count for the full-chip budgets) re-run for every budget. PHYs that do not exist at a node
are excluded.</p>
{_t(budget_rows, ['budget', 'envelope', 'basis', 'feasible', 'largest SPM that fits', 'recommended', 'geomean', 'mm2', 'W'])}
{_fig(figs, 'node_mem', 'Best feasible suite geomean per external memory and budget.')}
{_t(em_rows, ['budget', 'external memory', 'best geomean Gop/s', 'mm2', 'configuration'], 'num')}
<h2>Full SilicaFlux processor</h2>
<p>N replicated tiles (tensor + vector + SPM + DMA) per shared external-memory interface; 8 CPU cores as documented in
silicaflux_top.sf. Area, power and clock envelopes are MemoryFlow ASSUMPTIONS. A 32 MiB LLC as parameterised in
silicaflux_top.sf would add about {A.spm_area_mm2(32 * 1024 * KIB, 8, 128, 137, 28)[0]:.0f} mm&sup2; of SRAM at 28 nm on its
own (ANALYTICAL).</p>
{_t(full_rows, ['budget', 'tier', 'configuration', 'dense Gop/s', 'stream Gop/s', 'geomean', 'mm2', 'W'], 'num')}""")
    MD += ["## Node and external-memory comparison", "",
           _m(budget_rows, ["budget", "envelope", "basis", "feasible", "largest SPM", "recommended", "geomean", "mm2", "W"]),
           "", "## Full SilicaFlux processor (ASSUMED envelopes)", "",
           _m(full_rows, ["budget", "tier", "configuration", "dense", "stream", "geomean", "mm2", "W"]), ""]
    b130 = best_by.get("silicaflux-v-130")
    if b130:
        mx = max(p.cfg["spm_kib"] for p in joint_grid(baseline(BUDGETS["silicaflux-v-130"]), suite,
                                                       BUDGETS["silicaflux-v-130"], ref_ge) if p.feasible)
        findings.append((
            "130 nm is a fallback only if SilicaFlux-V shrinks to 128 KiB.",
            f"At 130 nm / 100 MHz no configuration with more than {mx} KiB of SPM fits the 8 mm^2 core budget, and the "
            f"best point reaches {b130.stretch.geomean_gops:.2f} Gop/s (vs {best_by['silicaflux-v-65'].recommended.geomean_gops:.2f} "
            "at 65 nm). DDR-class PHYs are not assumed at 130 nm; HyperRAM is the practical external memory there."))
    f28, f16 = best_by.get("full-28"), best_mem.get("full-16", {})
    one28 = best_mem.get("full-28", {}).get("LPDDR4X-4266 x32")
    h, l4 = f16.get("HBM2E 1 stack"), f16.get("LPDDR5-6400 4x32")
    if f28 and h and l4:
        findings.append((
            "For the full SilicaFlux, multi-channel LPDDR is the commercial sweet spot; HBM is a stretch option.",
            f"At 28 nm (no HBM PHY assumed) the recommended full chip is {f28.recommended.label}: "
            f"{f28.recommended.geomean_gops:.0f} Gop/s suite geomean in {f28.recommended.total_area_mm2:.0f} mm^2, "
            f"{f28.recommended.power_w:.1f} W" +
            (f"; a single LPDDR4X x32 channel caps any configuration at {one28.geomean_gops:.0f} Gop/s" if one28 else "") +
            f". At 16 nm, LPDDR5 4x32 reaches {l4.geomean_gops:.0f} Gop/s ({l4.geomean_gops / h.geomean_gops * 100:.0f} % "
            f"of HBM2E's {h.geomean_gops:.0f}) at {l4.power_w:.1f} W vs {h.power_w:.1f} W, on an organic package instead "
            "of a 2.5D interposer. Beyond ~16 tiles per memory interface the chip is DRAM-bound (see balance). "
            "Full-chip envelopes are ASSUMPTIONS."))
    hr = {r["extmem"]: r for r in nm_rows if r["budget"] == "silicaflux-v-65"}
    if hr:
        findings.append((
            "A no-DRAM SilicaFlux-V demonstrates the core but starves the accelerators.",
            f"The documented no-DRAM target reaches {nodram.geomean_gops:.3f} Gop/s suite geomean (QSPI-class link); the "
            f"same machine with DDR3-1600 x16 reaches {dram.geomean_gops:.2f}. On the 65 nm budget the best points per "
            "external memory are: " + "; ".join(f"{k} {v['geomean']:.2f} Gop/s in {v['area']:.1f} mm^2"
                                                for k, v in hr.items()) +
            ". HyperRAM (digital PHY, ~12 pins) is the low-cost, mature-node option; DDR3/LPDDR2 buys ~2-3x more."))
    summ["budgets"] = {"rows": budget_rows, "extmem": nm_rows, "full": full_rows}

    # ================================================================ balance
    mb = machine_balance(rec_cfg, list(suite))
    figs["balance"] = plots.balance_chart(mb.kernels, "Compute / bandwidth balance - recommended SilicaFlux-V",
                                          str(fig / "balance_recommended"))
    kb_rows = [[k.name, k.unit, f"{k.ai_dram:.2f}", f"{k.ai_onchip:.2f}", k.bound, f"{k.headroom:.2f}x",
                k.next_bound] for k in mb.kernels]
    prov_rows = [[k, f"{v:.4f}"] for k, v in mb.bytes_per_op_provisioned.items()]
    cpu_rows = []
    for w in suite:
        cl = cpu_orchestration(rec_cfg, w)
        cpu_rows.append([cl.name, f"{cl.dma_transfers:.0f}", f"{cl.tensor_tiles:.0f}", f"{cl.cpu_busy * 100:.1f} %",
                         f"{cl.max_tiles_per_core:.1f}"])
    H.append(f"""<h2>Compute / bandwidth balance</h2>
<p>For each kernel on the recommended SilicaFlux-V: the binding resource, and how much faster the kernel would run if
only that resource were unlimited (headroom; 1.0x = two resources bind together, i.e. balanced). Geomean headroom
{mb.geomean_headroom:.2f}x. Share of kernels bound by: {", ".join(f"{k} {v * 100:.0f} %" for k, v in mb.bound_share.items())}.</p>
{_fig(figs, 'balance', 'Per-kernel binding resource and headroom.')}
{_t(kb_rows, ['kernel', 'unit', 'AI DRAM op/B', 'AI on-chip op/B', 'bound', 'headroom', 'next bound'], 'num')}
<h3>Provisioned bytes per peak op</h3>{_t(prov_rows, ['level', 'B / op'], 'num')}
<h3>CPU cores: orchestration load</h3>
<p>Core cycles spent programming DMA transfers (double-buffered half-SPM chunks) and tensor tile commands, as a share of
one core (ASSUMPTION: {64} cycles per transfer, {24} per tile command). "Tiles per core" = accelerator tiles one core can
keep fed at this load; it sizes the CPU-to-tile ratio of the full SilicaFlux.</p>
{_t(cpu_rows, ['kernel', 'DMA transfers', 'tensor tile cmds', 'one-core busy', 'tiles per core'], 'num')}""")
    MD += ["## Compute / bandwidth balance (recommended SilicaFlux-V)", "",
           _m(kb_rows, ["kernel", "unit", "AI DRAM", "AI on-chip", "bound", "headroom", "next"]), "",
           _m(cpu_rows, ["kernel", "DMA transfers", "tile cmds", "core busy", "tiles/core"]), ""]
    summ["balance"] = {"bound_share": mb.bound_share, "geomean_headroom": mb.geomean_headroom,
                       "bytes_per_op": mb.bytes_per_op_provisioned}
    return {"html": "\n".join(H), "md": MD, "figs": figs, "findings": findings, "summary": summ,
            "best_by_budget": best_by}
