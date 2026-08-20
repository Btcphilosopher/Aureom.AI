import random

from neurax_gpu_core.compute.cuda_core_model import CudaCoreArray, popcount
from neurax_gpu_core.compute.instruction_pipeline import Instruction, OpCode
from neurax_gpu_core.compute.warp_scheduler import Warp, WarpScheduler, WarpState


def test_popcount():
    assert popcount(0) == 0
    assert popcount(0xFFFFFFFF) == 32
    assert popcount(0b1010) == 2


def test_cuda_core_array_partitions_by_warp_size():
    arr = CudaCoreArray(total_cores=128, warp_size=32)
    assert arr.partitions == 4
    assert len(arr.blocks) == 4


def test_processing_block_executes_fma_and_counts_flops():
    arr = CudaCoreArray(total_cores=32, warp_size=32)
    block = arr.blocks[0]
    instr = Instruction(opcode=OpCode.FP32_FMA, warp_id=0, pc=0)
    full_mask = (1 << 32) - 1
    result = block.execute(instr, full_mask, cycle=0)
    assert result.active_lanes == 32
    assert result.flops_retired == 32 * 2  # FMA = 2 flops/lane


def test_divergence_shrinks_active_mask_eventually():
    warp = Warp(warp_id=0, sm_id=0, block_id=0, warp_size=32,
                instructions=[Instruction(opcode=OpCode.BRANCH, warp_id=0, pc=0)])
    rng = random.Random(1)
    shrank = False
    for _ in range(50):
        warp.active_mask = (1 << 32) - 1
        warp.apply_divergence(rng, divergence_probability=1.0)
        if popcount(warp.active_mask) < 32:
            shrank = True
            break
    assert shrank
    assert popcount(warp.active_mask) >= 1  # never fully empties


def test_warp_finishes_after_all_instructions_issued():
    instrs = [Instruction(opcode=OpCode.FP32_ADD, warp_id=0, pc=i) for i in range(3)]
    warp = Warp(warp_id=0, sm_id=0, block_id=0, warp_size=32, instructions=instrs)
    assert not warp.is_finished()
    for _ in range(3):
        warp.advance_pc()
    assert warp.is_finished()


def test_scheduler_only_selects_ready_warps():
    scheduler = WarpScheduler(scheduler_id=0, issue_width=1)
    w1 = Warp(warp_id=0, sm_id=0, block_id=0, warp_size=32,
              instructions=[Instruction(opcode=OpCode.NOP, warp_id=0, pc=0)])
    w2 = Warp(warp_id=1, sm_id=0, block_id=0, warp_size=32,
              instructions=[Instruction(opcode=OpCode.NOP, warp_id=1, pc=0)])
    w2.state = WarpState.STALLED_MEMORY
    scheduler.add_warp(w1)
    scheduler.add_warp(w2)
    selected = scheduler.select(cycle=0)
    assert selected == [w1]


def test_scheduler_removes_finished_warps():
    scheduler = WarpScheduler(scheduler_id=0)
    warp = Warp(warp_id=0, sm_id=0, block_id=0, warp_size=32, instructions=[])
    warp.state = WarpState.DONE
    scheduler.add_warp(warp)
    removed = scheduler.remove_finished()
    assert removed == [0]
    assert 0 not in scheduler.warps
