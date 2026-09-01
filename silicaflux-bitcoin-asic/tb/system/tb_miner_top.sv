// tb_miner_top.sv -- full end-to-end system test of miner_top.sv via its
// external header-loading interface only (section 12/42/45):
//   1. Load a real header (real nBits -> miner_controller's own
//      nbits_expand path, not a pre-supplied target), start the search,
//      and check the exact winning core/nonce/hash against the Python
//      golden model (section 42's synthetic "artificially easy target"
//      demonstration, run for real).
//   2. An invalid-target (bits=0) header correctly enters ERROR with the
//      documented error_code, and recovers cleanly on the next header
//      (section 34).
//   3. Reset asserted mid-search returns the FSM to a clean IDLE able to
//      accept a new header afterward (section 45 checklist item 9,
//      "test pipeline reset").
`timescale 1ns/1ps
`include "tb/vectors/miner_top_scenario.svh"

module tb_miner_top;
  localparam int NUM_CORES = `MTOP_NUM_CORES;

  logic         clk, rst_n;
  logic          header_valid, header_ready;
  logic [607:0]  header_data;
  logic          start, stop;
  logic [31:0]   nonce_start_cfg, nonce_stride_cfg;
  logic          busy, found, exhausted, error;
  logic [31:0]   found_nonce, found_core_id;
  logic [255:0]  found_hash;
  logic [3:0]    error_code, state_out;
  logic [31:0]   tm_clock_cycles, tm_hashes_completed_lifetime, tm_valid_hashes_count;
  logic [31:0]   tm_error_count, tm_pipeline_stalls, tm_temperature_proxy, tm_power_proxy;
  logic [$clog2(NUM_CORES+1)-1:0] tm_active_core_count;

  miner_top #(.NUM_CORES(NUM_CORES), .ENABLE_TELEMETRY(1)) dut (
    .clk(clk), .rst_n(rst_n),
    .header_valid(header_valid), .header_ready(header_ready), .header_data(header_data),
    .start(start), .stop(stop),
    .nonce_start_cfg(nonce_start_cfg), .nonce_stride_cfg(nonce_stride_cfg),
    .busy(busy), .found(found), .found_nonce(found_nonce), .found_hash(found_hash),
    .found_core_id(found_core_id), .exhausted(exhausted), .error(error), .error_code(error_code),
    .state_out(state_out),
    .tm_clock_cycles(tm_clock_cycles), .tm_hashes_completed_lifetime(tm_hashes_completed_lifetime),
    .tm_valid_hashes_count(tm_valid_hashes_count), .tm_error_count(tm_error_count),
    .tm_pipeline_stalls(tm_pipeline_stalls), .tm_active_core_count(tm_active_core_count),
    .tm_temperature_proxy(tm_temperature_proxy), .tm_power_proxy(tm_power_proxy)
  );

  miner_protocol_checker u_checker (
    .clk(clk), .rst_n(rst_n),
    .header_valid(header_valid), .header_ready(header_ready), .start(start),
    .busy(busy), .found(found), .error(error), .exhausted(exhausted), .state_out(state_out)
  );

  always #5 clk = ~clk;
  int errors;
  logic [607:0] bad_header;

  task automatic load_and_start(input logic [607:0] hdr, input logic [31:0] ns, input logic [31:0] nstr);
    wait (header_ready === 1'b1);
    @(negedge clk);
    header_data = hdr; nonce_start_cfg = ns; nonce_stride_cfg = nstr;
    header_valid = 1'b1;
    @(negedge clk);
    header_valid = 1'b0;
    // ARMED is reached a couple of cycles later; start can be asserted
    // any time from here (miner_controller waits for it in ST_ARMED).
    repeat (3) @(negedge clk);
    start = 1'b1;
    @(negedge clk);
    start = 1'b0;
  endtask

  initial begin
    clk = 0; rst_n = 0; header_valid = 0; header_data = '0; start = 0; stop = 0;
    nonce_start_cfg = '0; nonce_stride_cfg = '0;
    errors = 0;
    @(negedge clk); rst_n = 1;

    // --- Scenario 1: real end-to-end found ---
    load_and_start(`MTOP_HEADER_DATA, `MTOP_NONCE_START, `MTOP_NONCE_STRIDE);
    wait (found === 1'b1 || error === 1'b1);
    if (error) begin
      errors++;
      $display("[FAIL] scenario1: unexpected error_code=%0d", error_code);
    end else begin
      if (found_nonce !== `MTOP_FOUND_NONCE) begin errors++; $display("[FAIL] scenario1 found_nonce=%08h want=%08h", found_nonce, `MTOP_FOUND_NONCE); end
      if (found_hash  !== `MTOP_FOUND_HASH)  begin errors++; $display("[FAIL] scenario1 found_hash=%064h want=%064h", found_hash, `MTOP_FOUND_HASH); end
      if (found_core_id !== `MTOP_FOUND_CORE_ID) begin errors++; $display("[FAIL] scenario1 found_core_id=%0d want=%0d", found_core_id, `MTOP_FOUND_CORE_ID); end
      if (errors == 0) $display("[INFO] scenario1 (end-to-end found): PASS");
    end
    @(negedge clk);

    // --- Scenario 2: invalid target (bits=0) -> ERROR, then recovery ---
    bad_header = `MTOP_HEADER_DATA;
    bad_header[31:0] = 32'h0;  // zero out nBits -> nbits_expand produces target=0
    load_and_start(bad_header, `MTOP_NONCE_START, `MTOP_NONCE_STRIDE);
    wait (error === 1'b1 || found === 1'b1);
    if (!error || error_code !== 4'd1) begin
      errors++;
      $display("[FAIL] scenario2: expected error_code=1 (invalid target), got error=%0d error_code=%0d", error, error_code);
    end else begin
      $display("[INFO] scenario2 (invalid target -> ERROR): PASS, error_code=%0d", error_code);
    end
    // Recovery: a fresh, valid header should be accepted and searchable again.
    @(negedge clk);
    load_and_start(`MTOP_HEADER_DATA, `MTOP_NONCE_START, `MTOP_NONCE_STRIDE);
    wait (found === 1'b1 || error === 1'b1);
    if (error) begin
      errors++;
      $display("[FAIL] scenario2 recovery: still in error after loading a valid header");
    end else if (found_nonce !== `MTOP_FOUND_NONCE) begin
      errors++;
      $display("[FAIL] scenario2 recovery: found_nonce=%08h want=%08h", found_nonce, `MTOP_FOUND_NONCE);
    end else begin
      $display("[INFO] scenario2 recovery (ERROR -> valid header -> found): PASS");
    end
    @(negedge clk);

    // --- Scenario 3: reset asserted mid-search ---
    load_and_start(`MTOP_HEADER_DATA, `MTOP_NONCE_START, `MTOP_NONCE_STRIDE);
    repeat (20) @(negedge clk);  // let the search run partway (well before it would find, per scenario 1's known trial count)
    if (!busy) begin
      errors++;
      $display("[FAIL] scenario3: expected busy=1 mid-search before reset");
    end
    rst_n = 0;
    repeat (3) @(negedge clk);
    rst_n = 1;
    @(negedge clk);
    if (busy !== 1'b0 || state_out !== 4'd0 || header_ready !== 1'b1) begin
      errors++;
      $display("[FAIL] scenario3: not cleanly IDLE after reset (busy=%0d state_out=%0d header_ready=%0d)",
                busy, state_out, header_ready);
    end
    // Confirm the FSM is genuinely usable again post-reset.
    load_and_start(`MTOP_HEADER_DATA, `MTOP_NONCE_START, `MTOP_NONCE_STRIDE);
    wait (found === 1'b1 || error === 1'b1);
    if (error || found_nonce !== `MTOP_FOUND_NONCE) begin
      errors++;
      $display("[FAIL] scenario3: post-reset search did not reproduce the known result (error=%0d found_nonce=%08h)", error, found_nonce);
    end else begin
      $display("[INFO] scenario3 (mid-search reset -> clean recovery): PASS");
    end
    // Telemetry counters update one cycle after the event they count
    // (they sample already-registered signals like `found`, standard
    // synchronous-design latency -- see docs/architecture.md); give the
    // final summary a moment to settle so it reports real, current
    // values rather than a stale pre-update read. Also note scenario 3's
    // reset legitimately zeroed telemetry along with everything else, so
    // only the post-reset recovery's single `found` is reflected below.
    repeat (3) @(negedge clk);

    if (errors == 0)
      $display("[PASS] tb_miner_top: end-to-end found, ERROR handling + recovery, and mid-search reset all correct. telemetry: cycles=%0d lifetime_hashes=%0d valid_hashes=%0d error_count=%0d",
                tm_clock_cycles, tm_hashes_completed_lifetime, tm_valid_hashes_count, tm_error_count);
    else
      $display("[FAIL] tb_miner_top: %0d errors", errors);
    $finish;
  end

  initial begin
    #200_000_000;
    $display("[FAIL] tb_miner_top: TIMEOUT");
    $finish;
  end
endmodule : tb_miner_top
