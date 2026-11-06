"""Configuration parsing and technology-input validation (GATE 1/4)."""
import pytest

from floorplanlab.config import (PROJECT, ConfigError, FloorplanSpec, PlaceSpec, RunSpec, load_design, load_platform,
                                 load_run)
from floorplanlab.lef import parse_lef, parse_lef_text
from floorplanlab.validate import check_design, check_lef_facts, check_platform, check_sdc_text, errors


def codes(fs):
    return {f.code for f in fs if f.severity == "error"}


# ---------------------------------------------------------------- parsing
def test_experiment_configs_parse_and_extend():
    for p in sorted((PROJECT / "configs/silicaflux_v/experiments").glob("*.yaml")):
        spec = load_run(p)
        assert isinstance(spec, RunSpec)
        assert spec.design == "silicaflux_v"
        assert spec.platform == ("sky130hd" if spec.id.startswith("S_") else "ihp_sg13g2")
    e = load_run(PROJECT / "configs/silicaflux_v/experiments/E_pdn_corridors.yaml")
    assert e.macros.halo_um == 30.0 and e.pdn.params["strap1_pitch"] == 50.4
    b = load_run(PROJECT / "configs/silicaflux_v/experiments/B_core_area_plus.yaml")
    assert b.floorplan.target_util == 0.35 and b.floorplan.aspect_ratio == 1.0     # inherited


def test_unknown_key_rejected(tmp_path):
    p = tmp_path / "x.yaml"
    p.write_text("id: x\ndesign: silicaflux_v\nplatform: ihp_sg13g2\nfloorplan: {mode: B, target_util: 0.5, "
                 "aspect_ratio: 1, core_margin_um: 10, bogus: 1}\n")
    with pytest.raises(ConfigError):
        load_run(p)


def test_design_config_and_mcu_i_unavailable():
    d = load_design("silicaflux_v")
    assert d.top == "sfv_soc_df" and "SFV_SRAM_MACRO" in d.rtl.defines
    with pytest.raises(ConfigError, match="not available"):
        load_design("mcu_i")


# ---------------------------------------------------------------- utilisation / sizing conflicts
def test_conflicting_sizing_modes():
    with pytest.raises(ValueError, match="conflicts"):
        FloorplanSpec(mode="A", die_area=[0, 0, 100, 100], core_area=[10, 10, 90, 90], target_util=0.5)
    with pytest.raises(ValueError, match="conflicts"):
        FloorplanSpec(mode="B", target_util=0.5, aspect_ratio=1, core_margin_um=10, die_area=[0, 0, 1, 1])
    with pytest.raises(ValueError):
        FloorplanSpec(mode="B", target_util=1.2, aspect_ratio=1, core_margin_um=10)


def test_conflicting_placement_density():
    with pytest.raises(ValueError, match="exactly one"):
        PlaceSpec(density=0.6, density_lb_addon=0.2)


def test_incorrect_die_dimensions():
    with pytest.raises(ValueError, match="ur > ll"):
        FloorplanSpec(mode="A", die_area=[0, 0, -5, 100], core_area=[10, 10, 90, 90])


# ---------------------------------------------------------------- technology inputs
def test_missing_lef_and_liberty(tmp_path):
    pf = load_platform("ihp_sg13g2")
    pf = pf.model_copy(update={"tech_lef": str(tmp_path / "missing.lef")})
    fs, lef = check_platform(pf)
    assert "FILE_NOT_FOUND" in codes(fs) and lef is None
    pf2 = load_platform("ihp_sg13g2")
    c = pf2.corners["typ"].model_copy(update={"liberty": [str(tmp_path / "missing.lib")]})
    pf2 = pf2.model_copy(update={"corners": {"typ": c}})
    fs2, _ = check_platform(pf2)
    assert any("Liberty" in f.message and f.code == "FILE_NOT_FOUND" for f in fs2)


def test_commercial_templates_and_disabled_platforms_rejected():
    for name in ("commercial_130", "commercial_65", "commercial_28", "gf180mcu"):
        fs, lef = check_platform(load_platform(name))
        assert "PLATFORM_NOT_ENABLED" in codes(fs), name
        assert lef is None


def test_unknown_platform():
    with pytest.raises(ConfigError, match="unknown platform"):
        load_platform("tsmc5")


def test_invalid_site_and_unknown_layers(tech_lef):
    lef = parse_lef(tech_lef)
    pf = load_platform("ihp_sg13g2").model_copy(update={"place_site": "nosuchsite", "macros": {}, "fill_cells": [],
                                                        "tie_cells": {}, "row_height_um": None, "site_width_um": None})
    r = pf.routing.model_copy(update={"min_layer": "Metal9", "io_h_layer": "Metal3", "io_v_layer": "Metal2",
                                      "max_layer": "Metal3", "pdn_layers": []})
    pf = pf.model_copy(update={"routing": r, "tapcell": None})
    c = codes(check_lef_facts(pf, lef))
    assert "INVALID_SITE" in c and "UNKNOWN_LAYER" in c


def test_real_platform_lef_facts():
    pf = load_platform("ihp_sg13g2")
    fs, lef = check_platform(pf)
    if lef is None:
        pytest.skip("IHP collateral not installed")
    assert not errors(fs)
    assert lef.sites["CoreSite"].height == pytest.approx(3.78)


# ---------------------------------------------------------------- design / constraints
def test_missing_clock_in_sdc():
    d = load_design("silicaflux_v")
    assert "NO_CLOCK" in codes(check_sdc_text("set_input_delay 1 [all_inputs]\n", d))
    ok = (PROJECT / d.sdc_template).read_text()
    assert not errors(check_sdc_text(ok, d))


def test_design_inputs_valid():
    d = load_design("silicaflux_v")
    assert not errors(check_design(d, load_platform("ihp_sg13g2")))


def test_lef_parser_macro_facts(tech_lef):
    m = parse_lef(tech_lef).macros["RAM"]
    assert m.is_block and m.width == 100 and m.legal_orients() == {"R0", "MX", "MY", "R180"}
    assert m.pin_side_r0() == "bottom"
    assert set(m.pg_pins()) == {"VDD!", "VSS!"}
    lib = parse_lef_text("MACRO X\n  CLASS CORE ;\nEND X\n")
    assert "X" in lib.macros


def test_non_physical_macro_modes_refused():
    from floorplanlab.pipeline import Run
    spec = load_run(PROJECT / "configs/silicaflux_v/experiments/A_baseline.yaml",
                    {"id": "t_logic_only", "macros": {"mode": "logic_only"}})
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        r = Run(spec, Path(d))
        assert r.check() is False
        assert r.rec["gates"]["15"]["status"] == "FAIL" and "refused" in r.rec["failure_reason"]
