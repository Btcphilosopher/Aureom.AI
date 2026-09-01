// tb_sha256_schedule_step.sv -- chains 64 sha256_schedule_step instances
// purely combinationally and checks against the SAME schedule vectors as
// tb_sha256_message_schedule.sv, proving the combinational building
// block used by sha256_pipeline.sv agrees with the registered
// SLIDING_WINDOW implementation used by sha256_compressor.sv.
`timescale 1ns/1ps
`include "tb/vectors/vector_counts.svh"

module tb_sha256_schedule_step;
  localparam int NB = `SCHEDULE_NBLOCKS;

  logic [31:0] blocks_flat   [0:NB*16-1];
  logic [31:0] expected_flat [0:NB*64-1];

  logic [511:0] window_c [0:64];
  logic [31:0]  w_out_c  [0:63];

  // window_c[0] is driven procedurally (below) while window_c[1:64] are
  // driven by continuous port connections from the generate chain --
  // Icarus does not allow mixing procedural and port-driven assignment
  // within elements of the same array, so index 0 goes through a
  // separate reg + continuous assign.
  logic [511:0] window0_reg;
  assign window_c[0] = window0_reg;

  genvar gk;
  generate
    for (gk = 0; gk < 64; gk++) begin : g_chain
      sha256_schedule_step u_step (
        .window_in(window_c[gk]), .t_in(6'(gk)),
        .w_out(w_out_c[gk]), .window_out(window_c[gk+1]), .t_out()
      );
    end
  endgenerate

  int errors;

  initial begin
    $readmemh("tb/vectors/schedule_blocks.hex", blocks_flat);
    $readmemh("tb/vectors/schedule_expected.hex", expected_flat);

    errors = 0;
    for (int blk = 0; blk < NB; blk++) begin
      for (int i = 0; i < 16; i++) window0_reg[511 - 32*i -: 32] = blocks_flat[blk*16 + i];
      #1;
      for (int t = 0; t < 64; t++) begin
        if (w_out_c[t] !== expected_flat[blk*64 + t]) begin
          errors++;
          $display("[FAIL] schedule_step block %0d round %0d: got=%08h want=%08h",
                    blk, t, w_out_c[t], expected_flat[blk*64 + t]);
        end
      end
    end

    if (errors == 0)
      $display("[PASS] tb_sha256_schedule_step: %0d blocks, %0d checks all matched (combinational chain)", NB, NB*64);
    else
      $display("[FAIL] tb_sha256_schedule_step: %0d/%0d checks failed", errors, NB*64);
    $finish;
  end
endmodule : tb_sha256_schedule_step
