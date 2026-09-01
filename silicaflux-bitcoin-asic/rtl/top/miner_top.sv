// miner_top.sv -- top-level SilicaFlux Bitcoin SHA-256 miner: header
// loading interface -> miner_controller (job FSM) -> hash_core_array
// (NUM_CORES parallel nonce search) -> telemetry (side branch, section
// 33). This is the "miner_top" from section 17/45 -- the single module
// a testbench (tb/system/tb_miner_top.sv) or an eventual synthesis flow
// targets as the design root.
//
// Parameters here are deliberately independent of any particular
// SilicaFlux-generated config package: miner_top takes NUM_CORES/
// ENABLE_TELEMETRY directly so it (and every testbench that instantiates
// it) stays usable standalone. `python -m silicaflux_bitcoin.generate`
// still produces rtl/generated/silicaflux_config_pkg.sv describing a
// named architecture's chosen values for these same parameters, for a
// build script to pass through -- see docs/silicaflux_ir.md.
module miner_top #(
  parameter int NUM_CORES        = 4,
  parameter bit ENABLE_TELEMETRY = 1
) (
  input  logic         clk,
  input  logic         rst_n,

  // Header loading interface (section 12).
  input  logic          header_valid,
  output logic           header_ready,
  input  logic [607:0]   header_data,
  input  logic            start,
  input  logic            stop,

  input  logic [31:0]     nonce_start_cfg,
  input  logic [31:0]     nonce_stride_cfg,

  output logic             busy,
  output logic             found,
  output logic [31:0]      found_nonce,
  output logic [255:0]     found_hash,
  output logic [31:0]      found_core_id,
  output logic              exhausted,
  output logic              error,
  output logic [3:0]        error_code,
  output logic [3:0]        state_out,

  // Telemetry outputs (section 33) -- '0 when ENABLE_TELEMETRY=0, and the
  // telemetry module itself is not instantiated (no area cost either way).
  output logic [31:0]     tm_clock_cycles,
  output logic [31:0]     tm_hashes_completed_lifetime,
  output logic [31:0]     tm_valid_hashes_count,
  output logic [31:0]     tm_error_count,
  output logic [31:0]     tm_pipeline_stalls,
  output logic [$clog2(NUM_CORES+1)-1:0] tm_active_core_count,
  output logic [31:0]     tm_temperature_proxy,
  output logic [31:0]     tm_power_proxy
);

  logic          arr_job_valid, arr_stop, arr_any_busy, arr_found, arr_search_exhausted;
  logic [511:0]  arr_header_block1;
  logic [95:0]   arr_header_tail3;
  logic [31:0]   arr_nonce_start, arr_nonce_stride, arr_found_nonce, arr_found_core_id;
  logic [255:0]  arr_target, arr_found_hash;
  logic [31:0]   arr_total_hashes_completed;
  logic [NUM_CORES-1:0] arr_core_active_vec;

  miner_controller #(.NUM_CORES(NUM_CORES)) u_ctrl (
    .clk(clk), .rst_n(rst_n),
    .header_valid(header_valid), .header_ready(header_ready), .header_data(header_data),
    .start(start), .stop(stop),
    .nonce_start_cfg(nonce_start_cfg), .nonce_stride_cfg(nonce_stride_cfg),
    .busy(busy), .found(found), .found_nonce(found_nonce), .found_hash(found_hash),
    .found_core_id(found_core_id), .exhausted(exhausted), .error(error), .error_code(error_code),
    .state_out(state_out),
    .arr_job_valid(arr_job_valid), .arr_header_block1(arr_header_block1),
    .arr_header_tail3(arr_header_tail3), .arr_nonce_start(arr_nonce_start),
    .arr_nonce_stride(arr_nonce_stride), .arr_target(arr_target), .arr_stop(arr_stop),
    .arr_any_busy(arr_any_busy), .arr_found(arr_found), .arr_found_nonce(arr_found_nonce),
    .arr_found_hash(arr_found_hash), .arr_found_core_id(arr_found_core_id),
    .arr_search_exhausted(arr_search_exhausted)
  );

  hash_core_array #(.NUM_CORES(NUM_CORES)) u_array (
    .clk(clk), .rst_n(rst_n),
    .job_valid(arr_job_valid), .header_block1(arr_header_block1), .header_tail3(arr_header_tail3),
    .nonce_start(arr_nonce_start), .nonce_stride(arr_nonce_stride), .target(arr_target),
    .midstate_valid(1'b0), .midstate_load(256'h0),  // top-level always computes its own midstate; direct injection is a hash_core_array-level capability for lower-level testbenches
    .stop(arr_stop),
    .any_busy(arr_any_busy), .found(arr_found), .found_nonce(arr_found_nonce),
    .found_hash(arr_found_hash), .found_core_id(arr_found_core_id),
    .search_exhausted(arr_search_exhausted),
    .total_hashes_completed(arr_total_hashes_completed), .core_active_vec(arr_core_active_vec)
  );

  generate
    if (ENABLE_TELEMETRY) begin : g_telemetry
      telemetry #(.NUM_CORES(NUM_CORES), .COUNTER_WIDTH(32)) u_telem (
        .clk(clk), .rst_n(rst_n), .enable(1'b1),
        .core_active_vec(arr_core_active_vec),
        .job_valid(arr_job_valid), .any_busy(arr_any_busy),
        .job_done_pulse(arr_found || arr_search_exhausted),
        .job_hash_count(arr_total_hashes_completed),
        .valid_hash_event(found), .error_event(error),
        .clock_cycles(tm_clock_cycles),
        .hashes_completed_lifetime(tm_hashes_completed_lifetime),
        .valid_hashes_count(tm_valid_hashes_count),
        .error_count(tm_error_count),
        .pipeline_stalls(tm_pipeline_stalls),
        .active_core_count(tm_active_core_count),
        .temperature_proxy(tm_temperature_proxy),
        .power_proxy(tm_power_proxy)
      );
    end else begin : g_no_telemetry
      assign tm_clock_cycles              = '0;
      assign tm_hashes_completed_lifetime = '0;
      assign tm_valid_hashes_count        = '0;
      assign tm_error_count               = '0;
      assign tm_pipeline_stalls           = '0;
      assign tm_active_core_count         = '0;
      assign tm_temperature_proxy         = '0;
      assign tm_power_proxy               = '0;
    end
  endgenerate

endmodule : miner_top
