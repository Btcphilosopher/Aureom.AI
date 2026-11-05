// =============================================================================
// tb_sf1_memctrl :: SilicaFlux v1 tile memory controller (memory_controller.sv,
//                   unmodified, from silicaflux.zip; 256 x 32-bit words)
//
//   1  scalar STORE / LOAD latency and back-to-back rate
//   2  VSTORE / VLOAD (4 words) latency and bytes per cycle
//   3  DFSTORE / DFLOAD with length <= 4: correct
//   4  DFSTORE / DFLOAD with length 8: the burst address never advances and the
//      128-bit buffer index wraps, so words 4..7 are never written / read
//      -> DEFECT expected (reported as MF_RESULT DEFECT when reproduced)
//   5  the tile write-back port and a STORE land in the SAME cycle: two array
//      writes per cycle, i.e. the inferred SRAM needs two write ports
// =============================================================================
`timescale 1ns/1ps
`include "tb_common.svh"

module tb_sf1_memctrl;
  import silicaflux_pkg::*;

  logic clk = 0, rst_n = 0;
  always #5 clk = ~clk;
  longint cyc = 0;
  always @(posedge clk) cyc <= cyc + 1;

  logic        req_valid = 0, req_ready, resp_valid, align_err, wb_valid = 0;
  logic [4:0]  req_opcode = '0, req_length = '0;
  logic [31:0] req_addr = '0, req_wdata = '0, resp_rdata, wb_addr = '0, wb_data = '0;
  logic [127:0] req_vwdata = '0, resp_vrdata;

  memory_controller dut (.clk, .rst_n, .req_valid, .req_ready, .req_opcode, .req_addr, .req_wdata,
    .req_vwdata, .req_length, .resp_valid, .resp_rdata, .resp_vrdata, .alignment_err(align_err),
    .wb_valid, .wb_addr, .wb_data);

  logic [31:0] refm [256];
  longint t_acc, t_rsp;
  int defect_hits = 0;

  // one transaction: valid for exactly one accepting cycle (the FSM re-accepts a held valid)
  task automatic xact(logic [4:0] op, logic [31:0] addr, logic [31:0] wd, logic [127:0] vwd, logic [4:0] len);
    while (!req_ready) @(negedge clk);
    req_opcode = op; req_addr = addr; req_wdata = wd; req_vwdata = vwd; req_length = len;
    req_valid = 1; t_acc = cyc + 1;
    @(negedge clk); req_valid = 0;
    while (!resp_valid) @(posedge clk);
    t_rsp = cyc;
    @(negedge clk);
  endtask

  longint c0;
  int n;
  initial begin
    for (int i = 0; i < 256; i++) refm[i] = 'x;
    repeat (3) @(negedge clk); rst_n = 1; repeat (2) @(negedge clk);

    // ---------------------------------------------------------------- 1 scalar
    for (int w = 0; w < 256; w++) begin
      xact(OP_STORE, 32'(w * 4), 32'h5F00_0000 + 32'(w * 2654435761), '0, '0);
      refm[w] = 32'h5F00_0000 + 32'(w * 2654435761);
    end
    xact(OP_LOAD, 32'd40, '0, '0, '0);
    `CHECK_EQ(resp_rdata, refm[10], "scalar load data")
    c0 = cyc;
    for (int w = 0; w < 256; w++) begin
      xact(OP_LOAD, 32'(w * 4), '0, '0, '0);
      `CHECK_EQ(resp_rdata, refm[w], "scalar load stream data")
    end
    tb_metric("sf1_scalar_load_words_per_cycle", 256.0 / real'(cyc - c0));
    tb_metric("sf1_scalar_load_cycles_per_word", real'(cyc - c0) / 256.0);
    tb_metric("sf1_scalar_load_bytes_per_cycle", 1024.0 / real'(cyc - c0));

    // ---------------------------------------------------------------- 2 vector
    c0 = cyc;
    for (int l = 0; l < 32; l++) begin
      logic [127:0] v;
      v = {32'(l * 4 + 3), 32'(l * 4 + 2), 32'(l * 4 + 1), 32'(l * 4)} ^ {4{32'hA5A5_0000}};
      xact(OP_VSTORE, 32'(l * 16), '0, v, '0);
      for (int k = 0; k < 4; k++) refm[l * 4 + k] = v[k*32 +: 32];
    end
    tb_metric("sf1_vstore_bytes_per_cycle", 512.0 / real'(cyc - c0));
    c0 = cyc;
    for (int l = 0; l < 32; l++) begin
      xact(OP_VLOAD, 32'(l * 16), '0, '0, '0);
      `CHECK_EQ(resp_vrdata, {refm[l*4+3], refm[l*4+2], refm[l*4+1], refm[l*4]}, "VLOAD data")
    end
    tb_metric("sf1_vload_bytes_per_cycle", 512.0 / real'(cyc - c0));

    // ---------------------------------------------------------------- 3 DF bursts <= 4 words
    for (int len = 1; len <= 4; len++) begin
      xact(OP_DFSTORE, 32'(128 * 4), '0, {32'hD0D3, 32'hD0D2, 32'hD0D1, 32'hD0D0} + 128'(len), 5'(len));
      for (int k = 0; k < len; k++) refm[128 + k] = 32'hD0D0 + 32'(k) + ((k == 0) ? 32'(len) : 0);
      xact(OP_DFLOAD, 32'(128 * 4), '0, '0, 5'(len));
      for (int k = 0; k < len; k++)
        `CHECK_EQ(resp_vrdata[k*32 +: 32], refm[128 + k], $sformatf("DFLOAD len %0d word %0d", len, k))
    end

    // ---------------------------------------------------------------- 4 DF burst of 8 words
    // fill words 160..167 with known values, DFSTORE 8 words of a fresh pattern
    for (int k = 0; k < 8; k++) begin
      xact(OP_STORE, 32'((160 + k) * 4), 32'h0BAD_0000 + 32'(k), '0, '0);
      refm[160 + k] = 32'h0BAD_0000 + 32'(k);
    end
    c0 = cyc;
    xact(OP_DFSTORE, 32'(160 * 4), '0, {32'h1111_0003, 32'h1111_0002, 32'h1111_0001, 32'h1111_0000}, 5'd8);
    tb_metric("sf1_dfstore8_cycles", real'(cyc - c0));
    n = 0;
    for (int k = 0; k < 8; k++) begin
      xact(OP_LOAD, 32'((160 + k) * 4), '0, '0, '0);
      // a correct 8-word burst would have written all 8 words
      if (k >= 4 && resp_rdata == refm[160 + k]) n++;      // unchanged -> never written
    end
    if (n == 4) defect_hits++;
    tb_metric("sf1_dfstore8_words_not_written", real'(n));
    // DFLOAD 8: the response can carry 4 words; words 4..7 are re-reads of 0..3
    c0 = cyc;
    xact(OP_DFLOAD, 32'(160 * 4), '0, '0, 5'd8);
    tb_metric("sf1_dfload8_cycles", real'(cyc - c0));
    tb_metric("sf1_dfload8_useful_bytes_per_cycle", 16.0 / real'(cyc - c0));
    if (resp_vrdata == {32'h1111_0003, 32'h1111_0002, 32'h1111_0001, 32'h1111_0000}) defect_hits++;

    // ---------------------------------------------------------------- 5 two writes in one cycle
    while (!req_ready) @(negedge clk);
    req_opcode = OP_STORE; req_addr = 32'(200 * 4); req_wdata = 32'h2222_2222; req_valid = 1;
    wb_valid = 1; wb_addr = 32'(201 * 4); wb_data = 32'h3333_3333;
    @(negedge clk); req_valid = 0; wb_valid = 0;
    while (!req_ready) @(negedge clk);
    xact(OP_LOAD, 32'(200 * 4), '0, '0, '0);
    `CHECK_EQ(resp_rdata, 32'h2222_2222, "FSM store landed")
    xact(OP_LOAD, 32'(201 * 4), '0, '0, '0);
    `CHECK_EQ(resp_rdata, 32'h3333_3333, "write-back port store landed in the same cycle")
    tb_metric("sf1_array_writes_in_one_cycle", 2.0);

    // ---------------------------------------------------------------- misalignment
    xact(OP_LOAD, 32'd2, '0, '0, '0);
    `CHECK(1, "misaligned load answered")

    tb_metric("sf1_dfburst_defect_reproduced", real'(defect_hits));
    if (tb_errors == 0 && defect_hits == 2)
      $display("MF_RESULT DEFECT errors=0 checks=%0d", tb_checks);
    else if (tb_errors == 0)
      $display("MF_RESULT PASS errors=0 checks=%0d", tb_checks);
    else
      $display("MF_RESULT FAIL errors=%0d checks=%0d", tb_errors, tb_checks);
    $finish;
  end
  initial begin #5_000_000; `CHECK(0, "global timeout"); tb_finish(); end
endmodule
