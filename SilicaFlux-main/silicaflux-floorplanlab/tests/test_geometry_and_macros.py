"""Die/core geometry, macro legality, pin constraints, PDN design rules (GATE 5/6/7/9)."""
import pytest

from floorplanlab.config import FloorplanSpec, load_platform
from floorplanlab.geometry import (ARRANGEMENTS, Box, MacroInst, Placement, arrange, mode_a, orient_facing,
                                   size_mode_b, snap_placements)
from floorplanlab.lef import parse_lef
from floorplanlab.validate import (check_geometry, check_macro_channels_pdn, check_macro_placement,
                                   check_macro_pin_coverage, check_pin_plan, errors)


def codes(fs):
    return {f.code for f in fs if f.severity == "error"}


def ram(n, k):
    return MacroInst(n, "RAM", 100.0, 50.0, "main_sram", k, "bottom")


def test_mode_b_accounts_regions_separately():
    spec = FloorplanSpec(mode="B", target_util=0.5, aspect_ratio=1.0, core_margin_um=10, corridor_um=5,
                         pdn_overhead=0.05, logic_growth=1.0)
    macros = [ram(f"m{i}", (i, 0)) for i in range(4)]
    g = size_mode_b(spec, 10000.0, macros, halo=5, site_w=0.5, row_h=4.0, mgrid=0.005)
    b = g.breakdown
    naive = (10000 + 4 * 5000) / 0.5          # the forbidden "everything / util" sizing
    assert b["std_cell_region_required_um2"] == pytest.approx(20000)
    assert b["macro_halo_area_um2"] > 0 and b["routing_corridor_area_um2"] > 0 and b["pdn_overhead_area_um2"] > 0
    assert g.core.area != pytest.approx(naive, rel=0.05)
    assert g.core.w % 0.5 == pytest.approx(0, abs=1e-6) or abs(g.core.w / 0.5 - round(g.core.w / 0.5)) < 1e-6
    assert abs(g.core.h / 4.0 - round(g.core.h / 4.0)) < 1e-6
    assert g.die.contains(g.core)


def test_mode_b_grows_to_envelope():
    spec = FloorplanSpec(mode="B", target_util=0.5, aspect_ratio=1.0, core_margin_um=10)
    g = size_mode_b(spec, 100.0, [ram("m", (0, 0))], 5, 0.5, 4.0, 0.005, envelope=(400, 120))
    assert g.core.w >= 400 and g.breakdown["grown_to_arrangement_envelope"]


def test_invalid_core_coordinates_and_utilisation(tech_lef):
    lef = parse_lef(tech_lef)
    pf = load_platform("ihp_sg13g2")
    spec = FloorplanSpec(mode="A", die_area=[0, 0, 100, 100], core_area=[10, 10, 150, 90])
    g = mode_a(spec, 1000.0, [], 0)
    assert "CORE_OUTSIDE_DIE" in codes(check_geometry(g, pf, lef))
    spec2 = FloorplanSpec(mode="A", die_area=[0, 0, 100, 100], core_area=[10, 10, 90, 90])
    g2 = mode_a(spec2, 99999.0, [], 0)
    assert "OVER_UTILISED" in codes(check_geometry(g2, pf, lef))
    g3 = mode_a(spec2, 100.0, [], 0)
    assert "MARGIN_TOO_SMALL" in codes(check_geometry(g3, pf, lef, ring_extent_um=20))


def test_macro_overlap_unplaced_orientation_and_outside(tech_lef):
    lef = parse_lef(tech_lef)
    core = Box(0, 0, 1000, 1000)
    ms = [ram("a", (0, 0)), ram("b", (0, 1)), ram("c", (1, 0)), ram("d", (1, 1))]
    pl = [Placement("a", "RAM", 100, 100, "R0", 100, 50), Placement("b", "RAM", 150, 120, "R0", 100, 50),
          Placement("c", "RAM", 500, 500, "R90", 100, 50), Placement("x", "RAM", 700, 100, "R0", 100, 50)]
    c = codes(check_macro_placement(pl, core, ms, 5, 10, ["R0", "MX", "MY", "R180"], lef, {"RAM": 4}))
    assert {"MACRO_OVERLAP", "UNPLACED_MACRO", "ILLEGAL_ORIENT", "UNKNOWN_MACRO"} <= c
    pl2 = [Placement("a", "RAM", 950, 100, "R0", 100, 50)]
    assert "MACRO_OUTSIDE_CORE" in codes(check_macro_placement(pl2, core, ms[:1], 5, 10, ["R0"], lef))


