"""Roofline, workloads, tiling, cache, energy and area models."""
import math

import pytest

from memoryflow.models import area as A
from memoryflow.models import cache as C
from memoryflow.models import energy as E
from memoryflow.models.hardware import EXTMEM_PRESETS, ComputeConfig, ScratchpadConfig, SystemConfig
from memoryflow.models.roofline import Roofline, attainable, measured_point, ridge_point, spm_bank_efficiency
from memoryflow.models.tiling import best_gemm_tiling, gemm_footprint, gemm_traffic_lower_bound
from memoryflow.models.workloads import Conv2d, Dot, Fft, Gemm, SpMV, Stencil2D, VecAdd, default_suite
from memoryflow.provenance import Provenance


def test_attainable_is_min_of_roofs():
    assert attainable(1.0, 100.0, 10.0) == 10.0
    assert attainable(50.0, 100.0, 10.0) == 100.0
    assert ridge_point(100.0, 10.0) == 10.0
    with pytest.raises(ValueError):
        attainable(-1, 1, 1)


def test_peaks_theoretical():
    c = ComputeConfig(clock_hz=1e9, tensor_rows=16, tensor_cols=16, vec_lanes=8, cpu_cores=2)
    assert c.peak_ops("tensor").value == 512e9 and c.peak_ops("tensor").provenance is Provenance.THEORETICAL
    assert c.peak_ops("vector").value == 16e9 and c.peak_ops("cpu").value == 4e9


def test_extmem_bandwidths():
    d = EXTMEM_PRESETS["DDR4-3200 x32"]
    assert d.peak_bw().value == pytest.approx(12.8e9)
    assert d.sustained_bw().value < d.peak_bw().value
    assert EXTMEM_PRESETS["HBM2E 1 stack"].peak_bw().value == pytest.approx(409.6e9)
    assert not EXTMEM_PRESETS["HBM2E 1 stack"].available_at(40)
    assert EXTMEM_PRESETS["DDR4-3200 x32"].available_at(40)


def test_workload_op_counts():
    assert Gemm(4, 5, 6).ops == 240
    assert VecAdd(10).ai_compulsory() == pytest.approx(10 / 60)
    assert Dot(100).ops == 200
    cv = Conv2d(1, 3, 8, 8, 4, 3, 3, 1, 1)
    assert cv.p == 8 and cv.ops == 2 * 4 * 64 * 27
    assert Fft(1024, 1).ops == pytest.approx(5 * 1024 * 10)
    assert SpMV(100, 4).ops == 800


def test_gemm_tiling_fits_and_beats_naive():
    t = best_gemm_tiling(512, 512, 512, 256 * 1024)
    assert t.fits and t.footprint_bytes <= 256 * 1024
    assert t.footprint_bytes == gemm_footprint(t.tm, t.tn, t.tk)
    naive = 512 * 512 * 512 * 2   # every operand from DRAM
    assert t.dram_bytes < naive / 50
    assert t.dram_bytes >= Gemm(512, 512, 512).compulsory_bytes
    assert t.dram_bytes >= 0.25 * gemm_traffic_lower_bound(512, 512, 512, 256 * 1024)


def test_more_spm_never_increases_gemm_traffic():
    prev = math.inf
    for kib in (32, 64, 128, 256, 512, 1024):
        t = best_gemm_tiling(1024, 1024, 1024, kib * 1024).dram_bytes
        assert t <= prev
        prev = t


def test_stencil_and_spmv_capacity_effects():
    small = SystemConfig(spm=ScratchpadConfig(capacity_bytes=64 * 1024))
    big = SystemConfig(spm=ScratchpadConfig(capacity_bytes=64 * 1024 * 1024))
    s = Stencil2D(512, 512, 10)
    assert s.dram_bytes(big) == s.compulsory_bytes < s.dram_bytes(small)
    sp = SpMV(1 << 16, 8)
    assert sp.dram_bytes(small) > sp.dram_bytes(big)


