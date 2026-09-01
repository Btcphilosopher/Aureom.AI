// tb_hash_core.sv -- integration test for hash_core.sv: real nonce
// searches against a genuinely small (not fabricated) target, alternating
// between the internal-midstate-computation path (use_midstate=0) and
// the direct midstate-injection path (use_midstate=1, section 14),
// checking that the core reports a miss on every trial before the true
// first match and a hit -- with the exact right nonce, hash, and trial
// count -- at the real first match (see generate_vectors.py:
// gen_hash_core_vectors for how "real first match" is established).
// Also exercises nonce_exhausted (section 34) with a directed overflow case.
`timescale 1ns/1ps
`include "tb/vectors/vector_counts.svh"

module tb_hash_core;
  localparam int N = `HASH_CORE_N;

  logic [511:0] block1_v      [0:N-1];
  logic [95:0]  tail3_v       [0:N-1];
  logic [31:0]  nonce_init_v  [0:N-1];
  logic [31:0]  nonce_step_v  [0:N-1];
  logic [255:0] target_v      [0:N-1];
  logic [31:0]  found_nonce_v [0:N-1];
  logic [255:0] found_hash_v  [0:N-1];
  logic [31:0]  trials_v      [0:N-1];
  logic [255:0] midstate_v    [0:N-1];
  logic         use_ms_v      [0:N-1];

  logic         clk, rst_n;
  logic         job_valid;
  logic [511:0] header_block1;
  logic [95:0]  header_tail3;
  logic [31:0]  nonce_init, nonce_step;
  logic [255:0] target;
  logic         midstate_valid;
  logic [255:0] midstate_load;
  logic         stop;
  logic         busy, found, nonce_exhausted;
  logic [31:0]  found_nonce, hashes_completed;
  logic [255:0] found_hash;
  logic         core_active;

  hash_core dut (
    .clk(clk), .rst_n(rst_n),
    .job_valid(job_valid), .header_block1(header_block1), .header_tail3(header_tail3),
    .nonce_init(nonce_init), .nonce_step(nonce_step), .target(target),
    .midstate_valid(midstate_valid), .midstate_load(midstate_load),
    .stop(stop),
    .busy(busy), .found(found), .found_nonce(found_nonce), .found_hash(found_hash),
    .nonce_exhausted(nonce_exhausted),
    .hashes_completed(hashes_completed), .core_active(core_active)
  );

  always #5 clk = ~clk;

  int errors;

  initial begin
    $readmemh("tb/vectors/hc_block1.hex", block1_v);
    $readmemh("tb/vectors/hc_tail3.hex", tail3_v);
    $readmemh("tb/vectors/hc_nonce_init.hex", nonce_init_v);
    $readmemh("tb/vectors/hc_nonce_step.hex", nonce_step_v);
    $readmemh("tb/vectors/hc_target.hex", target_v);
    $readmemh("tb/vectors/hc_found_nonce.hex", found_nonce_v);
    $readmemh("tb/vectors/hc_found_hash.hex", found_hash_v);
    $readmemh("tb/vectors/hc_trials_to_find.hex", trials_v);
    $readmemh("tb/vectors/hc_midstate.hex", midstate_v);
    $readmemh("tb/vectors/hc_use_midstate.hex", use_ms_v);

    clk = 0; rst_n = 0; job_valid = 0; stop = 0;
    header_block1 = '0; header_tail3 = '0; nonce_init = '0; nonce_step = '0;
    target = '0; midstate_valid = 0; midstate_load = '0;
    errors = 0;
    @(negedge clk); rst_n = 1;

    for (int i = 0; i < N; i++) begin
      @(negedge clk);
      header_block1  = block1_v[i];
      header_tail3   = tail3_v[i];
      nonce_init     = nonce_init_v[i];
      nonce_step     = nonce_step_v[i];
      target         = target_v[i];
      midstate_valid = use_ms_v[i];
      midstate_load  = use_ms_v[i] ? midstate_v[i] : 256'h0;
      job_valid      = 1'b1;
      @(negedge clk);
      job_valid      = 1'b0;

      wait (found === 1'b1);
      if (found_nonce !== found_nonce_v[i]) begin
        errors++;
        $display("[FAIL] hash_core case %0d: found_nonce=%08h want=%08h", i, found_nonce, found_nonce_v[i]);
      end
      if (found_hash !== found_hash_v[i]) begin
        errors++;
        $display("[FAIL] hash_core case %0d: found_hash=%064h want=%064h", i, found_hash, found_hash_v[i]);
      end
      if (hashes_completed !== trials_v[i]) begin
        errors++;
        $display("[FAIL] hash_core case %0d: hashes_completed=%0d want=%0d", i, hashes_completed, trials_v[i]);
      end
      @(negedge clk);
    end

    // Directed nonce_exhausted case: nonce_init near the top of the 32-bit
    // range with an unreachable target, so the core must overflow and
    // report nonce_exhausted rather than hang or silently wrap forever.
    @(negedge clk);
    header_block1  = block1_v[0];
    header_tail3   = tail3_v[0];
    nonce_init     = 32'hFFFF_FFF0;
    nonce_step     = 32'd1;
    target         = 256'h0;  // unreachable: nothing meets target 0 except a hash of exactly 0
    midstate_valid = 1'b0;
    job_valid      = 1'b1;
    @(negedge clk);
    job_valid = 1'b0;
    wait (nonce_exhausted === 1'b1 || found === 1'b1);
    if (found) begin
      errors++;
      $display("[FAIL] nonce_exhausted case: unexpectedly reported found");
    end else begin
      $display("[INFO] nonce_exhausted case: correctly overflowed without a false match");
    end

    if (errors == 0)
      $display("[PASS] tb_hash_core: %0d nonce-search scenarios + nonce_exhausted case all correct", N);
    else
      $display("[FAIL] tb_hash_core: %0d errors", errors);
    $finish;
  end

  initial begin
    #50_000_000;
    $display("[FAIL] tb_hash_core: TIMEOUT");
    $finish;
  end
endmodule : tb_hash_core