def test_macro_pin_access(tech_lef):
    lef = parse_lef(tech_lef)
    core = Box(0, 0, 1000, 1000)
    ms = [ram("a", (0, 0)), ram("b", (0, 1))]
    # a's pins (bottom, R0) face b's back side only 2 um away -> blocked
    pl = [Placement("a", "RAM", 100, 300, "R0", 100, 50), Placement("b", "RAM", 100, 230, "R0", 100, 50)]
    assert "PIN_ACCESS_BLOCKED" in codes(check_macro_placement(pl, core, ms, 5, 40, ["R0", "MX"], lef))
    # pins facing the core edge
    pl2 = [Placement("a", "RAM", 100, 0, "R0", 100, 50)]
    assert "PIN_ACCESS_EDGE" in codes(check_macro_placement(pl2, core, ms[:1], 0, 10, ["R0"], lef))
    assert orient_facing("bottom", "top", ["R0", "MX"]) == "MX"


def test_all_arrangements_legal(tech_lef):
    lef = parse_lef(tech_lef)
    ms = [ram(f"s{b}{i}", (b, i)) for b in range(4) for i in range(2)]
    ms += [MacroInst(f"t{i}", "RAM", 100, 50, "tspm", (i,), "bottom") for i in range(4)]
    for name in ARRANGEMENTS:
        probe = arrange(name, Box(0, 0, 1e5, 1e5), ms, 5, 20, ["R0", "MX", "MY", "R180"], "bottom", 40)
        core = Box(10, 10, 10 + probe.envelope_w + 400, 10 + probe.envelope_h + 200)
        pl = snap_placements(arrange(name, core, ms, 5, 20, ["R0", "MX", "MY", "R180"], "bottom", 40).placements,
                             core, 0.5, 4.0, 0.005)
        assert not errors(check_macro_placement(pl, core, ms, 5, 20, ["R0", "MX", "MY", "R180"], lef)), name


def test_pdn_channel_rule(tech_lef):
    lef = parse_lef(tech_lef)
    params = {"strap1_layer": "Metal2", "strap1_pitch": 30.0, "strap1_width": 2.0}
    pl = [Placement("a", "RAM", 0, 0, "R0", 100, 50), Placement("b", "RAM", 120, 0, "R0", 100, 50)]
    assert "PDN_CHANNEL" in codes(check_macro_channels_pdn(pl, params, lef))
    pl[1] = Placement("b", "RAM", 140, 0, "R0", 100, 50)
    assert not errors(check_macro_channels_pdn(pl, params, lef))


def test_macro_pin_coverage_rule(tech_lef):
    lef = parse_lef(tech_lef)
    pf = load_platform("ihp_sg13g2").model_copy(update={"macros": {"RAM": {"lef": str(tech_lef)}}})
    # pin stripes are vertical (12 / 50 um tall): horizontal Metal1 straps at pitch 5 cross all of them
    ok = {"macro_connect": ["Metal3", "Metal1"], "strap1_layer": "Metal1", "strap1_pitch": 5.0, "strap1_width": 1.0}
    assert not check_macro_pin_coverage(ok, pf, lef)
    # pitch 20: the 12 um VDD! stripe may be missed (warning), the 50 um ones are still crossed
    mid = dict(ok, strap1_pitch=20.0)
    fs = check_macro_pin_coverage(mid, pf, lef)
    assert not errors(fs) and any(f.code == "PDN_MACRO_STRIPE_COVERAGE" for f in fs)
    # pitch 60 > every stripe -> error
    assert "PDN_MACRO_PIN_COVERAGE" in codes(check_macro_pin_coverage(dict(ok, strap1_pitch=60.0), pf, lef))
    # straps PARALLEL to the pin stripes (vertical Metal2 over vertical pins): the attempt-1 failure mode
    par = {"macro_connect": ["Metal3", "Metal2"], "strap1_layer": "Metal2", "strap1_pitch": 5.0, "strap1_width": 1.0}
    assert "PDN_MACRO_PIN_COVERAGE" in codes(check_macro_pin_coverage(par, pf, lef))


def test_overlapping_pin_constraints():
    die = Box(0, 0, 500, 500)
    ports = ["clk", "rst", "a[0]", "a[1]"]
    fs = check_pin_plan([("g1", "left", ["clk", "a*"]), ("g2", "right", ["a[1]"])], ports, die, {"left": 0.5}, 2, 10)
    assert "PIN_CONFLICT" in codes(fs)
    fs2 = check_pin_plan([("g1", "left", ["nosuchport"])], ports, die, {}, 2, 10)
    assert "PIN_UNKNOWN" in codes(fs2)
    many = [f"p[{i}]" for i in range(2000)]
    fs3 = check_pin_plan([("g", "top", ["p*"])], many, die, {"top": 0.5}, 2, 10)
    assert "PIN_CAPACITY" in codes(fs3)
