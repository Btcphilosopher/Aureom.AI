from neurax_gpu_core.architecture.chip_layout import ChipLayout
from neurax_gpu_core.architecture.gpu_design import GPUDesign
from neurax_gpu_core.architecture.interconnect import Interconnect
from neurax_gpu_core.utils.config import GPUConfig


def test_chip_layout_places_every_sm_exactly_once():
    layout = ChipLayout(num_sms=40, sms_per_gpc=8)
    assert len(layout.placements) == 40
    assert {p.sm_id for p in layout.placements.values()} == set(range(40))


def test_chip_layout_neighbours_are_symmetric():
    layout = ChipLayout(num_sms=16, sms_per_gpc=4)
    for sm_id, placement in layout.placements.items():
        for neighbour in layout.neighbours(sm_id):
            assert sm_id in layout.neighbours(neighbour)


def test_interconnect_congestion_rises_with_traffic():
    ic = Interconnect(bandwidth_gbps=100, topology="crossbar")
    ic.record_traffic(bytes_moved=10)
    low = ic.congestion_fraction(window_ns=1000)
    ic.reset_window()
    ic.record_traffic(bytes_moved=100_000)
    high = ic.congestion_fraction(window_ns=1000)
    assert high > low


def test_interconnect_topology_efficiency_ordering():
    crossbar = Interconnect(bandwidth_gbps=100, topology="crossbar")
    ring = Interconnect(bandwidth_gbps=100, topology="ring")
    assert crossbar.effective_bandwidth_gbps > ring.effective_bandwidth_gbps


def test_gpu_design_assembles_all_subsystems():
    cfg = GPUConfig()
    cfg.architecture.num_sms = 10
    design = GPUDesign(cfg)
    assert len(design.sms) == 10
    assert design.total_cuda_cores() == 10 * cfg.compute.cuda_cores_per_sm
    summary = design.summary()
    assert summary["num_sms"] == 10
    assert summary["memory_bandwidth_gbps"] > 0


def test_gpu_design_uses_hbm_when_configured():
    cfg = GPUConfig()
    cfg.memory.use_hbm = True
    design = GPUDesign(cfg)
    assert design.summary()["memory_type"] == "HBM"
