import random

from neurax_gpu_core.architecture.gpu_design import GPUDesign
from neurax_gpu_core.compute.instruction_pipeline import Instruction, OpCode
from neurax_gpu_core.execution.kernel_dispatch import Kernel, KernelDispatcher
from neurax_gpu_core.execution.warp_execution import WarpExecutionEngine
from neurax_gpu_core.utils.config import GPUConfig


def _tiny_kernel(name="k", grid=8, block=64, n_instr=6) -> Kernel:
    template = [Instruction(opcode=OpCode.FP32_ADD, warp_id=-1, pc=i) for i in range(n_instr)]
    return Kernel(name=name, grid_size=grid, block_size=block, instr_template=template)


def _tiny_design(num_sms=2) -> GPUDesign:
    cfg = GPUConfig()
    cfg.architecture.num_sms = num_sms
    cfg.compute.max_warps_per_sm = 8
    return GPUDesign(cfg)


def test_dispatcher_queues_blocks_when_sms_are_full():
    design = _tiny_design(num_sms=1)
    dispatcher = KernelDispatcher(sms=design.sms, warp_size=design.config.compute.warp_size)
    kernel = _tiny_kernel(grid=20, block=256)  # far more warps than 1 SM can hold
    dispatcher.launch(kernel, launch_cycle=0)
    dispatcher.try_dispatch(cycle=0)
    assert dispatcher.queue_depth() > 0  # some blocks had to wait


def test_dispatcher_eventually_drains_with_execution():
    design = _tiny_design(num_sms=2)
    dispatcher = KernelDispatcher(sms=design.sms, warp_size=design.config.compute.warp_size)
    engine = WarpExecutionEngine(design.sms, dispatcher, design.memory_controller, random.Random(0))
    kernel = _tiny_kernel(grid=6, block=64, n_instr=4)
    run = dispatcher.launch(kernel, launch_cycle=0)

    for cycle in range(2000):
        engine.run_cycle(cycle, freq_ghz=2.0, divergence_probability=0.0)
        if run.is_complete:
            break

    assert run.is_complete
    assert run.completion_cycle is not None
    assert run.latency_cycles() is not None and run.latency_cycles() >= 0


def test_kernel_run_not_complete_until_all_blocks_done():
    design = _tiny_design(num_sms=2)
    dispatcher = KernelDispatcher(sms=design.sms, warp_size=design.config.compute.warp_size)
    kernel = _tiny_kernel(grid=4, block=32, n_instr=2)
    run = dispatcher.launch(kernel, launch_cycle=0)
    assert not run.is_complete
    assert run.blocks_completed == 0
    assert run.total_blocks == 4
