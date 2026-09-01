// ============================================================================
// AUTO-GENERATED FILE -- DO NOT EDIT BY HAND
//
// Produced by silicaflux.generators.sv_emitter.emit_config_package() from
// architecture "default". Regenerate with:
//     python -m silicaflux_bitcoin.generate --config <yaml> --out <path>
// Source of truth is the architecture spec (silicaflux/architecture/spec.py)
// and the named config file, NOT this file -- edits here will be
// overwritten on the next `generate` run.
// ============================================================================

// Architecture notes:
//   Architecture name : default
//   Process node       : generic/unspecified (informational only, section 23)
//   Core micro-arch    : ITERATIVE
//
//   Clock domain 'core_clk': target 100.0 MHz

package silicaflux_config_pkg;

  // ---- INTERFACE -- external port widths fixed by the Bitcoin protocol ----
  localparam int NONCE_WIDTH = 32;  // Width of the nonce field. Must be 32 for Bitcoin-header compliance (enforced by NonceAllocConfig.validate()).
  localparam int HEADER_WIDTH_BITS = 640;  // 80-byte Bitcoin block header, fixed by the protocol.
  localparam int HASH_WIDTH_BITS = 256;  // SHA-256 digest width, fixed by the algorithm.

  // ---- DATAFLOW -- core count / nonce search partitioning ----
  localparam int NUM_CORES = 4;  // Number of parallel hash_core instances in hash_core_array.sv.
  localparam int NONCE_START = 0;  // First nonce value handed to the allocator.
  localparam int NONCE_STRIDE = 1;  // Per-core nonce increment stride; core i searches NONCE_START + i*NONCE_STRIDE, +NUM_CORES*NONCE_STRIDE, ...

  // ---- PIPELINE -- core micro-architecture and stage count ----
  localparam bit CORE_ARCH_PIPELINED = 1'b0;  // 1 = sha256_pipeline.sv (spatially unrolled), 0 = sha256_compressor.sv (iterative, 1 round/cycle).
  localparam int PIPELINE_DEPTH = 1;  // Number of pipeline stages when CORE_ARCH_PIPELINED=1; 64/PIPELINE_DEPTH rounds of combinational logic per stage. Ignored (treated as don't-care) when CORE_ARCH_PIPELINED=0.
  localparam int ROUNDS_PER_STAGE = 1;  // Derived: 64 / PIPELINE_DEPTH for the pipelined core, else 1.

  // ---- REGISTER -- message-schedule and telemetry storage architecture ----
  localparam string SCHEDULE_ARCHITECTURE = "SLIDING_WINDOW";  // Message-schedule storage/advance strategy; see sha256_message_schedule.sv and docs/architecture.md section 6.
  localparam int TELEMETRY_COUNTER_WIDTH = 32;  // Bit width of each telemetry counter register.

  // ---- CONTROL -- control-plane / compile-time feature enables ----
  localparam bit ENABLE_ASSERTIONS = 1'b1;  // Compile-time enable for SVA assertions (formal/, tb/ binds).
  localparam bit ENABLE_TELEMETRY = 1'b1;  // Compile-time enable for telemetry.sv instantiation in miner_top.sv.

  // ---- CLOCK -- clock domain metadata (abstract, technology-independent) ----
  localparam real CLOCK_FREQUENCY_TARGET_MHZ = 100.000;  // Abstract target only -- NOT a timing constraint or Fmax claim. Real Fmax is whatever STA against a real technology library reports.
  localparam bit ENABLE_CLOCK_GATING = 1'b0;  // Research switch for clock-gating the idle pipeline stages/cores; see rtl/control/miner_controller.sv and docs/architecture.md section 20.

endpackage : silicaflux_config_pkg
