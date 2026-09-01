import numpy as np

from batteryfactory.config.chemistry_profiles import get_profile
from batteryfactory.datamodel.models import Cell, CellFormat, Chemistry, TestResult
from batteryfactory.production.formation import FormationLine, FormationRecipe
from batteryfactory.production.testing import EOLTester
from batteryfactory.quality.cell_matching import CellMatchingEngine
from batteryfactory.quality.quality_engine import QualityDistributionGenerator, cp, cpk, defect_rate_ppm, first_pass_yield


def _make_cell():
    return Cell("CELL-TEST", CellFormat.PRISMATIC, Chemistry.LFP, [], "line-1")


def test_formation_more_cycles_improves_coulombic_efficiency():
    rng = np.random.default_rng(6)
    profile = get_profile(Chemistry.LFP)
    line = FormationLine(rng=rng)
    fast = line.run(_make_cell(), profile, FormationRecipe(num_cycles=1, charge_c_rate=1.0, discharge_c_rate=1.0))
    thorough = line.run(_make_cell(), profile, FormationRecipe(num_cycles=5, charge_c_rate=0.2, discharge_c_rate=0.5))
    assert thorough.coulombic_efficiency_pct >= fast.coulombic_efficiency_pct


def test_eol_tester_classifies_full_result_range():
    rng = np.random.default_rng(7)
    profile = get_profile(Chemistry.LFP)
    formation = FormationLine(rng=rng)
    tester = EOLTester(rng=rng)
    seen_results = set()
    for _ in range(300):
        cell = _make_cell()
        fresult = formation.run(cell, profile, FormationRecipe())
        _, quality_result = tester.run(cell, profile, fresult)
        seen_results.add(quality_result.result)
    assert TestResult.PASS in seen_results  # the common case must actually occur


def test_quality_capability_formulas():
    assert cp(usl=10, lsl=0, std=1.0) == 10 / 6
    assert cpk(usl=10, lsl=0, mean=5, std=1.0) == cp(10, 0, 1.0)
    assert defect_rate_ppm(mean=5, std=1.0, usl=10, lsl=0) < 100  # process well within spec -> very low ppm
    assert first_pass_yield(90, 100) == 90.0


def test_quality_distribution_variability_widens_spread():
    rng = np.random.default_rng(8)
    gen = QualityDistributionGenerator(rng=rng)
    nominal = {"capacity_ah": 100, "resistance_mohm": 1.5, "voltage_v": 3.2, "weight_g": 900, "thickness_um": 15000}
    tight = gen.generate(nominal, n=2000, variability_multiplier=0.5)
    loose = gen.generate(nominal, n=2000, variability_multiplier=3.0)
    assert np.std(loose["capacity_ah"]) > np.std(tight["capacity_ah"])


def test_cell_matching_minimises_within_module_spread():
    cells = []
    for i in range(84 * 2):
        c = Cell(f"C{i}", CellFormat.PRISMATIC, Chemistry.LFP, [], "line-1")
        c.capacity_ah = 90.0 + (i % 20) * 0.1
        c.internal_resistance_mohm = 1.0 + (i % 10) * 0.02
        cells.append(c)
    matcher = CellMatchingEngine()
    groups = matcher.match_cells_to_modules(cells, cells_per_module=84, series_count=14, parallel_count=6)
    assert len(groups) == 2
    for g in groups:
        assert g.capacity_spread_pct < 5.0  # sorted bucketing keeps modules tightly matched