def test_roofline_bounds_and_provenance():
    r = Roofline(SystemConfig())
    assert r.effective_dram_bw() <= r.ceilings["DRAM sustained"][0]
    for w in default_suite():
        pt = r.evaluate(w)
        assert 0 < pt.perf <= pt.peak * (1 + 1e-12)
        assert pt.bound in {"compute", "dram", "dma", "spm"}
        assert pt.provenance is Provenance.ANALYTICAL
    vadd = r.evaluate(VecAdd(1 << 20))
    assert vadd.bound in {"dma", "dram"}


def test_measured_point():
    mp = measured_point("x", "tensor", 1000, 100, 10, 1e9, 1e12)
    assert mp.perf == 1e11 and mp.ai == 10 and mp.provenance is Provenance.RTL_SIMULATION


def test_bank_efficiency_monotonic():
    v = [spm_bank_efficiency(b) for b in (2, 4, 8, 16)]
    assert v == sorted(v) and v[0] == 0.75 and v[-1] < 1


def test_lru_cache_basics():
    c = C.SetAssocCache(256, 64, 2)          # 2 sets x 2 ways
    for a in (0, 128, 0, 256, 128):          # all map to set 0
        c.access(a)
    s = c.stats
    assert (s.accesses, s.hits, s.misses) == (5, 1, 4)


def test_tiled_gemm_has_fewer_misses():
    naive = C.SetAssocCache(8 * 1024, 64, 4).run(C.gemm_trace(48, tile=0))
    tiled = C.SetAssocCache(8 * 1024, 64, 4).run(C.gemm_trace(48, tile=16))
    assert tiled.miss_rate < naive.miss_rate / 3


def test_streaming_miss_rate():
    st = C.SetAssocCache(32 * 1024, 64, 8).run(C.stream_trace(64 * 1024, 4))
    assert st.miss_rate == pytest.approx(C.analytic_streaming_miss_rate(4, 64), rel=0.01)
    assert C.amat(1, 0.1, 100) == 11


def test_sram_energy_anchors():
    assert E.sram_read_pj_per_64b(8) == pytest.approx(10, rel=0.01)
    assert E.sram_read_pj_per_64b(32) == pytest.approx(20, rel=0.01)
    assert E.sram_read_pj_per_64b(1024) == pytest.approx(100, rel=0.01)
    assert E.sram_read_pj_per_64b(32, 28) < E.sram_read_pj_per_64b(32, 65)


def test_dram_power():
    q = E.dram_power_at_bw(1e9, 10.0)
    assert q.value == pytest.approx(0.08)


def test_macro_tiling_mirrors_rtl():
    p = A.plan_macro_tiling(1024, 72, 256, 32)     # tb_sram_prims macro configuration
    assert (p.rows, p.cols, p.instances) == (4, 3, 12)
    assert 0 < p.utilisation <= 1


def test_choose_macro_splits_wide_words():
    plan, area = A.choose_macro(1024, 266, A.AnalyticalSramAreaModel(40))
    assert plan.cols >= 2 and area > 0


def test_area_monotonic_in_capacity_and_node():
    a = [A.spm_area_mm2(k * 1024, 8, 64, 72, 40)[0] for k in (128, 256, 512, 1024)]
    assert a == sorted(a)
    assert A.spm_area_mm2(256 * 1024, 8, 64, 72, 28)[0] < A.spm_area_mm2(256 * 1024, 8, 64, 72, 65)[0]


def test_compiler_table_model(tmp_path):
    p = tmp_path / "lib.csv"
    p.write_text("words,bits,ports,area_um2\n1024,72,1,52000\n2048,72,1,95000\n")
    m = A.CompilerTableAreaModel.from_csv(p)
    assert m.supported(1024, 72) and not m.supported(512, 72)
    assert m.macro_area_um2(1024, 72) == 52000
    assert m.macro_area_um2(4096, 72) == pytest.approx(95000 * 2)
