"""Results export: OpenDB geometry/connectivity/DEF (OpenROAD), floorplan images,
TwinLab exchange JSON.  Checked by GATE 13."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from .validate import Finding


def export_run(run) -> list[Finding]:
    from . import twinlab
    from .visualise import render_run
    out: list[Finding] = []
    exp = run.dir / "export"
    exp.mkdir(parents=True, exist_ok=True)
    rd = run.ctx.results_dir
    odb = next((o for o in ("3_place.odb", "2_floorplan.odb", "2_5_floorplan_tapcell.odb") if (rd / o).is_file()), None)
    if odb is None:
        return [Finding(13, "error", "NO_ODB", "no OpenDB database to export")]
    sdc = "3_place.sdc" if odb.startswith("3_") else "1_synth.sdc"
    env = run._analysis_env({"FLP_ODB": odb, "FLP_SDC": sdc, "FLP_OUT": str(exp),
                             "FLP_CLOCK_PORT": run.design.clock.port})
    from . import pipeline
    r = run.ctx.openroad(pipeline.SCRIPTS / "analysis" / "export_geometry.tcl", "flp_export_geometry", env)
    run.stage("export_geometry", r)
    if r.returncode != 0:
        return [Finding(13, "error", "EXPORT_FAILED", f"export_geometry.tcl failed (rc {r.returncode}); see {r.log}")]
    files = {"geometry.json": exp / "geometry.json", "connectivity.json": exp / "connectivity.json",
             "cells.csv.gz": exp / "cells.csv.gz", "def": exp / f"{Path(odb).stem}.def.gz"}
    for k, p in files.items():
        if not p.is_file() or p.stat().st_size == 0:
            out.append(Finding(13, "error", "MISSING_EXPORT", f"{k} not written"))
    if [f for f in out if f.severity == "error"]:
        return out
    geo = json.loads(files["geometry.json"].read_text())
    labels = {g.name: g.name for g in run.design.logical_groups}
    try:
        imgs = render_run(run.dir, labels)
        out.append(Finding(13, "info", "IMAGES", f"rendered {', '.join(p.name for p in imgs)}"))
    except Exception as e:  # recorded
        out.append(Finding(13, "error", "RENDER_FAILED", f"floorplan rendering failed: {e}"))
    # OpenROAD-rendered views of the same database (labelled by view in the file name)
    ri = run.ctx.openroad(pipeline.SCRIPTS / "analysis" / "or_images.tcl", "flp_or_images",
                          {"FLP_ODB": str(rd / odb), "FLP_OUT": str(exp)}, timeout=900, gui=True)
    run.stage("or_images", ri)
    shots = [p.name for p in exp.glob("or_*.png")]
    out.append(Finding(13, "info" if shots else "warning", "OR_IMAGES",
                       f"OpenROAD-rendered images: {', '.join(sorted(shots)) or 'none (see log)'}"))
    try:
        ex = twinlab.build_export(run, geo, run._lef())
        tl = exp / "twinlab_floorplan.json"
        tl.write_text(ex.model_dump_json(indent=1))
        twinlab.load_export(tl)                       # round-trip validation against the schema
        out.append(Finding(13, "info", "TWINLAB_EXPORT", f"{tl.name} written and validated (schema {twinlab.SCHEMA_VERSION})"))
    except Exception as e:
        out.append(Finding(13, "error", "TWINLAB_EXPORT", f"TwinLab export failed: {e}"))
    # reference to the ODB for the OpenROAD GUI (not copied: large, in results/)
    run.rec["exports"] = {"odb": str(rd / odb), "def": str(files["def"]), "geometry": str(files["geometry.json"]),
                          "connectivity": str(files["connectivity.json"]), "cells": str(files["cells.csv.gz"]),
                          "twinlab": str(exp / "twinlab_floorplan.json"),
                          "images": [str(p) for p in exp.glob("floorplan.*")]}
    try:
        hs = __import__("floorplanlab.metrics", fromlist=["x"]).congestion_hotspots(run.out / "grt_congestion.rpt", geo)
        if hs is not None:
            run.rec["metrics"].setdefault("route", {})["hotspots"] = hs
    except Exception as e:
        out.append(Finding(13, "warning", "HOTSPOTS", f"congestion hotspot analysis failed: {e}"))
    from .connectivity import analyse
    try:
        run.rec["metrics"]["connectivity"] = analyse(exp / "connectivity.json", geo)
    except Exception as e:
        out.append(Finding(13, "warning", "CONNECTIVITY", f"connectivity analysis failed: {e}"))
    return out
