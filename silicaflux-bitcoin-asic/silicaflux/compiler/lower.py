"""
silicaflux.compiler.lower -- the deterministic MinerArchitecture -> IRDesign
lowering pass.

`lower()` (1) re-validates the architecture (belt-and-braces: the spec
layer validates on construction already, but this is the compiler's own
gate and must not trust its input), then (2) emits one IRParam per
architectural knob, tagged with the IRKind it structurally belongs to.
Nothing here is a hash computation -- this only ever produces parameters
and comments for the RTL to consume as `localparam`/`parameter`.
"""
from __future__ import annotations

from silicaflux.architecture.spec import ArchitectureError, MinerArchitecture
from silicaflux.ir.nodes import IRClockDomain, IRDesign, IRKind, IRParam


def lower(arch: MinerArchitecture, top_name: str = "miner_top") -> IRDesign:
    arch.validate()  # re-validate; never trust the caller already did

    params: list[IRParam] = []

    # --- DATAFLOW: how many independent hash cores, and their nonce split ---
    params.append(IRParam("NUM_CORES", arch.num_cores, IRKind.DATAFLOW,
                           "Number of parallel hash_core instances in hash_core_array.sv."))
    params.append(IRParam("NONCE_START", arch.nonce.nonce_start, IRKind.DATAFLOW,
                           "First nonce value handed to the allocator."))
    params.append(IRParam("NONCE_STRIDE", arch.nonce.nonce_stride, IRKind.DATAFLOW,
                           "Per-core nonce increment stride; core i searches "
                           "NONCE_START + i*NONCE_STRIDE, +NUM_CORES*NONCE_STRIDE, ..."))

    # --- PIPELINE: core micro-architecture selection ---
    is_pipelined = arch.pipeline.architecture.value == "PIPELINED"
    params.append(IRParam("CORE_ARCH_PIPELINED", is_pipelined, IRKind.PIPELINE,
                           "1 = sha256_pipeline.sv (spatially unrolled), "
                           "0 = sha256_compressor.sv (iterative, 1 round/cycle).",
                           sv_type="bit"))
    params.append(IRParam("PIPELINE_DEPTH", arch.pipeline.pipeline_depth, IRKind.PIPELINE,
                           "Number of pipeline stages when CORE_ARCH_PIPELINED=1; "
                           "64/PIPELINE_DEPTH rounds of combinational logic per stage. "
                           "Ignored (treated as don't-care) when CORE_ARCH_PIPELINED=0."))
    params.append(IRParam("ROUNDS_PER_STAGE", arch.pipeline.rounds_per_stage(), IRKind.PIPELINE,
                           "Derived: 64 / PIPELINE_DEPTH for the pipelined core, else 1."))

    # --- REGISTER: message-schedule storage architecture ---
    params.append(IRParam("SCHEDULE_ARCHITECTURE", f'"{arch.pipeline.schedule_architecture.value}"',
                           IRKind.REGISTER,
                           "Message-schedule storage/advance strategy; see "
                           "sha256_message_schedule.sv and docs/architecture.md section 6.",
                           sv_type="string"))
    params.append(IRParam("TELEMETRY_COUNTER_WIDTH", arch.telemetry.counter_width, IRKind.REGISTER,
                           "Bit width of each telemetry counter register."))

    # --- CONTROL / INTERFACE: widths the control plane and header-load
    #     interface are built against ---
    params.append(IRParam("NONCE_WIDTH", arch.nonce.nonce_width, IRKind.INTERFACE,
                           "Width of the nonce field. Must be 32 for Bitcoin-header "
                           "compliance (enforced by NonceAllocConfig.validate())."))
    params.append(IRParam("HEADER_WIDTH_BITS", 640, IRKind.INTERFACE,
                           "80-byte Bitcoin block header, fixed by the protocol."))
    params.append(IRParam("HASH_WIDTH_BITS", 256, IRKind.INTERFACE,
                           "SHA-256 digest width, fixed by the algorithm."))
    params.append(IRParam("ENABLE_ASSERTIONS", arch.enable_assertions, IRKind.CONTROL,
                           "Compile-time enable for SVA assertions (formal/, tb/ binds).",
                           sv_type="bit"))
    params.append(IRParam("ENABLE_TELEMETRY", arch.telemetry.enabled, IRKind.CONTROL,
                           "Compile-time enable for telemetry.sv instantiation in miner_top.sv.",
                           sv_type="bit"))

    clocks = [IRClockDomain(arch.clock.name, arch.clock.target_frequency_mhz, arch.clock.enable_clock_gating)]
    params.append(IRParam("CLOCK_FREQUENCY_TARGET_MHZ", arch.clock.target_frequency_mhz, IRKind.CLOCK,
                           "Abstract target only -- NOT a timing constraint or Fmax claim. "
                           "Real Fmax is whatever STA against a real technology library reports.",
                           sv_type="real"))
    params.append(IRParam("ENABLE_CLOCK_GATING", arch.clock.enable_clock_gating, IRKind.CLOCK,
                           "Research switch for clock-gating the idle pipeline stages/cores; "
                           "see rtl/control/miner_controller.sv and docs/architecture.md section 20.",
                           sv_type="bit"))

    notes = [
        f"Architecture name : {arch.name}",
        f"Process node       : {arch.process_node} (informational only, section 23)",
        f"Core micro-arch    : {arch.pipeline.architecture.value}",
    ]

    return IRDesign(
        top_name=top_name,
        source_config_name=arch.name,
        params=params,
        clock_domains=clocks,
        notes=notes,
    )
