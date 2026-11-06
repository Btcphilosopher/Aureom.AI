"""One FloorplanLab run: validate -> synth (shared) -> floorplan -> PDN -> place
-> pre-route timing -> preliminary global route -> export, with quality gates.

Every number recorded in run.json is read from a tool output (Yosys stat,
OpenROAD/OpenDB JSON written by scripts/analysis/*.tcl, OpenSTA reports, ORFS
logs).  A stage that is skipped or fails leaves its gates NOT_RUN / FAIL; it
is never reported as passed.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import shutil
import subprocess
import traceback
from pathlib import Path

from . import geometry as G
from . import metrics as M
from . import pins as P
from . import validate as V
from .config import PROJECT, ConfigError, RunSpec, load_design, load_platform, load_run
from .lef import load_lefs
from .orfs import (FLOORPLAN_STEPS, PDN_STEPS, PLACE_STEPS, RESULTS, OrfsContext, git_revision,
                   import_synthesis, sha256_file, synth_context, tool_versions)

SCRIPTS_SRC = PROJECT / "scripts"
SCRIPTS = SCRIPTS_SRC          # replaced per run by a snapshot (see Run.snapshot_scripts)
GATES = {
    1: "RTL inputs valid", 2: "Synthesis succeeds", 3: "No unexpected unresolved black boxes",
    4: "Required technology inputs present", 5: "Die/core geometry valid", 6: "Macros legally placed",
    7: "I/O placement passes geometry checks", 8: "Tapcell/endcap stage completed",
    9: "PDN generation and connectivity checks pass", 10: "Placement legality checks pass",
    11: "Timing analysis completes with valid constraints", 12: "Preliminary routing/congestion analysis completes",
    13: "Results exported successfully", 14: "Experiment is reproducible",
    15: "No fabricated metrics or undeclared substitutions",
}
ORFS_VARS = ["SCRIPTS_DIR", "PLATFORM_DIR", "TECH_LEF", "SC_LEF", "ADDITIONAL_LEFS", "LIB_FILES", "RESULTS_DIR",
             "REPORTS_DIR", "LOG_DIR", "DESIGN_NAME", "PLATFORM", "MIN_ROUTING_LAYER", "MAX_ROUTING_LAYER",
             "FASTROUTE_TCL", "NUM_CORES", "PLACE_SITE", "IO_PLACER_H", "IO_PLACER_V"]


def now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


class Run:
    def __init__(self, spec: RunSpec, results_root: Path = RESULTS):
        self.spec = spec
        self.design = load_design(spec.design)
        self.platform = load_platform(spec.platform)
        self.dir = results_root / spec.id
        self.ctx = OrfsContext(self.design, self.platform, self.dir / "orfs")
        self.out = self.dir / "analysis"
        self.period = spec.clock_period_ns or self.design.clock.period_ns
        self.lef = None
        self.rec_path = self.dir / "run.json"
        self.rec = self._load_record()

    # ------------------------------------------------------------------ record
    def _load_record(self) -> dict:
        if self.rec_path.is_file():
            rec = json.loads(self.rec_path.read_text())
            if rec.get("spec") == json.loads(self.spec.model_dump_json()):
                return rec
        return self._fresh_record()

    def _fresh_record(self) -> dict:
        return {"run_id": self.spec.id, "created": now(), "spec": json.loads(self.spec.model_dump_json()),
                "design": {"name": self.design.name, "top": self.design.top, "description": self.design.description},
                "platform": {"name": self.platform.name, "status": self.platform.status,
                             "orfs_platform": self.platform.orfs_platform, "process": self.platform.process,
                             "provenance": self.platform.provenance},
                "stages": {}, "gates": {str(g): {"name": n, "status": "NOT_RUN", "findings": []} for g, n in GATES.items()},
                "metrics": {}, "status": "pending", "failure_reason": None}

    def save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.rec["updated"] = now()
        self.rec_path.write_text(json.dumps(self.rec, indent=2, default=str) + "\n")

    def gate(self, n: int, findings: list, ran: bool = True, note: str | None = None) -> bool:
        errs = [f for f in findings if f.severity == "error"]
        g = self.rec["gates"][str(n)]
        g["findings"] = [f.to_dict() for f in findings]
        g["status"] = ("FAIL" if errs else "PASS") if ran else "NOT_RUN"
        if note:
            g["note"] = note
        return not errs

    def stage(self, name: str, result) -> bool:
        self.rec["stages"][name] = {"rc": result.returncode, "seconds": result.seconds, "log": result.log,
                                    "target": result.target, "finished": now()}
        self.save()
        return result.returncode == 0

    def fail(self, reason: str) -> None:
        self.rec["status"] = "failed"
        self.rec["failure_reason"] = reason
        self.save()

    # ------------------------------------------------------------------ helpers
    def _lef(self):
        if self.lef is None:
            mac = [m.lef for m in self.platform.macros.values()]
            self.lef = load_lefs([self.platform.tech_lef, *self.platform.sc_lefs, *mac])
        return self.lef

    def _analysis_env(self, extra: dict) -> dict[str, str]:
        env = self.ctx.orfs_env(ORFS_VARS)
        groups = " ".join(f"{g.name} {{{' '.join(g.match)}}}" for g in self.design.logical_groups)
        env.update({"FLP_GROUPS": groups, "FLP_OUT": str(self.out), "FLP_SCRIPTS": str(SCRIPTS),
                    "FLP_CORNER": self.platform.analysis_corner})
        env.update({k: str(v) for k, v in extra.items()})
        return env

    def _stage_metrics(self, stage: str, odb: str, sdc: str, timing=False, check_place=False, power=False) -> dict | None:
        env = self._analysis_env({"FLP_STAGE": stage, "FLP_ODB": odb, "FLP_SDC": sdc,
                                  "FLP_TIMING": int(timing), "FLP_CHECK_PLACEMENT": int(check_place),
                                  "FLP_POWER": int(power)})
        r = self.ctx.openroad(SCRIPTS / "analysis" / "stage_metrics.tcl", f"flp_{stage}_metrics", env)
        self.stage(f"metrics_{stage}", r)
        f = self.out / f"{stage}_metrics.json"
        if r.returncode != 0 or not f.is_file():
            return None
        return json.loads(f.read_text())

    # ------------------------------------------------------------------ stages
    def snapshot_scripts(self) -> None:
        """Run from a frozen copy of scripts/ + the platform PDN Tcl: OpenSTA's `source`
        reads scripts incrementally, so editing a script during a run corrupts it
        (observed once: A_baseline route stage).  The snapshot hash is recorded."""
        global SCRIPTS
        snap = self.dir / "scripts_snapshot"
        if snap.exists():
            shutil.rmtree(snap)
        shutil.copytree(SCRIPTS_SRC, snap)
        pdn = Path(self.platform.pdn["tcl"])
        shutil.copy2(pdn, snap / f"pdn_{self.platform.name}.tcl")
        h = hashlib.sha256()
        for f in sorted(snap.rglob("*.tcl")):
            h.update(f.read_bytes())
        self.rec["scripts_sha256"] = h.hexdigest()
        SCRIPTS = snap
        self.platform.pdn["tcl"] = str(snap / f"pdn_{self.platform.name}.tcl")

    def check(self) -> bool:
        self.snapshot_scripts()
        if self.spec.macros.mode != "physical":
            # logic_only / mock are declared in the schema so configs cannot slip them in
            # unnoticed; they are not implemented in this release (both enabled platforms
            # have physical SRAM macros) and are refused rather than approximated.
            self.gate(15, [V.Finding(15, "error", "MODE_NOT_IMPLEMENTED",
                                     f"macro mode '{self.spec.macros.mode}' is not implemented; only 'physical' runs")])
            self.fail(f"macro mode '{self.spec.macros.mode}' refused (not implemented; never production-eligible)")
            return False
        fs = V.check_design(self.design, self.platform)
        ok1 = self.gate(1, [f for f in fs if f.gate == 1])
        pf_find, lef = V.check_platform(self.platform, list(self.design.expected_macros.get(self.platform.name, {})))
        self.lef = lef
        ok4 = self.gate(4, pf_find)
        rf = V.check_run(self.spec, self.platform, lef)
        for f in rf:
            self.rec["gates"][str(f.gate)].setdefault("prechecks", []).append(f.to_dict())
        vend = subprocess.run(["python3", str(PROJECT / "tools" / "import_sources.py"), "--check"],
                              capture_output=True, text=True)
        self.rec["vendored_sources_check"] = vend.stdout.strip()
        self.rec["tools"] = tool_versions()
        self.rec["git_revision"] = git_revision()
        self.save()
        # run pre-check errors block only the stages they concern (all recorded)
        needs = {5: "floorplan", 6: "floorplan", 7: "floorplan", 9: "pdn", 10: "place", 11: "place", 15: "check"}
        req = set(getattr(self, "requested", ["check", "synth", "floorplan", "pdn", "place"]))
        pre_errs = [f for f in rf if f.severity == "error" and needs.get(f.gate, "check") in req]
        if [f for f in rf if f.severity == "error"] and not pre_errs:
            self.rec["deferred_precheck_errors"] = [f.to_dict() for f in rf if f.severity == "error"]
        if not (ok1 and ok4) or pre_errs or vend.returncode != 0:
            reasons = [f.message for f in V.errors(fs + pf_find + rf)]
            if vend.returncode != 0:
                reasons.append("vendored RTL differs from repository archives")
            self.fail("input validation failed: " + "; ".join(reasons[:6]))
            return False
        return True

    def synth(self) -> bool:
        sctx = synth_context(self.design, self.platform, self.period)
        stat = sctx.reports_dir / "synth_stat.txt"
        if not (sctx.results_dir / "1_synth.v").is_file():
            sctx.inputs_dir.mkdir(parents=True, exist_ok=True)
            sctx.write_config(sctx.base_vars(self.period))
            r = sctx.make(["synth"], "1_synth")
            self.rec["stages"]["synth"] = {"rc": r.returncode, "seconds": r.seconds, "log": r.log, "shared": True}
            if r.returncode != 0:
                self.gate(2, [V.Finding(2, "error", "SYNTH_FAILED", f"ORFS synth failed (rc {r.returncode}), see {r.log}")])
                self.fail("synthesis failed")
                return False
        else:
            self.rec["stages"]["synth"] = {"rc": 0, "shared": True, "reused": str(sctx.work_home)}
        syn = M.synthesis_summary(sctx, self.design, self.platform)
        self.rec["synthesis"] = syn
        self.rec["metrics"]["std_cell_area_synth_um2"] = syn["std_cell_area_um2"]
        self.rec["metrics"]["macro_inventory"] = syn["macros"]
        f2 = M.synth_findings_gate2(syn)
        f3 = M.synth_findings_gate3(syn, self.design, self.platform)
        ok = self.gate(2, f2) & self.gate(3, f3)
        hashes = import_synthesis(self.ctx, sctx)
        self.rec["netlist_sha256"] = hashes["1_synth.v"]
        self.rec["synth_key"] = sctx.work_home.name
        self.save()
        if not ok:
            self.fail("synthesis gates failed")
        return ok

    def _macro_insts(self) -> list[G.MacroInst]:
        insts = [(m["name"], m["master"]) for m in self.rec["synthesis"]["macro_instances"]]
        return G.classify_macros(insts, self._lef().macros, self.design.macro_groups)

    def prepare_floorplan(self) -> bool:
        pf, sp = self.platform, self.spec
        lef = self._lef()
        macros = self._macro_insts()
        halo, channel = sp.macros.halo_um, sp.macros.channel_um
        site_w, row_h = pf.site_width_um, pf.row_height_um
        mgrid = lef.manufacturing_grid or 0.005
        arrangement = None
        params = {**pf.pdn.get("params", {}), **sp.pdn.params}
        side_gap = V.vertical_strap_window(params, lef) + 2 * site_w
        if sp.macros.placement == "manual" and sp.macros.arrangement:
            probe = G.arrange(sp.macros.arrangement, G.Box(0, 0, 1e5, 1e5), macros, halo, channel,
                              pf.macro_allowed_orients, macros[0].pin_side_r0 if macros else "bottom", side_gap)
            envelope = (probe.envelope_w, probe.envelope_h)
        else:
            envelope = None
        std_area = self.rec["metrics"]["std_cell_area_synth_um2"]
        if sp.floorplan.mode == "B":
            geom = G.size_mode_b(sp.floorplan, std_area, macros, halo, site_w, row_h, mgrid, envelope)
        else:
            geom = G.mode_a(sp.floorplan, std_area, macros, halo)
        ring_extent = (params.get("ring_offset", 0) + 2 * params.get("ring_width", 0) + params.get("ring_spacing", 0)) if params.get("ring") else 0
        gf = V.check_geometry(geom, pf, lef, ring_extent)
        self.rec["geometry"] = geom.to_dict()
        placements: list[G.Placement] = []
        if sp.macros.placement == "manual":
            if sp.macros.arrangement:
                arrangement = G.arrange(sp.macros.arrangement, geom.core, macros, halo, channel,
                                        pf.macro_allowed_orients, macros[0].pin_side_r0 if macros else "bottom", side_gap)
                placements = G.snap_placements(arrangement.placements, geom.core, site_w, row_h, mgrid)
                self.rec["arrangement"] = {"name": arrangement.name, "description": arrangement.description}
            else:
                placements = [G.Placement(i, next(m.master for m in macros if m.name == i), float(v[0]), float(v[1]), v[2],
                                          *(lambda mm: (mm.width, mm.height))(next(m for m in macros if m.name == i)))
                              for i, v in sp.macros.positions.items()]
            mf = V.check_macro_placement(placements, geom.core, macros, halo, channel, pf.macro_allowed_orients, lef,
                                         self.design.expected_macros.get(pf.name))
            mf += V.check_macro_channels_pdn(placements, params, lef)
            self.rec["planned_macro_placement"] = [p.__dict__ for p in placements]
            self.rec["gates"]["6"]["prechecks"] = [f.to_dict() for f in mf]
            gf += mf
        self.gate(5, gf)
        # I/O plan
        ports = P.top_ports(self.ctx.results_dir / "1_synth.v", self.design.top)
        pitch = {}
        if pf.routing:
            ih, iv = lef.layers.get(pf.routing.io_h_layer), lef.layers.get(pf.routing.io_v_layer)
            pitch = {"left": ih.pitch if ih else 0.5, "right": ih.pitch if ih else 0.5,
                     "top": iv.pitch if iv else 0.5, "bottom": iv.pitch if iv else 0.5}
        pinf = V.check_pin_plan(P.pin_groups(self.design, sp.pins), ports, geom.die, pitch,
                                sp.pins.min_distance_tracks, sp.pins.corner_avoidance_um) if sp.pins.mode == "plan" else []
        self.rec["gates"]["7"]["prechecks"] = [f.to_dict() for f in pinf]
        self.rec["io_ports"] = len(ports)
        errs = V.errors(gf + pinf)
        if errs:
            self.fail("floorplan pre-checks failed: " + "; ".join(e.message for e in errs[:5]))
            return False
        # ORFS config
        inp = self.ctx.inputs_dir
        inp.mkdir(parents=True, exist_ok=True)
        v = self.ctx.base_vars(self.period)
        v["DIE_AREA"] = " ".join(f"{x:.3f}" for x in geom.die.as_list())
        v["CORE_AREA"] = " ".join(f"{x:.3f}" for x in geom.core.as_list())
        v["MACRO_PLACE_HALO"] = f"{halo:g} {halo:g}"
        v["MACRO_PLACE_CHANNEL"] = f"{channel:g} {channel:g}"
        if sp.macros.placement == "manual":
            mp = inp / "macro_placement.tcl"
            mp.write_text(P.macro_placement_tcl(placements, SCRIPTS / "orfs_hooks" / "macro_placement_lib.tcl"))
            v["MACRO_PLACEMENT_TCL"] = str(mp)
        io = inp / "io_constraints.tcl"
        io.write_text(P.io_constraints_tcl(self.design, sp.pins, ports, geom.die))
        v["IO_CONSTRAINTS"] = str(io)
        v["PLACE_PINS_ARGS"] = P.place_pins_args(sp.pins)
        v["PDN_TCL"] = pf.pdn["tcl"]
        v["POST_PDN_TCL"] = str(SCRIPTS / "orfs_hooks" / "post_pdn.tcl")
        for k, val in params.items():
            v[f"FLP_PDN_{k.upper()}"] = " ".join(map(str, val)) if isinstance(val, list) else str(val)
        v["FLP_MACRO_PG"] = " ".join(f"{p} {n}" for p, n in pf.macro_pg_pins.items())
        v["FLP_SCRIPTS"] = str(SCRIPTS)
        v["FLP_OUT"] = str(self.out)
        if sp.place.density is not None:
            v["PLACE_DENSITY"] = f"{sp.place.density:g}"
        else:
            v["PLACE_DENSITY_LB_ADDON"] = f"{sp.place.density_lb_addon:g}"
        v["GPL_TIMING_DRIVEN"] = str(int(sp.place.timing_driven))
        v["GPL_ROUTABILITY_DRIVEN"] = str(int(sp.place.routability_driven))
        v["CELL_PAD_IN_SITES_GLOBAL_PLACEMENT"] = str(sp.place.pad_global)
        v["CELL_PAD_IN_SITES_DETAIL_PLACEMENT"] = str(sp.place.pad_detail)
        self.ctx.write_config(v)
        self.rec["config_mk_sha256"] = sha256_file(self.ctx.config_mk)
        self.save()
        return True

    def floorplan(self) -> bool:
        if not self.prepare_floorplan():
            return False
        if not self.stage("floorplan", self.ctx.make(FLOORPLAN_STEPS, "2_floorplan")):
            self.gate(5, [V.Finding(5, "error", "FLOORPLAN_FAILED", "ORFS floorplan stage failed; see log")])
            self.fail("ORFS floorplan stage failed")
            return False
        fm = self._stage_metrics("floorplan", "2_5_floorplan_tapcell.odb", "1_synth.sdc")
        if fm is None:
            self.fail("floorplan metrics extraction failed")
            return False
        self.rec["metrics"]["floorplan"] = M.compact_stage(fm)
        f6 = M.macro_findings(fm, self, self._lef())
        self.gate(6, f6)
        f8 = M.tapcell_findings(fm, self.platform, self.ctx)
        self.gate(8, f8, note=self.platform.tapcell.note if self.platform.tapcell else None)
        self.save()
        return not V.errors(f6) and not V.errors(f8)

    def pdn(self) -> bool:
        ok = self.stage("pdn", self.ctx.make(PDN_STEPS, "2_6_pdn"))
        if not ok:
            self.gate(9, [V.Finding(9, "error", "PDNGEN_FAILED", "ORFS PDN stage (pdngen) failed; see log")])
            self.fail("PDN generation failed")
            return False
        f9 = M.pdn_findings(self.out / "pdn_checks.json")
        plog = self.ctx.logs_dir / "2_6_floorplan_pdn.log"
        if plog.is_file():
            import re as _re
            from collections import Counter as _C
            w = _C(_re.findall(r"\[WARNING (PDN-\d+)\]", plog.read_text(errors="replace")))
            if w:
                f9.append(V.Finding(9, "warning", "PDN_WARNINGS", "pdngen warnings: " + ", ".join(f"{k} x{n}" for k, n in sorted(w.items()))
                                    + " (PDN-0110 = no via where parallel/non-overlapping shapes meet)"))
        pm = self._stage_metrics("pdn", "2_floorplan.odb", "1_synth.sdc")
        if pm:
            self.rec["metrics"]["pdn"] = {"nets": pm["pdn_nets"]}
        self.gate(9, f9)
        self.save()
        return not V.errors(f9)

    def place(self) -> bool:
        r = self.ctx.make(PLACE_STEPS, "3_place")
        if r.returncode != 0 and "GPL-0307" in Path(r.log).read_text(errors="replace"):
            # RePlAce divergence: retry ONCE as the tool instructs ("Re-run with a
            # smaller max_phi_cof value"); the failed attempt stays in the record.
            self.rec.setdefault("retries", []).append({"stage": "place", "reason": "GPL-0307 RePlAce divergence",
                                                       "log": r.log, "action": "GLOBAL_PLACEMENT_ARGS=-max_phi_coef 1.02"})
            shutil.copy2(r.log, Path(r.log).with_suffix(".attempt1.log"))
            with open(self.ctx.config_mk, "a") as fh:
                fh.write("export GLOBAL_PLACEMENT_ARGS = -max_phi_coef 1.02\n")
            self.rec["config_mk_sha256"] = sha256_file(self.ctx.config_mk)
            r = self.ctx.make(PLACE_STEPS, "3_place")
        if not self.stage("place", r):
            self.gate(10, [V.Finding(10, "error", "PLACE_FAILED", "ORFS placement failed; see log")])
            self.fail("ORFS placement failed")
            return False
        pm = self._stage_metrics("place", "3_place.odb", "3_place.sdc", timing=True, check_place=True, power=True)
        if pm is None:
            self.fail("placement metrics extraction failed")
            return False
        self.rec["metrics"]["place"] = M.compact_stage(pm)
        self.gate(10, M.placement_findings(pm))
        self.gate(7, M.pin_findings(pm, self))
        self.gate(11, M.timing_findings(pm, self.design, self.out / "place_timing_setup.rpt"))
        self.rec["metrics"]["timing_preroute"] = M.timing_summary(pm, self.out, "place", self.design.clock.name)
        self.rec["metrics"]["power_vectorless"] = M.power_summary(self.out / "place_power.rpt", self.platform)
        self.rec["metrics"]["logs"] = M.orfs_log_metrics(self.ctx)
        self.save()
        return True

    def timing(self) -> bool:
        """Re-run pre-route STA on the existing 3_place.odb (no placement re-run)."""
        if not (self.ctx.results_dir / "3_place.odb").is_file():
            self.gate(11, [V.Finding(11, "error", "NO_PLACEMENT", "3_place.odb missing: run the place stage first")])
            return False
        pm = self._stage_metrics("place", "3_place.odb", "3_place.sdc", timing=True, check_place=True, power=True)
        if pm is None:
            self.gate(11, [V.Finding(11, "error", "STA_FAILED", "STA script failed")])
            return False
        self.gate(11, M.timing_findings(pm, self.design, self.out / "place_timing_setup.rpt"))
        self.rec["metrics"]["timing_preroute"] = M.timing_summary(pm, self.out, "place", self.design.clock.name)
        self.save()
        return True

    def route_estimate(self) -> bool:
        if not self.spec.route_estimate.enabled:
            self.gate(12, [], ran=False, note="route estimate not requested")
            return True
        env = self._analysis_env({"FLP_GRT_ITERS": self.spec.route_estimate.congestion_iterations})
        r = self.ctx.openroad(SCRIPTS / "analysis" / "route_estimate.tcl", "flp_route_estimate", env)
        self.stage("route_estimate", r)
        rm = M.route_summary(self.out, Path(r.log))
        self.rec["metrics"]["route"] = rm
        self.gate(12, M.route_findings(rm, r.returncode))
        self.save()
        return r.returncode == 0

    def export(self) -> bool:
        from .export import export_run
        fs = export_run(self)
        self.gate(13, fs)
        self.save()
        return not V.errors(fs)

    def finalize(self) -> None:
        self.gate(14, M.repro_findings(self))
        self.gate(15, M.integrity_findings(self))
        failed = [g for g, v in self.rec["gates"].items() if v["status"] == "FAIL"]
        if self.rec.get("status") != "failed":
            self.rec["status"] = "completed" if not failed else "completed_with_gate_failures"
            self.rec["failure_reason"] = None
        self.rec["failed_gates"] = failed
        self.rec["physically_valid"] = (not failed) and self.spec.macros.mode == "physical" and \
            all(self.rec["gates"][str(g)]["status"] == "PASS" for g in (2, 3, 4, 5, 6, 7, 8, 9, 10, 11))
        self.rec["readiness"] = "PRELIMINARY FLOORPLAN ONLY -- not fabrication-ready (no CTS, detailed routing, " \
                                "extraction, signoff STA, DRC/LVS, IR/EM signoff, DFT, package)."
        self.save()

    def run(self, stages: list[str]) -> dict:
        order = ["check", "synth", "floorplan", "pdn", "place", "timing", "route", "export"]
        self.requested = list(stages)
        if "check" in stages and self.rec_path.is_file():
            # a run that starts from 'check' is a fresh attempt: archive the old record
            prev = json.loads(self.rec_path.read_text())
            hist = self.dir / "previous_attempts"
            hist.mkdir(parents=True, exist_ok=True)
            n = len(list(hist.glob("run.*.json"))) + 1
            (hist / f"run.{n}.json").write_text(json.dumps(prev, indent=2, default=str) + "\n")
            self.rec = self._fresh_record()
            self.rec["previous_attempts"] = n
        self.rec["status"] = "running"
        if "check" not in stages:
            snap = self.dir / "scripts_snapshot"
            if snap.exists():
                global SCRIPTS
                SCRIPTS = snap
                self.platform.pdn["tcl"] = str(snap / f"pdn_{self.platform.name}.tcl")
            else:
                self.snapshot_scripts()
        self.save()
        try:
            for st in order:
                if st not in stages:
                    continue
                ok = {"check": self.check, "synth": self.synth, "floorplan": self.floorplan, "pdn": self.pdn,
                      "place": self.place, "timing": self.timing, "route": self.route_estimate,
                      "export": self.export}[st]()
                if not ok and st in ("check", "synth", "floorplan", "pdn", "place"):
                    break
        except ConfigError as e:
            self.fail(f"configuration error: {e}")
        except Exception as e:  # recorded, never swallowed silently
            self.rec["traceback"] = traceback.format_exc()
            self.fail(f"internal error: {e}")
        self.finalize()
        return self.rec


def run_file(path: str | Path, stages: list[str], overrides: dict | None = None) -> dict:
    spec = load_run(path, overrides)
    return Run(spec).run(stages)
