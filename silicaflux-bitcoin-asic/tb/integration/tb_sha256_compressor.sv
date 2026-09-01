// tb_sha256_compressor.sv -- integration test for the ITERATIVE core
// (sha256_compressor.sv) against `COMPRESSOR_N` single-block compression
// steps from the Python golden model: known-answer vectors (empty,
// "abc", the NIST 2-block vector, a Bitcoin genesis-header-shaped
// 2-block message) plus randomised messages of 1..4 blocks. Multi-block
// messages exercise state_in continuation from a previous block's
// state_out, not just a fresh H0 start -- i.e. exactly the mechanism
// hash_core.sv will later use for midstate continuation.
`timescale 1ns/1ps
`include "tb/vectors/vector_counts.svh"

module tb_sha256_compressor;
  localparam int N = `COMPRESSOR_N;

  logic [255:0] state_in  [0:N-1];
  logic [511:0] block_in  [0:N-1];
  logic [255:0] state_exp [0:N-1];

  logic         clk, rst_n, start, busy, done;
  logic [255:0] state_in_p, state_out;
  logic [511:0] block_p;

  sha256_compressor dut (
    .clk(clk), .rst_n(rst_n), .start(start),
    .state_in(state_in_p), .block_bits(block_p),
    .busy(busy), .done(done), .state_out(state_out)
  );

  always #5 clk = ~clk;

  int errors;

  initial begin
    $readmemh("tb/vectors/compressor_state_in.hex", state_in);
    $readmemh("tb/vectors/compressor_block.hex", block_in);
    $readmemh("tb/vectors/compressor_state_out.hex", state_exp);

    clk = 0; rst_n = 0; start = 0; state_in_p = '0; block_p = '0;
    errors = 0;
    @(negedge clk); rst_n = 1;

    for (int i = 0; i < N; i++) begin
      state_in_p = state_in[i];
      block_p    = block_in[i];
      @(negedge clk);
      start = 1;
      @(negedge clk);
      start = 0;
      // done pulses after exactly 64 more cycles (round_cnt 0..63).
      wait (done === 1'b1);
      if (state_out !== state_exp[i]) begin
        errors++;
        $display("[FAIL] compressor case %0d: got=%064h want=%064h", i, state_out, state_exp[i]);
      end
      @(negedge clk);  // let done deassert before the next start
    end

    if (errors == 0)
      $display("[PASS] tb_sha256_compressor: %0d single-block compressions all matched", N);
    else
      $display("[FAIL] tb_sha256_compressor: %0d/%0d cases failed", errors, N);
    $finish;
  end

  // Safety timeout in case `done` never asserts (e.g. a hang bug). Scaled
  // to N: each case is ~66 cycles (~660ns) plus load/settle overhead: 4us
  // budget per case comfortably covers that with headroom, so a genuine
  // hang still gets caught well before this fires for any realistic N.
  initial begin
    #(N * 4_000 + 100_000);
    $display("[FAIL] tb_sha256_compressor: TIMEOUT waiting for done");
    $finish;
  end
endmodule : tb_sha256_compressor
