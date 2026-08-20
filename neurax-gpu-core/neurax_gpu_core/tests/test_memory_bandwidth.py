from neurax_gpu_core.memory.vram_model import VRAMModel


def test_single_request_completion_respects_latency_floor():
    vram = VRAMModel(capacity_gb=8, bandwidth_gbps=400, latency_ns=300, num_channels=4)
    completion = vram.service(address=0, size_bytes=128, issue_time_ns=0.0)
    assert completion >= 300.0


def test_bandwidth_saturation_increases_queue_delay():
    vram = VRAMModel(capacity_gb=8, bandwidth_gbps=100, latency_ns=100, num_channels=1)
    # Flood a single channel with many back-to-back large requests.
    completions = []
    for i in range(20):
        completions.append(vram.service(address=0, size_bytes=1_000_000, issue_time_ns=0.0))
    # Later requests on the same saturated channel must complete later.
    assert completions[-1] > completions[0]
    assert vram.average_queue_delay_ns() > 0.0


def test_multiple_channels_spread_load():
    vram = VRAMModel(capacity_gb=8, bandwidth_gbps=400, latency_ns=100, num_channels=8)
    assert len(vram.channels) == 8
    # Addresses interleaved at 256B granularity should land on different channels.
    touched = {id(vram._channel_for(addr)) for addr in range(0, 8 * 256, 256)}
    assert len(touched) == 8


def test_achieved_bandwidth_never_exceeds_capacity_over_long_run():
    # All requests target the same address -> the same single channel, so this
    # also exercises single-channel serialisation, not just the aggregate cap.
    vram = VRAMModel(capacity_gb=8, bandwidth_gbps=200, latency_ns=50, num_channels=4)
    last_completion_ns = 0.0
    for i in range(500):
        last_completion_ns = vram.service(address=0, size_bytes=4096, issue_time_ns=float(i))
    achieved = vram.achieved_bandwidth_gbps(elapsed_ns=last_completion_ns)
    assert achieved <= vram.total_bandwidth_gbps + 1e-6
    # Single-channel bandwidth share is bandwidth/num_channels; a run that
    # only ever hits one channel can't exceed that share either.
    assert achieved <= vram.channel_bandwidth_bytes_per_ns + 1e-6
