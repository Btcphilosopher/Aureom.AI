// tb_hash_core_array.sv -- system-level test for hash_core_array.sv:
// NUM_CORES cores searching in true (lockstep) parallel against a real,
// small target. The expected winner (core id, nonce, hash, and total
// system-wide hash count at the moment of the win) is computed directly
// by the Python golden model simulating every core's own nonce sequence
// -- see generate_vectors.py:gen_hash_core_array_vectors -- not assumed.
`timescale 1ns/1ps
`include "tb/vectors/hca_scenario.svh"

module tb_hash_core_array;
  localparam int NUM_CORES = `HCA_NUM_CORES;

  logic          clk, rst_n, job_valid, stop;
  logic [511:0]  header_block1;
  logic [95:0]   header_tail3;
  logic [31:0]   nonce_start, nonce_stride;
  logic [255:0]  target;
  logic          midstate_valid;
  logic [255:0]  midstate_load;

  logic          any_busy, found, search_exhausted;
  logic [31:0]   found_nonce, found_core_id, total_hashes_completed;
  logic [255:0]  found_hash;
  logic [NUM_CORES-1:0] core_active_vec;

  hash_core_array #(.NUM_CORES(NUM_CORES)) dut (
    .clk(clk), .rst_n(rst_n),
    .job_valid(job_valid), .header_block1(header_block1), .header_tail3(header_tail3),
    .nonce_start(nonce_start), .nonce_stride(nonce_stride), .target(target),
    .midstate_valid(midstate_valid), .midstate_load(midstate_load), .stop(stop),
    .any_busy(any_busy), .found(found), .found_nonce(found_nonce), .found_hash(found_hash),
    .found_core_id(found_core_id), .search_exhausted(search_exhausted),
    .total_hashes_completed(total_hashes_completed),
    .core_active_vec(core_active_vec)
  );

  always #5 clk = ~clk;

  int errors;

  initial begin
    clk = 0; rst_n = 0; job_valid = 0; stop = 0;
    header_block1 = `HCA_BLOCK1; header_tail3 = `HCA_TAIL3;
    nonce_start = `HCA_NONCE_START; nonce_stride = `HCA_NONCE_STRIDE;
    target = `HCA_TARGET; midstate_valid = 0; midstate_load = '0;
    errors = 0;

    @(negedge clk); rst_n = 1;
    @(negedge clk);
    job_valid = 1;
    @(negedge clk);
    job_valid = 0;

    wait (found === 1'b1);
    @(negedge clk);  // let total_hashes_completed's registered update settle

    if (found_core_id !== `HCA_FOUND_CORE_ID) begin
      errors++;
      $display("[FAIL] found_core_id=%0d want=%0d", found_core_id, `HCA_FOUND_CORE_ID);
    end
    if (found_nonce !== `HCA_FOUND_NONCE) begin
      errors++;
      $display("[FAIL] found_nonce=%08h want=%08h", found_nonce, `HCA_FOUND_NONCE);
    end
    if (found_hash !== `HCA_FOUND_HASH) begin
      errors++;
      $display("[FAIL] found_hash=%064h want=%064h", found_hash, `HCA_FOUND_HASH);
    end
    if (total_hashes_completed !== `HCA_EXPECTED_HASHES_COMPLETED) begin
      errors++;
      $display("[FAIL] total_hashes_completed=%0d want=%0d", total_hashes_completed, `HCA_EXPECTED_HASHES_COMPLETED);
    end

    // Every core should have stopped (no longer busy) shortly after the win.
    repeat (4) @(negedge clk);
    if (any_busy !== 1'b0) begin
      errors++;
      $display("[FAIL] any_busy still 1 after the array reported found -- a core failed to stop");
    end

    // Second job on the same array: an unreachable target (0) over a
    // small, fully-exhaustible nonce range (nonce_stride large enough
    // that NUM_CORES*stride overflows the 32-bit nonce space in only a
    // few trials) -- exercises search_exhausted (section 34) without a
    // false found.
    @(negedge clk);
    nonce_start  = 32'hFFFF_0000;
    nonce_stride = 32'h1000_0000;  // core_nonce_step = NUM_CORES*stride overflows fast
    target       = 256'h0;
    job_valid    = 1;
    @(negedge clk);
    job_valid = 0;
    wait (search_exhausted === 1'b1 || found === 1'b1);
    if (found) begin
      errors++;
      $display("[FAIL] search_exhausted case: unexpectedly reported found against an unreachable target");
    end else begin
      $display("[INFO] search_exhausted case: array correctly reported exhaustion, no false match");
    end

    if (errors == 0)
      $display("[PASS] tb_hash_core_array(NUM_CORES=%0d): correct winning core/nonce/hash, correct total_hashes_completed=%0d, all cores stopped, search_exhausted correct",
                NUM_CORES, total_hashes_completed);
    else
      $display("[FAIL] tb_hash_core_array: %0d errors", errors);
    $finish;
  end

  initial begin
    #100_000_000;
    $display("[FAIL] tb_hash_core_array: TIMEOUT");
    $finish;
  end
endmodule : tb_hash_core_array
