"""Python cycle/analytical models vs RTL-measured anchors.

The anchors below are MF_METRIC values from the Verilator regression of this
release (build/rtl_results.json).  If the RTL changes, re-run
`memoryflow rtl` and these tests keep the models honest.
"""
import pytest

from memoryflow.models import banking as B
from memoryflow.models import dataflow as D
from memoryflow.models import dma as M

RTL_SPM_MOD = {"spm_stride1_throughput": 2.994152, "spm_stride4_throughput": 1.5,
               "spm_random3_throughput": 2.252252, "spm_single_port_throughput": 1.0,
               "spm_hotbank_throughput": 1.0}
RTL_SPM_XOR = {"spm_stride4_throughput": 2.389, "spm_stride8_throughput": 1.997, "spm_stride16_throughput": 1.0}
RTL_SPM_RSP2 = {"spm_single_port_throughput": 0.5, "spm_stride1_throughput": 1.501}
RTL_DMA = {"dma_ext2spm_4k_burst1_cycles": 2480, "dma_ext2spm_4k_burst2_cycles": 1306,
           "dma_ext2spm_4k_burst4_cycles": 730, "dma_ext2spm_4k_burst16_cycles": 728,
           "dma_spm2spm_4k_burst1_cycles": 1036, "dma_spm2spm_4k_burst4_cycles": 652}
RTL_DMA_SKEW = {8: 588, 16: 556}
RTL_TENSOR = {(8, True): 265, (8, False): 323, (32, True): 289, (32, False): 515}


@pytest.mark.parametrize("rtl,setup", [(RTL_SPM_MOD, ("spm_mod")), (RTL_SPM_XOR, "spm_xor"), (RTL_SPM_RSP2, "spm_rsp2")])
def test_spm_model_within_1pct_of_rtl(rtl, setup):
    rows = B.calibration_table({setup: rtl})
    assert len(rows) == len(rtl)
    for r in rows:
        assert abs(r["error_pct"]) < 1.0, r


def test_spm_single_port_littles_law():
    for depth, exp in ((1, 0.25), (2, 0.5), (3, 0.75), (4, 1.0), (8, 1.0)):
        r = B.simulate_spm([list(range(400))], 4, 256, "modulo", depth)
        assert r.throughput == pytest.approx(exp, abs=0.01)


def test_spm_random_vs_analytic():
    sim = B.simulate_spm(B.random_streams(3, 3000, 1024), 4, 256, "modulo").throughput
    ana = B.expected_random_throughput(3, 4)
    assert sim == pytest.approx(ana, rel=0.05)


def test_dma_cycle_model_within_1pct():
    for key, rtl in RTL_DMA.items():
        b = int(key.split("burst")[1].split("_")[0])
        src = "ext" if "ext2spm" in key else "spm"
        sim = M.simulate_dma_copy(4096, b, src, "spm", dst_addr=0 if src == "ext" else 0x2000).cycles
        assert abs(sim - rtl) / rtl < 0.01, (key, sim, rtl)


def test_dma_cycle_model_skewed_spm_copy():
    for b, rtl in RTL_DMA_SKEW.items():
        sim = M.simulate_dma_copy(4096, b, "spm", "spm", dst_addr=0x2008).cycles
        assert abs(sim - rtl) / rtl < 0.01


def test_dma_analytic_latency_bound_regime():
    e = M.dma_copy_cycles_analytic(4096, 16, 21)
    assert e.bound == "latency" and abs(e.cycles - 728) / 728 < 0.02


def test_dma_path_bw_and_bdp():
    bw = M.dma_path_bw(8, 500e6, 45, 16, 16)
    assert bw == pytest.approx(16 / 52 * 8 * 500e6)
    assert M.required_outstanding_beats(8.96e9, 90e-9, 16) == 51


@pytest.mark.parametrize("k,dbuf", list(RTL_TENSOR))
def test_tensor_tile_model_matches_rtl(k, dbuf):
    assert D.tensor_tiles_cycles(k, 8, dbuf=dbuf) == pytest.approx(RTL_TENSOR[(k, dbuf)], rel=0.015)


def test_pipeline_sim_matches_analytic_and_double_buffer_helps():
    for tl, tc, ts in ((10, 5, 2), (3, 8, 3), (5, 5, 5)):
        sim = D.pipeline_sim(20, tl, tc, ts, nbuf=3).makespan
        assert sim == pytest.approx(D.pipeline_analytic(20, tl, tc, ts, 3))
        assert D.pipeline_sim(20, tl, tc, ts, 1).makespan > D.pipeline_sim(20, tl, tc, ts, 2).makespan
    assert D.pipeline_sim(10, 1, 4, 0, 1).makespan == D.pipeline_analytic(10, 1, 4, 0, 1)


def test_deadlock_predicate_matches_rtl_experiment():
    assert D.joined_stream_deadlock(4, 16) is True        # tb_deadlock VEC_IN_FIFO=4 -> DEADLOCK
    assert D.joined_stream_deadlock(16, 16) is False      # VEC_IN_FIFO=16 -> PASS
    assert D.joined_stream_deadlock(4, 16, sequenced=True) is False


def test_operand_reuse():
    assert D.operand_bytes_per_mac(8, 8) == 0.25
    assert D.operand_bytes_per_mac(16, 16) == 0.125
    assert D.reuse_traffic_factor(16, 8, 2) == 2
