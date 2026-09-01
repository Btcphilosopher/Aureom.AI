// tb_sha256_message_schedule.sv -- self-checking unit testbench for the
// SLIDING_WINDOW message schedule (sha256_message_schedule.sv). For each
// of `SCHEDULE_NBLOCKS` random 16-word blocks, loads the block then
// walks all 64 rounds via `advance`, checking w_t against the Python
// golden model's message_schedule() at every single round -- not just
// the final word -- so a bug in any one round is caught precisely.
`timescale 1ns/1ps
`include "tb/vectors/vector_counts.svh"

module tb_sha256_message_schedule;
  localparam int NB = `SCHEDULE_NBLOCKS;

  logic [31:0] blocks_flat   [0:NB*16-1];
  logic [31:0] expected_flat [0:NB*64-1];

  logic         clk, rst_n, load, advance;
  logic [511:0] block_bits;
  logic [31:0]  w_t;
  logic [5:0]   t_q;

  sha256_message_schedule dut (
    .clk(clk), .rst_n(rst_n), .load(load),
    .block_bits(block_bits), .advance(advance),
    .w_t(w_t), .t_q(t_q)
  );

  always #5 clk = ~clk;

  int errors;
  int checks;

  initial begin
    $readmemh("tb/vectors/schedule_blocks.hex", blocks_flat);
    $readmemh("tb/vectors/schedule_expected.hex", expected_flat);

    clk = 0; rst_n = 0; load = 0; advance = 0;
    errors = 0; checks = 0;
    block_bits = '0;

    @(negedge clk); rst_n = 1;

    for (int blk = 0; blk < NB; blk++) begin
      for (int i = 0; i < 16; i++) block_bits[511 - 32*i -: 32] = blocks_flat[blk*16 + i];
      @(negedge clk);
      load = 1;
      @(negedge clk);
      load = 0;
      // After the load edge, w_t/t_q reflect round 0 immediately (combinational read of w_mem).
      for (int t = 0; t < 64; t++) begin
        checks++;
        if (w_t !== expected_flat[blk*64 + t] || t_q !== t[5:0]) begin
          errors++;
          $display("[FAIL] schedule block %0d round %0d: t_q=%0d w_t=%08h want=%08h",
                    blk, t, t_q, w_t, expected_flat[blk*64 + t]);
        end
        advance = 1;
        @(negedge clk);
        advance = 0;
      end
    end

    if (errors == 0)
      $display("[PASS] tb_sha256_message_schedule: %0d blocks, %0d round-checks all matched", NB, checks);
    else
      $display("[FAIL] tb_sha256_message_schedule: %0d/%0d round-checks failed", errors, checks);
    $finish;
  end
endmodule : tb_sha256_message_schedule
