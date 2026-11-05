"""End-to-end report generation (uses whatever RTL/synth results exist)."""
from memoryflow.report.build import generate
from memoryflow.cli import main


def test_report_generates_all_artifacts(tmp_path):
    s = generate(tmp_path, verbose=False)
    for f in ("report.html", "REPORT.md", "inventory.md", "summary.json", "design_space_grid.csv",
              "sweeps_one_at_a_time.csv", "figures/roofline.png", "figures/banking_maps.svg",
              "figures/architecture_recommended.svg", "figures/pareto.png", "figures/sram_area.png",
              "memoryflow_inventory.md", "figures/baselines_per_workload.png", "figures/node_external_memory.png",
              "figures/balance_recommended.png"):
        assert (tmp_path / f).exists(), f
    assert s["recommendation"]["Recommended"]["feasible"]
    html = (tmp_path / "report.html").read_text()
    assert "Repository evidence" in html and "PROPOSED" in html
    assert "MEASURED" in html
    assert "Documented SilicaFlux-V targets" in html and "Compute / bandwidth balance" in html
    from memoryflow.silicaflux.sources import silicaflux_root
    if silicaflux_root() is not None:
        assert "SilicaFlux repository inventory" in html and "REFERENCED_ONLY" in html
        assert "origin" in (tmp_path / "inventory.md").read_text() or "`" in (tmp_path / "inventory.md").read_text()
        assert s["silicaflux_inventory"]["available"]

def test_cli_roofline_and_explore(capsys):
    assert main(["roofline", "--config", "reference"]) == 0
    assert "DMA path" in capsys.readouterr().out
    assert main(["explore", "--top", "3"]) == 0
    assert "recommended" in capsys.readouterr().out
    assert main(["explore", "--top", "2", "--budget", "v1-assumed-40"]) == 0
    assert main(["baselines"]) == 0
    assert "MemoryFlow recommended" in capsys.readouterr().out
