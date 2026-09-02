import json

import pytest

from silicaflux_pv_spectral.main import main


@pytest.mark.parametrize("mode", ["baseline", "optimise", "sweep", "report"])
def test_cli_runs_every_mode_without_error(capsys, mode):
    exit_code = main(["--material", "SILICON", "--mode", mode, "--max-sweep-configs", "40"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "SilicaFlux" in captured.out


def test_cli_tandem_architecture(capsys):
    exit_code = main(["--material", "SILICON", "--mode", "optimise", "--architecture", "tandem"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "tandem" in captured.out


def test_cli_writes_json_output(tmp_path):
    out_path = tmp_path / "result.json"
    exit_code = main(["--material", "SILICON", "--mode", "baseline", "--json-out", str(out_path)])
    assert exit_code == 0
    assert out_path.exists()
    with open(out_path) as f:
        payload = json.load(f)
    assert "efficiency" in payload


def test_cli_accepts_every_material():
    from silicaflux_pv_spectral.materials import MATERIAL_LIBRARY

    for name in MATERIAL_LIBRARY:
        assert main(["--material", name, "--mode", "baseline"]) == 0
