import numpy as np

from batteryfactory.datamodel.models import CellFormat, Chemistry
from batteryfactory.production.calendering import CalenderingModel, CalenderingParameters
from batteryfactory.production.cell_assembly import CellAssemblyLine
from batteryfactory.production.coating import CoatingMachine, CoatingParameters
from batteryfactory.production.electrode_line import ElectrodeLineConfig, ElectrodeProductionLine
from batteryfactory.production.mixing import MixingProcess, MixingRecipe


def test_mixing_quality_degrades_with_time_deviation():
    rng = np.random.default_rng(1)
    mixer = MixingProcess(rng=rng)
    good_recipe = MixingRecipe(94, 3, 3, 45, 90, 25, 4000)  # mixing_time_min=90 hits the target viscosity dead-on
    bad_recipe = MixingRecipe(94, 3, 3, 45, 10, 25, 4000)  # way under-mixed
    good = mixer.run(good_recipe, 100)
    bad = mixer.run(bad_recipe, 100)
    assert good.quality_score > bad.quality_score


def test_coating_defects_increase_with_speed():
    rng = np.random.default_rng(2)
    machine = CoatingMachine(rng=rng)
    slow = machine.run(CoatingParameters(10, 80, 600, 110), slurry_quality_score=1.0)
    fast = machine.run(CoatingParameters(100, 80, 600, 110), slurry_quality_score=1.0)
    assert fast.defects.total_defect_rate >= slow.defects.total_defect_rate


def test_calendering_increases_density_with_pressure():
    model = CalenderingModel()
    low = model.compute(CalenderingParameters(50, 60, 30, 40))
    high = model.compute(CalenderingParameters(500, 60, 30, 40))
    assert high.density_g_cc > low.density_g_cc
    assert high.porosity_pct < low.porosity_pct


def test_electrode_line_produces_batch_with_traceable_material_ids():
    rng = np.random.default_rng(3)
    line = ElectrodeProductionLine(rng=rng)
    config = ElectrodeLineConfig(
        electrode_type="cathode",
        mixing_recipe=MixingRecipe(94, 3, 3, 45, 90, 25, 4500),
        coating_params=CoatingParameters(30, 80, 600, 110),
        calendering_params=CalenderingParameters(300, 60, 30, 40),
    )
    result = line.run_batch(config, batch_size_kg=50, material_batch_ids=["MATB-001", "MATB-002"])
    assert result.batch.material_batch_ids == ["MATB-001", "MATB-002"]
    assert 0 < result.stage_yield_pct <= 100
    assert result.batch in line.stored_batches


def test_cell_assembly_recipe_differs_by_format():
    rng = np.random.default_rng(4)
    cyl = CellAssemblyLine(CellFormat.CYLINDRICAL, Chemistry.LFP, "line-1", rng=rng)
    pouch = CellAssemblyLine(CellFormat.POUCH, Chemistry.LFP, "line-1", rng=rng)
    cyl_steps = {type(m).name for m in cyl.chain}
    pouch_steps = {type(m).name for m in pouch.chain}
    assert "winding" in cyl_steps
    assert "casing" not in pouch_steps  # pouch cells use a laminate pouch, not a rigid casing


def test_cell_assembly_produces_cell_or_scraps():
    rng = np.random.default_rng(5)
    line = CellAssemblyLine(CellFormat.PRISMATIC, Chemistry.NMC, "line-1", rng=rng)
    outcomes = [line.assemble([]) for _ in range(200)]
    assert any(o.cell is not None for o in outcomes)
    assert any(o.cell is None for o in outcomes)  # some defect rate expected over 200 runs
