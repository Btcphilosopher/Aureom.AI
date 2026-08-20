from neurax_gpu_core.silicon.area_model import AreaModel
from neurax_gpu_core.silicon.transistor_cost import TransistorCostModel
from neurax_gpu_core.silicon.yield_model import YieldModel
from neurax_gpu_core.utils.config import get_preset


def test_larger_die_area_for_more_sms():
    small = get_preset("efficiency")
    large = get_preset("flagship")
    small_area = AreaModel(small).estimate().total_die_mm2
    large_area = AreaModel(large).estimate().total_die_mm2
    assert large_area > small_area


def test_yield_falls_as_area_grows():
    cfg = get_preset("mainstream")
    model = YieldModel(cfg.silicon)
    small_yield = model.evaluate(50.0).murphy_yield_fraction
    big_yield = model.evaluate(600.0).murphy_yield_fraction
    assert 0.0 <= big_yield <= small_yield <= 1.0


def test_dies_per_wafer_decreases_with_area():
    cfg = get_preset("mainstream")
    model = YieldModel(cfg.silicon)
    assert model.dies_per_wafer(50.0) > model.dies_per_wafer(500.0)


def test_cost_per_good_die_is_positive_and_finite():
    cfg = get_preset("mainstream")
    breakdown = TransistorCostModel(cfg).evaluate()
    assert breakdown.cost_per_good_die_usd > 0
    assert breakdown.cost_per_good_die_usd < float("inf")
    assert breakdown.area.total_die_mm2 > 0


def test_reticle_limit_flag_reacts_to_absurd_sm_count():
    cfg = get_preset("flagship")
    cfg.architecture.num_sms = 100_000
    breakdown = AreaModel(cfg).estimate()
    assert breakdown.fits_reticle_limit is False
