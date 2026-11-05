// =============================================================================
// tb_deadlock :: joined-stream producer/consumer deadlock experiment
// Vector ADD of 1024 int16 (256 beats) with BOTH operand channels started at
// once, DMA burst = 16 beats.  The DMA write side serves bursts in order; the
// vector unit consumes only when A and B are both present.
//   VEC_IN_FIFO >= 16 : an A burst fits in the A FIFO, the B burst follows
//                       -> completes (MF_RESULT PASS)
//   VEC_IN_FIFO  = 4  : the DMA blocks mid A-burst on a full A FIFO while the
//                       B burst waits behind it -> no progress
//                       -> watchdog reports MF_RESULT DEADLOCK
// The Python model memoryflow.models.dataflow.joined_stream_deadlock() states
// the same condition analytically (FIFO depth < burst length).
// =============================================================================
`timescale 1ns/1ps
`default_nettype none
`include "tb_common.svh"

module tb_deadlock #(parameter int VEC_IN_FIFO = 16);
  localparam int VEC_IN_FIFO_P = VEC_IN_FIFO;
  `include "tb_system_common.svh"

  logic [31:0] rd32, st, b0, b1, b2, pb0, pb1, pb2;
  int          stuck;

  initial begin
    psel = 0; penable = 0; pwrite = 0; paddr = '0; pwdata = '0;
    h_req_valid = 0; h_req_we = 0; h_req_addr = '0; h_req_wdata = '0; h_req_wstrb = '0;
    repeat (3) @(negedge clk);
    rst_n = 1;
    @(negedge clk);
    for (int i = 0; i < 256; i++) begin
      host_write64(32'h0000 + 8 * i, {$urandom(), $urandom()});
      host_write64(32'h1000 + 8 * i, {$urandom(), $urandom()});
    end
    apb_write(CTL + 13'h004, 32'd0);                       // ADD
    dma_setup(2, 32'h0, 32'h2000, 32'd2048);
    dma_setup(0, 32'h0000, 32'h0, 32'd2048);
    dma_setup(1, 32'h1000, 32'h0, 32'd2048);
    apb_write(creg(2, 0), C_START | C_SSTR | c_sport(0) | c_burst(4));
    apb_write(creg(0, 0), C_START | C_DSTR | c_dport(0) | c_burst(4));
    apb_write(creg(1, 0), C_START | C_DSTR | c_dport(1) | c_burst(4));
    stuck = 0;
    pb0 = '1; pb1 = '1; pb2 = '1;
    forever begin
      repeat (50) @(negedge clk);
      apb_read(creg(0, 8'h20), b0);
      apb_read(creg(1, 8'h20), b1);
      apb_read(creg(2, 8'h20), b2);
      apb_read(creg(2, 8'h04), st);
      if (!st[0]) break;                                   // result channel finished
      if (b0 == pb0 && b1 == pb1 && b2 == pb2) stuck++; else stuck = 0;
      pb0 = b0; pb1 = b1; pb2 = b2;
      if (stuck >= 20) break;                              // 1000+ cycles, no beat moved
    end
    tb_metric("deadlock_vec_in_fifo", real'(VEC_IN_FIFO));
    tb_metric("deadlock_dma_burst_beats", 16.0);
    tb_metric("deadlock_beats_a", real'(b0));
    tb_metric("deadlock_beats_b", real'(b1));
    tb_metric("deadlock_beats_result", real'(b2));
    if (stuck >= 20) begin
      $display("watchdog: no DMA progress for >=1000 cycles (A=%0d B=%0d R=%0d beats)", b0, b1, b2);
      $display("MF_RESULT DEADLOCK errors=0 checks=%0d", tb_checks);
      $finish;
    end else begin
      `CHECK_EQ(b2, 32'd256, "all 256 result beats delivered")
      tb_finish();
    end
  end

  initial begin
    #200ms;
    $display("TIMEOUT");
    tb_finish();
  end
endmodule

`default_nettype wire
