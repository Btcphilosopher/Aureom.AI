"""Tool integration tests.

* ORFS public reference design `gcd` on ihp-sg13g2 (REFERENCE DESIGN -- passing
  it says nothing about SilicaFlux).
* OpenROAD command failure propagation.
* SilicaFlux-V: recorded runs are checked for gate consistency (the full
  SilicaFlux flow is the experiment set, not a unit test).
"""
import json
import subprocess

import pytest

from conftest import requires_tools
from floorplanlab.config import PROJECT, load_design, load_platform, tool_env
from floorplanlab.orfs import OrfsContext


@requires_tools
def test_openroad_command_failure_is_reported(tmp_path):
    ctx = OrfsContext(load_design("silicaflux_v"), load_platform("ihp_sg13g2"), tmp_path)
    bad = tmp_path / "bad.tcl"
    bad.write_text("this_is_not_a_command\n")
    r = ctx.openroad(bad, "bad", {})
    assert r.returncode != 0
    assert "this_is_not_a_command" in open(r.log).read()


@requires_tools
def test_orfs_unknown_target_fails(tmp_path):
    ctx = OrfsContext(load_design("silicaflux_v"), load_platform("ihp_sg13g2"), tmp_path)
    ctx.inputs_dir.mkdir(parents=True)
    ctx.write_config({"DESIGN_NAME": "x", "PLATFORM": "ihp-sg13g2"})
    assert ctx.make(["no-such-target"], "bad").returncode != 0


@requires_tools
@pytest.mark.slow
def test_orfs_reference_gcd_ihp(tmp_path):
    """REFERENCE DESIGN: ORFS flow/designs/ihp-sg13g2/gcd through synth/floorplan/place."""
    env = tool_env()
    flow = env["ORFS_FLOW"]
    cmd = ["make", "-C", flow, f"DESIGN_CONFIG={flow}/designs/ihp-sg13g2/gcd/config.mk", f"WORK_HOME={tmp_path}",
           f"OPENROAD_EXE={env['OPENROAD_EXE']}", f"YOSYS_CMD={env['YOSYS_EXE']}", "place"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    log = r.stdout[-3000:] + r.stderr[-3000:]
    assert r.returncode == 0, log
    res = tmp_path / "results/ihp-sg13g2/gcd/base"
    assert (res / "3_place.odb").is_file()
    dp = (tmp_path / "logs/ihp-sg13g2/gcd/base/3_5_place_dp.log").read_text()
    assert "Placement violations 0" in dp or "FLW-0012" in dp


def test_silicaflux_recorded_runs_consistent():
    runs = [p for p in sorted((PROJECT / "results").glob("*/run.json")) if not p.parent.name.startswith(("_", "synth"))]
    runs += sorted((PROJECT / "reports/runs").glob("*/run.json"))
    if not runs:
        pytest.skip("no recorded SilicaFlux runs")
    for p in runs:
        r = json.loads(p.read_text())
        assert r["design"]["top"] == "sfv_soc_df"
        failed = [g for g, v in r["gates"].items() if v["status"] == "FAIL"]
        if r.get("physically_valid"):
            assert not failed, p
            assert r["gates"]["9"]["status"] == "PASS" and r["gates"]["10"]["status"] == "PASS"
        # a run that failed a stage must carry a reason
        if r["status"] == "failed":
            assert r.get("failure_reason")
