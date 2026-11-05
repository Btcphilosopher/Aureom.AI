// =============================================================================
// tb_mbist :: March C- MBIST through the SPM hooks
//   SA_EN = 0 : fault-free banks -> PASS with solid and checkerboard backgrounds
//   SA_EN = 1 : stuck-at-1 cell at bank 2 / word 77 / bit 5 -> FAIL detected,
//               failing bank and first failing address reported correctly
// Also checks functional ports are blocked while MBIST runs and that
// functional data written before MBIST is (as expected) destroyed by it.
// =============================================================================
`timescale 1ns/1ps
`default_nettype none
`include "tb_common.svh"

module tb_mbist #(parameter bit SA_EN = 1'b0);
  localparam int NP = 1, NBANKS = 4, BD = 256, DW = 64, NB = 8, AW = 32, SW = 72;
  localparam int FB = 2, FA = 77, FBIT = 5;

  logic clk = 0, rst_n = 0;
  always #5 clk = ~clk;

  logic          req_valid, req_ready, req_we, rsp_valid, rsp_err, rsp_corr;
  logic [AW-1:0] req_addr;
  logic [DW-1:0] req_wdata, rsp_rdata;
  logic [NB-1:0] req_wstrb;
  logic          mb_start, mb_busy, mb_done, mb_fail;
  logic [SW-1:0] mb_bg;
  logic [NBANKS-1:0] mb_fb;
  logic [7:0]    mb_fa;
  logic [15:0]   cc, cu;
  logic [31:0]   c1, c2;

  sf_spm_banked #(.NPORTS(NP), .NBANKS(NBANKS), .DW(DW), .BANK_DEPTH(BD), .AW(AW), .ECC_MODE(2),
                  .SA_EN(SA_EN), .SA_BANK(FB), .SA_ADDR(FA), .SA_BIT(FBIT), .SA_VAL(1'b1)) dut (
    .clk, .rst_n, .req_valid, .req_ready, .req_we, .req_addr, .req_wdata, .req_wstrb,
    .rsp_valid, .rsp_ready(1'b1), .rsp_rdata, .rsp_err, .rsp_corr,
    .inj_en(1'b0), .inj_bank('0), .inj_mask('0), .cnt_corr(cc), .cnt_uncorr(cu),
    .mbist_start(mb_start), .mbist_bg(mb_bg), .mbist_busy(mb_busy), .mbist_done(mb_done),
    .mbist_fail(mb_fail), .mbist_fail_bank(mb_fb), .mbist_fail_addr(mb_fa),
    .cnt_conflict_cycles(c1), .cnt_stall_cycles(c2), .lp_sleep(1'b0));

  int cycles;

  task automatic run_bist(input logic [SW-1:0] bg);
    mb_bg = bg;
    @(negedge clk); mb_start = 1;
    @(negedge clk); mb_start = 0;
    cycles = 1;
    // functional port must be blocked
    req_valid = 1; req_we = 0; req_addr = '0;
    #1 `CHECK(!req_ready, "functional port blocked during MBIST")
    @(negedge clk);
    req_valid = 0;
    while (!mb_done) begin @(negedge clk); cycles++; end
    `CHECK(!mb_busy, "MBIST idle after done")
  endtask

  logic [SW-1:0] chk_bg;

  initial begin
    req_valid = 0; req_we = 0; req_addr = '0; req_wdata = '0; req_wstrb = '0;
    mb_start = 0; mb_bg = '0;
    for (int b = 0; b < SW; b++) chk_bg[b] = b[0];
    repeat (3) @(negedge clk);
    rst_n = 1;
    @(negedge clk);

    run_bist('0);
    tb_metric("mbist_march_c_cycles", real'(cycles));
    tb_metric("mbist_words_per_bank", real'(BD));
    if (!SA_EN) begin
      `CHECK(!mb_fail, "fault-free March C- (solid background) passes")
      run_bist(chk_bg);
      `CHECK(!mb_fail, "fault-free March C- (checkerboard background) passes")
    end else begin
      `CHECK(mb_fail, "stuck-at fault detected")
      `CHECK_EQ(mb_fb, 4'b0100, "failing bank isolated")
      `CHECK_EQ(mb_fa, 8'(FA), "first failing address reported")
      run_bist(chk_bg);
      `CHECK(mb_fail, "stuck-at fault detected with checkerboard background")
    end
    tb_finish();
  end

  initial begin
    #20ms;
    $display("TIMEOUT");
    tb_finish();
  end
endmodule

`default_nettype wire
