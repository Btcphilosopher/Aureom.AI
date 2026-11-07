"""Run the fictional demo end to end and print a compact report.

Usage::

    python -m housebuilder_vision.demo.run_demo [--out exports/demo] [--samples 500] [--side-view]

Steps: :func:`~housebuilder_vision.demo.build_demo.build_demo_project` ->
:func:`~housebuilder_vision.pipeline.run_pipeline` (analysis, calibration, hypotheses,
twin, quantities, programme / logistics / carbon / heat loss, cost, uncertainty
simulation, repeat-build economics, build-scenario comparison) ->
:func:`~housebuilder_vision.pipeline.export_project` (project.json, results.json,
twin.glb, CSV tables, twin.ifc when ``ifcopenshell`` is installed, manifest).

Runs offline (bundled detection fixtures, the offline
:func:`~housebuilder_vision.demo.build_demo.demo_registry`; no network and no optional
dependency required) in well under a minute.  The only way it reaches an external
service is the explicit opt-in ``HBV_ENABLE_VLM=1`` (Claude VLM adapter, needs
``ANTHROPIC_API_KEY``).  Every price is FICTIONAL; every interval is assumed scenario
uncertainty, not a calibrated statistic.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Iterable, Optional, Sequence, TextIO

from ..core.models import QuantityStatus
from ..core.provenance import Basis

__all__ = ["main", "format_report", "run"]

BANNER = ("Aureom Housebuilder.OS Vision - FICTIONAL demonstration (synthetic images, fictional survey "
          "dimension and prices). Conceptual reconstruction: not a survey, design, tender price or compliance check.")


def _money(v: Optional[float], cur: str = "GBP") -> str:
    if v is None or v != v:
        return "n/a"
    return f"{cur} {v:,.0f}"


def _rng(tv, fmt: str = "{:.2f}") -> str:
    if tv is None or tv.value is None:
        return "unknown"
    s = fmt.format(tv.value)
    if tv.low is not None and tv.high is not None and tv.high > tv.low:
        s += f" ({fmt.format(tv.low)}-{fmt.format(tv.high)})"
    return f"{s} {tv.unit}".strip() + f" [{tv.basis.value}]"


def _table(rows: Sequence[Sequence[str]], header: Sequence[str]) -> list[str]:
    cols = [header, *rows]
    widths = [max(len(str(r[i])) for r in cols) for i in range(len(header))]
    fmt = "  ".join("{:<%d}" % w if i == 0 else "{:>%d}" % w for i, w in enumerate(widths))
    out = ["  " + fmt.format(*header), "  " + "  ".join("-" * w for w in widths)]
    out += ["  " + fmt.format(*[str(c) for c in r]) for r in rows]
    return out


def format_report(project, result, manifest=None) -> str:
    """Compact plain-text report of a :class:`PipelineResult` (and optional export manifest)."""
    from ..io.ifc_adapter import provenance_counts

    cur = project.settings.currency
    L: list[str] = [BANNER, ""]
    an = result.analysis
    # ---------------------------------------------------------------- evidence
    L.append("1. Evidence")
    if an is not None:
        for img in an.images:
            L.append(f"  image {img.image_id}  {img.original_filename}  {img.kind.value} / {img.view.value}  "
                     f"{img.width_px}x{img.height_px}px  sha256 {img.sha256[:12]}...")
        feats = an.all_features()
        by_basis = Counter(f.basis.value for f in feats)
        L.append(f"  {len(feats)} active features by basis: "
                 + ", ".join(f"{b} {by_basis.get(b, 0)}" for b in [x.value for x in Basis]))
        L.append(f"  {len(an.facades)} facade observation(s): "
                 + ", ".join(f"{f.view.value}/{f.block_hint}" for f in an.facades))
        L.append(f"  {len(an.unknowns)} unknown(s) carried (e.g. '{an.unknowns[0][:90]}...')" if an.unknowns else
                 "  no unknowns listed")
    pc = provenance_counts(result.twin)
    L.append("  twin parameters by basis: " + ", ".join(
        f"{k} {pc.get(k, 0)}" for k in ("observed", "inferred", "user_confirmed", "assumed", "unknown")))
    L.append("")
    # ---------------------------------------------------------------- calibration
    cal = result.calibration
    L.append("2. Calibration")
    if cal is not None:
        L.append(f"  method {cal.method}: {_rng(cal.metres_per_pixel, '{:.5f}')}")
        if cal.reference is not None:
            r = cal.reference
            L.append(f"  reference {r.real_length:.2f} {r.unit} +/- {r.tolerance:.2f} - {r.description}")
        if cal.notes:
            L.append(f"  next: {cal.notes[-1][:150]}")
    L.append("")
    # ---------------------------------------------------------------- hypotheses
    L.append("3. Geometry hypotheses (plausibility = subjective prior, not a probability)")
    for h in result.hypotheses:
        mark = "*" if h.hypothesis_id == result.selected_hypothesis_id else " "
        main = next((b for b in h.blocks if b.role.value == "main"), h.blocks[0])
        L.append(f" {mark}{h.hypothesis_id} {h.name} (p={h.plausibility:.2f}); {len(h.blocks)} block(s)")
        L.append(f"     main width {_rng(main.width)}; depth {_rng(main.depth)}; pitch {_rng(main.roof.pitch_deg, '{:.1f}')}")
    L.append("")
    # ---------------------------------------------------------------- twin
    twin, g = result.twin, result.boq.geometry
    L.append(f"4. Twin '{twin.twin_id}' v{twin.version} (hypothesis {twin.source_hypothesis_id})")
    for b in twin.blocks:
        L.append(f"  {b.block_id:8s} {b.role.value:9s} {b.width.value:.2f} x {b.depth.value:.2f} m, "
                 f"{int(b.storeys.value or 0)} storey(s), {b.roof.form.value} roof "
                 f"{(b.roof.pitch_deg.value or 0):.1f} deg, {'heated' if b.heated else 'unheated'}")
    obs = sum(1 for o in twin.openings if not o.hidden_side_rule)
    L.append(f"  openings: {obs} observed, {len(twin.openings) - obs} rule-filled on hidden facades (assumed)")
    L.append(f"  GEA {g.gea_m2:.1f} m2, GIA {g.gia_m2:.1f} m2 (heated {g.heated_gia_m2:.1f}), external wall net "
             f"{g.external_wall_net_m2:.1f} m2, roof surface {g.roof_surface_area_m2:.1f} m2, wall thickness "
             f"{g.external_wall_thickness_m:.3f} m")
    sel = twin.assemblies
    L.append(f"  assemblies (assumed unless confirmed): wall {sel.external_wall}, roof {sel.pitched_roof}, "
             f"floor {sel.ground_floor}, foundation {sel.foundation}")
    L.append("")
    # ---------------------------------------------------------------- BoQ
    est = result.estimate
    by_q: dict[str, float] = {}
    for cl in est.lines:
        if cl.quantity_line_id:
            by_q[cl.quantity_line_id] = by_q.get(cl.quantity_line_id, 0.0) + cl.amount
    boq_lines = {ln.line_id: ln for ln in result.boq.lines}
    top = sorted(by_q.items(), key=lambda kv: -kv[1])[:8]
    n_status = Counter(ln.status.value for ln in result.boq.lines)
    L.append(f"5. Bill of quantities: {len(result.boq.lines)} lines ("
             + ", ".join(f"{k} {v}" for k, v in sorted(n_status.items())) + "); top lines by cost")
    rows = []
    for lid, amt in top:
        ln = boq_lines.get(lid)
        if ln is None:
            continue
        q = f"{ln.installed_qty:.1f} {ln.unit}" if ln.installed_qty is not None else "-"
        rows.append([lid[:34], ln.description[:34], q, ln.basis.value, _money(amt, cur)])
    L += _table(rows, ["line", "description", "installed", "basis", "cost"])
    L.append("")
    # ---------------------------------------------------------------- cost
    L.append(f"6. Cost boundaries ({est.rate_book_name}; programme {result.programme.duration_weeks:.1f} weeks)")
    rows = [[b.name, _money(b.amount, cur), f"{b.amount / g.gia_m2:,.0f}/m2" if g.gia_m2 else "-"]
            for b in est.boundaries]
    L += _table(rows, ["boundary", "amount", f"{cur} per m2 GIA"])
    L.append(f"  unresolved items: {len(est.unresolved_items)}")
    L.append(f"  carbon {result.carbon.total_kgco2e / 1000:.1f} tCO2e (A1-A3+A5, illustrative); heat loss coefficient "
             f"{result.heat_loss.heat_loss_coefficient_w_k:.0f} W/K (simplified, not SAP)")
    L.append("")
    # ---------------------------------------------------------------- simulation
    sim = result.simulation
    if sim is not None:
        L.append(f"7. Uncertainty ({sim.n_samples} samples, {sim.config.method}, seed {sim.config.seed}) - "
                 "assumed scenario uncertainty, not calibrated statistics")
        rows = []
        for m in sim.metrics:
            if "." in m.metric:
                continue
            f = (lambda v: _money(v, cur)) if m.unit == cur else (lambda v: f"{v:,.1f}")
            rows.append([m.metric, m.unit, f(m.p10), f(m.p50), f(m.p90)])
        L += _table(rows, ["metric", "unit", "P10", "P50", "P90"])
        ys = sim.samples.get("construction_incl_contingency") or []
        base = next((b.amount for b in est.boundaries if b.key == "construction_incl_contingency"), None)
        if ys and base is not None:
            pct = 100.0 * sum(1 for v in ys if v <= base) / len(ys)
            L.append(f"  the deterministic estimate {_money(base, cur)} sits at about P{pct:.0f} of the simulated "
                     "distribution (assumed ranges are skewed: ground classes, productivity, rates)")
        L.append("  next-best evidence (share of cost variance; P10-P90 width it accounts for):")
        for r in sim.information_value[:5]:
            L.append(f"   {r['rank']}. {r['group']:20s} {r['variance_share']:5.1%}  "
                     f"{_money(r['p10_p90_width_accounted'], cur):>12s}  -> {r['resolving_action']}")
        L.append("  strongest input per group (Spearman rho with construction cost; correlated groups share "
                 "their factor):")
        best: dict[str, object] = {}
        for it in sorted(sim.sensitivity, key=lambda it: -abs(it.spearman_rho)):
            best.setdefault(it.group, it)
        for it in list(best.values())[:6]:
            L.append(f"   {it.input_name[:55]:55s} {it.group:20s} rho {it.spearman_rho:+.2f}")
        if sim.conditional_on_ground:
            L.append("  cost P50 by ground class: " + "; ".join(
                f"{k} {_money(v.p50, cur)}" for k, v in sim.conditional_on_ground.items()))
        L.append("")
    # ---------------------------------------------------------------- scenarios
    if result.comparison is not None:
        L.append("8. Build scenarios (each one coherent house; never averaged)")
        rows = []
        for o in result.comparison.outcomes:
            p = (f"{_money(o.cost_p10, cur)} / {_money(o.cost_p90, cur)}" if o.cost_p10 is not None else "-")
            rows.append([o.name[:38], f"{o.external_wall_thickness_m:.3f}", f"{o.gia_m2:.1f}",
                         _money(o.construction_cost, cur), f"{o.cost_per_m2_gia:,.0f}", p,
                         f"{o.programme_weeks:.1f}", f"{o.embodied_carbon_kgco2e / 1000:.1f}",
                         f"{o.heat_loss_coefficient_w_k:.0f}"])
        L += _table(rows, ["scenario", "wall m", "GIA m2", "construction", "/m2", "P10 / P90", "weeks", "tCO2e",
                           "HLC W/K"])
        L.append("")
    # ---------------------------------------------------------------- repeat build
    if result.repeat_build:
        L.append("9. Repeat build (FICTIONAL production economics): average C(n)/n vs incremental C(n+1)-C(n)")
        for sid, by_b in result.repeat_build.items():
            for boundary in ("factory_gate", "installed"):
                rb = by_b.get(boundary)
                if rb is None:
                    continue
                if all(abs(r.total_cost) < 0.005 for r in rb.rows):
                    L.append(f"  {sid} - {boundary}: no factory components (zero at every n)")
                    continue
                by_n = {r.n: r for r in rb.rows}
                rows = [[str(n), _money(by_n[n].total_cost, cur), _money(by_n[n].average_cost, cur),
                         _money(by_n[n].incremental_cost, cur)] for n in rb.comparison_ns if n in by_n]
                L.append(f"  {sid} - {boundary}")
                L += _table(rows, ["n", "total C(n)", "average", "incremental"])
        L.append("")
    # ---------------------------------------------------------------- exports
    if manifest is not None:
        L.append(f"10. Exports ({len(manifest.files)} files)")
        for f in manifest.files:
            L.append(f"  {f.path:28s} {f.format:5s} {f.size_bytes:>10,d} B  sha256 {f.sha256[:12]}...")
        for w in manifest.warnings[:5]:
            L.append(f"  warning: {w[:150]}")
        L.append("")
    L.append("Timings (s): " + ", ".join(f"{k} {v:.2f}" for k, v in result.timings_s.items()))
    L.append(f"Run log: {len(project.run_log)} record(s) with input/output sha256, seeds and versions.")
    return "\n".join(L)


def run(out_dir: Path, *, samples: int = 500, side_view: bool = False, store_dir: Optional[Path] = None,
        formats: Iterable[str] = ("json", "glb", "csv", "ifc"), seed: Optional[int] = None):
    """Build the demo, run the pipeline and export; returns ``(project, result, manifest)``."""
    from .. import pipeline as P
    from .build_demo import build_demo_project, demo_registry

    out_dir = Path(out_dir)
    store = Path(store_dir) if store_dir is not None else out_dir / "source_images"
    registry = demo_registry()
    project = build_demo_project(store, include_side_view=side_view, registry=registry)
    if seed is not None:
        project.simulation_config = project.simulation_config.model_copy(update={"seed": int(seed)})
    result = P.run_pipeline(project, store_dir=store, simulate=samples > 0, n_samples=max(20, samples),
                            registry=registry)
    t0 = time.perf_counter()
    manifest = P.export_project(project, out_dir, boq=result.boq, estimate=result.estimate,
                                simulation=result.simulation, repeat=result.repeat_results(),
                                comparison=result.comparison, formats=tuple(formats), library=project.library,
                                rate_book=project.rate_book, run_log=project)
    result.timings_s["export"] = round(time.perf_counter() - t0, 4)
    return project, result, manifest


def main(argv: Optional[Sequence[str]] = None, *, stream: Optional[TextIO] = None) -> int:
    """CLI entry point (``hbv-demo`` / ``python -m housebuilder_vision.demo.run_demo``)."""
    ap = argparse.ArgumentParser(prog="python -m housebuilder_vision.demo.run_demo",
                                 description="Run the fictional Housebuilder.OS Vision demo end to end.")
    ap.add_argument("--out", default="exports/demo", help="export directory (default: exports/demo)")
    ap.add_argument("--samples", type=int, default=500,
                    help="uncertainty samples (default 500; 0 skips the simulations)")
    ap.add_argument("--side-view", action="store_true", help="also use the left elevation (multi-view depth)")
    ap.add_argument("--store", default=None, help="where original images are preserved (default: <out>/source_images)")
    ap.add_argument("--seed", type=int, default=None, help="simulation seed (default: SimulationConfig default)")
    ap.add_argument("--formats", default="json,glb,csv,ifc", help="comma-separated export formats")
    args = ap.parse_args(list(argv) if argv is not None else None)
    stream = stream or sys.stdout
    if args.samples < 0:
        ap.error("--samples must be >= 0")
    formats = tuple(f.strip() for f in args.formats.split(",") if f.strip())
    t0 = time.perf_counter()
    project, result, manifest = run(Path(args.out), samples=args.samples, side_view=args.side_view,
                                    store_dir=Path(args.store) if args.store else None, formats=formats,
                                    seed=args.seed)
    print(format_report(project, result, manifest), file=stream)
    print(f"Total {time.perf_counter() - t0:.1f} s. Exports in {Path(args.out).resolve()}", file=stream)
    if any(ln.status == QuantityStatus.UNRESOLVED for ln in result.boq.lines) or result.estimate.unresolved_items:
        print("Note: some items are unresolved (listed in the exports, never priced as zero).", file=stream)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
