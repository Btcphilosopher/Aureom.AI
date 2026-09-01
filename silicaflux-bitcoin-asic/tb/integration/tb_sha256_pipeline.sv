// tb_sha256_pipeline.sv -- streaming integration test for sha256_pipeline.sv.
//
// Reuses the same COMPRESSOR_N single-block vectors as
// tb_sha256_compressor.sv (same {state_in, block, expected state_out}
// contract), but drives them as a true streaming pipeline: a new
// state_in/block presented every clock (valid_in=1 back-to-back), and
// results collected off valid_out/state_out in the same order, with no
// stalls. scripts/run_iverilog.sh runs this at every valid PIPELINE_DEPTH
// (1/2/4/8/16/32/64) via `-P` parameter override, to prove the
// parameterization is not just plausible RTL but actually produces
// correct results at every supported depth.
//
// NUM_CASES caps how many vectors are streamed. At PIPELINE_DEPTH in
// {8,16,32,64} the full COMPRESSOR_N set runs in a few seconds. At
// PIPELINE_DEPTH in {1,2,4} each stage is one giant *unregistered*
// combinational block spanning 16/32/64 chained rounds with zero
// intermediate flip-flops -- structurally valid and verilator-lint-clean
// (confirmed during bring-up), but Icarus Verilog's event-driven engine
// was observed to become impractically slow settling that much unbroken
// combinational logic at the full vector count (multi-minute runs where
// depths >=8 take seconds). A smaller NUM_CASES keeps those depths'
// verification runs practical while still exercising real, varied inputs
// (not just a single fixed vector) -- see reports/ for exactly which
// count each depth was actually run with.
`timescale 1ns/1ps
`include "tb/vectors/vector_counts.svh"

module tb_sha256_pipeline #(parameter int PIPELINE_DEPTH = 64, parameter int NUM_CASES = `COMPRESSOR_N);
  localparam int N = NUM_CASES;

  logic [255:0] state_in  [0:N-1];
  logic [511:0] block_in  [0:N-1];
  logic [255:0] state_exp [0:N-1];
  logic [255:0] collected [0:N-1];

  logic         clk, rst_n, valid_in, valid_out;
  logic [255:0] state_in_p, state_out;
  logic [511:0] block_p;

  sha256_pipeline #(.PIPELINE_DEPTH(PIPELINE_DEPTH)) dut (
    .clk(clk), .rst_n(rst_n),
    .valid_in(valid_in), .state_in(state_in_p), .block_bits(block_p),
    .valid_out(valid_out), .state_out(state_out)
  );

  always #5 clk = ~clk;

  int collect_count;
  int errors;

  // Collector: runs concurrently with the driver below, appending every
  // valid_out beat to `collected` in arrival order.
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      collect_count <= 0;
    end else if (valid_out) begin
      collected[collect_count] <= state_out;
      collect_count <= collect_count + 1;
    end
  end

  initial begin
    $readmemh("tb/vectors/compressor_state_in.hex", state_in);
    $readmemh("tb/vectors/compressor_block.hex", block_in);
    $readmemh("tb/vectors/compressor_state_out.hex", state_exp);

    clk = 0; rst_n = 0; valid_in = 0; state_in_p = '0; block_p = '0;
    errors = 0;
    @(negedge clk); rst_n = 1;

    // Drive all N inputs back-to-back, one per cycle (true pipeline: no stalls).
    for (int i = 0; i < N; i++) begin
      valid_in   = 1'b1;
      state_in_p = state_in[i];
      block_p    = block_in[i];
      @(negedge clk);
    end
    valid_in = 1'b0;

    // Drain: wait until the collector has seen all N results.
    wait (collect_count == N);
    @(negedge clk);

    for (int i = 0; i < N; i++) begin
      if (collected[i] !== state_exp[i]) begin
        errors++;
        $display("[FAIL] pipeline(depth=%0d) case %0d: got=%064h want=%064h",
                  PIPELINE_DEPTH, i, collected[i], state_exp[i]);
      end
    end

    if (errors == 0)
      $display("[PASS] tb_sha256_pipeline(PIPELINE_DEPTH=%0d): %0d streamed single-block compressions all matched, in order",
                PIPELINE_DEPTH, N);
    else
      $display("[FAIL] tb_sha256_pipeline(PIPELINE_DEPTH=%0d): %0d/%0d cases failed", PIPELINE_DEPTH, errors, N);
    $finish;
  end

  initial begin
    #2_000_000;
    $display("[FAIL] tb_sha256_pipeline(PIPELINE_DEPTH=%0d): TIMEOUT", PIPELINE_DEPTH);
    $finish;
  end
endmodule : tb_sha256_pipeline
