// =============================================================================
// tb_param_smoke :: functional smoke test of sf_memflow_top at an arbitrary
// parameterisation (default = the RECOMMENDED SilicaFlux-V prototype:
// 128-bit datapath, 8 banks x 1024 words (128 KiB), XOR interleave, 16x16
// tensor array, 8-lane vector unit, 64-deep DMA data FIFOs).
//  P1 host-port write/read of every SPM bank
//  P2 DMA SPM->SPM 2 KiB copy
//  P3 GEMM tile C(16x16) = A(16xK) * B(Kx16), K = 16, vs in-TB reference
//  P4 vector ADD (lanes = DW/16) vs in-TB reference
// References are computed in the testbench from the same random operands.
// =============================================================================
`timescale 1ns/1ps
`default_nettype none
`include "tb_common.svh"

module tb_param_smoke #(
  parameter int DW      = 128,
  parameter int NBANKS  = 8,
  parameter int BDEPTH  = 1024,
  parameter int ILV     = 1,
  parameter int TR      = 16,
  parameter int TC      = 16,
  parameter int DFIFO   = 64
);
  localparam int NB = DW / 8, AW = 32, K = 16;
  localparam int LANES = DW / 16;
  localparam int EPB = DW / 32, NOUT = TR * TC / EPB;
  localparam logic [12:0] DMA = 13'h0000, CTL = 13'h1000;

  logic clk = 0, rst_n = 0;
  always #5 clk = ~clk;
  longint cyc = 0;
  always @(posedge clk) cyc <= cyc + 1;

  logic        psel, penable, pwrite, pready, pslverr, irq;
  logic [12:0] paddr;
  logic [31:0] pwdata, prdata;
  logic          h_req_valid, h_req_ready, h_req_we, h_rsp_valid, h_rsp_err;
  logic [AW-1:0] h_req_addr;
  logic [DW-1:0] h_req_wdata, h_rsp_rdata;
  logic [NB-1:0] h_req_wstrb;
  logic          xr_req_valid, xr_rsp_ready, xw_req_valid, xw_rsp_ready;
  logic [AW-1:0] xr_req_addr, xw_req_addr;
  logic [DW-1:0] xw_req_wdata;
  logic [NB-1:0] xw_req_wstrb;

  sf_memflow_top #(.DW(DW), .SPM_NBANKS(NBANKS), .SPM_BANK_DEPTH(BDEPTH), .SPM_INTERLEAVE(ILV),
                   .TEN_TR(TR), .TEN_TC(TC), .DMA_DFIFO(DFIFO), .VEC_IN_FIFO(16), .TEN_IN_FIFO(16)) u_top (
    .clk, .rst_n, .psel, .penable, .pwrite, .paddr, .pwdata, .prdata, .pready, .pslverr, .irq,
    .h_req_valid, .h_req_ready, .h_req_we, .h_req_addr, .h_req_wdata, .h_req_wstrb,
    .h_rsp_valid, .h_rsp_ready(1'b1), .h_rsp_rdata, .h_rsp_err,
    .xr_req_valid, .xr_req_ready(1'b0), .xr_req_addr, .xr_rsp_valid(1'b0), .xr_rsp_ready,
    .xr_rsp_rdata('0), .xr_rsp_err(1'b0),
    .xw_req_valid, .xw_req_ready(1'b0), .xw_req_addr, .xw_req_wdata, .xw_req_wstrb,
    .xw_rsp_valid(1'b0), .xw_rsp_ready, .xw_rsp_err(1'b0));

  task automatic apb_write(input logic [12:0] a, input logic [31:0] d);
    psel = 1; penable = 0; pwrite = 1; paddr = a; pwdata = d;
    @(negedge clk); penable = 1;
    @(negedge clk); psel = 0; penable = 0; pwrite = 0;
  endtask
  task automatic apb_read(input logic [12:0] a, output logic [31:0] d);
    psel = 1; penable = 0; pwrite = 0; paddr = a;
    @(negedge clk); penable = 1;
    #1 d = prdata;
    @(negedge clk); psel = 0; penable = 0;
  endtask
  function automatic logic [12:0] creg(int ch, int off); return DMA + 13'(12'h100 + ch * 12'h40 + off); endfunction
  task automatic host_op(input bit we, input int a, input logic [DW-1:0] d, output logic [DW-1:0] q);
    bit acc;
    h_req_valid = 1; h_req_we = we; h_req_addr = AW'(a); h_req_wdata = d; h_req_wstrb = '1;
    acc = 0;
    while (!acc) begin #1 acc = h_req_ready; @(negedge clk); end
    h_req_valid = 0;
    while (!h_rsp_valid) @(negedge clk);
    q = h_rsp_rdata;
    @(negedge clk);
  endtask
  task automatic dma(int ch, int src, int dst, int len, logic [31:0] ctrl);
    apb_write(creg(ch, 8'h08), 32'(src)); apb_write(creg(ch, 8'h0C), 32'(dst));
    apb_write(creg(ch, 8'h10), 32'(len)); apb_write(creg(ch, 8'h14), 32'd1);
    apb_write(creg(ch, 0), ctrl);
  endtask
  task automatic dma_wait(int ch, string tag);
    logic [31:0] st; int n;
    n = 0;
    do begin apb_read(creg(ch, 8'h04), st); n++; end while (st[0] && n < 50000);
    `CHECK_EQ(st[2:0], 3'b010, $sformatf("%s: channel %0d DONE", tag, ch))
  endtask
  function automatic logic [DW-1:0] rnd();
    logic [DW-1:0] v;
    for (int i = 0; i < DW / 32; i++) v[i*32 +: 32] = $urandom();
    return v;
  endfunction

  localparam logic [31:0] C_START = 32'h1, C_SSTR = 32'h4, C_DSTR = 32'h8;
  logic [DW-1:0] a_beats [K], b_beats [K], q, va [32], vb [32];
  logic signed [31:0] cref [TR][TC];

  initial begin
    psel = 0; penable = 0; pwrite = 0; paddr = '0; pwdata = '0;
    h_req_valid = 0; h_req_we = 0; h_req_addr = '0; h_req_wdata = '0; h_req_wstrb = '0;
    repeat (3) @(negedge clk);
    rst_n = 1;
    @(negedge clk);
    tb_metric("param_dw", real'(DW));
    tb_metric("param_tensor_rows", real'(TR));

    // P1: one word per bank region
    for (int i = 0; i < 4 * NBANKS; i++) begin
      logic [DW-1:0] d;
      d = rnd();
      host_op(1, 32'h6000 + i * NB, d, q);
      host_op(0, 32'h6000 + i * NB, '0, q);
      `CHECK_EQ(q, d, "P1 host write/read")
    end

    // P2: SPM->SPM copy of 2 KiB (addresses fit the smallest 32 KiB SPM)
    begin
      logic [DW-1:0] src [256];
      for (int i = 0; i < 2048 / NB; i++) begin src[i] = rnd(); host_op(1, 32'h6800 + i * NB, src[i], q); end
      dma(0, 32'h6800, 32'h7000, 2048, C_START | (32'd4 << 4));
      dma_wait(0, "P2");
      for (int i = 0; i < 2048 / NB; i++) begin
        host_op(0, 32'h7000 + i * NB, '0, q);
        `CHECK_EQ(q, src[i], "P2 copy data")
      end
    end

    // P3: GEMM tile on the TR x TC array
    for (int k = 0; k < K; k++) begin
      a_beats[k] = rnd(); b_beats[k] = rnd();
      host_op(1, 32'h0000 + k * NB, a_beats[k], q);
      host_op(1, 32'h1000 + k * NB, b_beats[k], q);
    end
    for (int i = 0; i < TR; i++) for (int j = 0; j < TC; j++) begin
      cref[i][j] = 0;
      for (int k = 0; k < K; k++)
        cref[i][j] += 32'($signed(a_beats[k][i*8 +: 8])) * 32'($signed(b_beats[k][j*8 +: 8]));
    end
    apb_write(CTL + 13'h00C, 32'(K));
    apb_write(CTL + 13'h010, 32'd1);
    dma(2, 0, 32'h2000, TR * TC * 4, C_START | C_SSTR | (32'd1 << 12) | (32'd4 << 4));
    dma(1, 32'h1000, 0, K * NB, C_START | C_DSTR | (32'd3 << 16) | (32'd4 << 4));
    dma_wait(1, "P3 B");
    dma(0, 32'h0000, 0, K * NB, C_START | C_DSTR | (32'd2 << 16) | (32'd4 << 4));
    dma_wait(0, "P3 A");
    dma_wait(2, "P3 C");
    begin
      int bad; bad = 0;
      for (int n = 0; n < NOUT; n++) begin
        host_op(0, 32'h2000 + n * NB, '0, q);
        for (int e = 0; e < EPB; e++) begin
          int idx; idx = n * EPB + e;
          if ($signed(q[e*32 +: 32]) !== cref[idx / TC][idx % TC]) bad++;
        end
      end
      `CHECK(bad == 0, $sformatf("P3 %0dx%0d GEMM tile matches reference (%0d bad)", TR, TC, bad))
    end

    // P4: vector ADD with DW/16 lanes
    for (int i = 0; i < 32; i++) begin
      va[i] = rnd(); vb[i] = rnd();
      host_op(1, 32'h3000 + i * NB, va[i], q);
      host_op(1, 32'h4000 + i * NB, vb[i], q);
    end
    apb_write(CTL + 13'h004, 32'd0);
    dma(2, 0, 32'h5000, 32 * NB, C_START | C_SSTR | (32'd0 << 12) | (32'd3 << 4));
    dma(0, 32'h3000, 0, 32 * NB, C_START | C_DSTR | (32'd0 << 16) | (32'd3 << 4));
    dma(1, 32'h4000, 0, 32 * NB, C_START | C_DSTR | (32'd1 << 16) | (32'd3 << 4));
    dma_wait(0, "P4 A"); dma_wait(1, "P4 B"); dma_wait(2, "P4 R");
    for (int i = 0; i < 32; i++) begin
      logic [DW-1:0] e;
      for (int l = 0; l < LANES; l++) e[l*16 +: 16] = va[i][l*16 +: 16] + vb[i][l*16 +: 16];
      host_op(0, 32'h5000 + i * NB, '0, q);
      `CHECK_EQ(q, e, "P4 vector add")
    end
    tb_finish();
  end

  initial begin
    #200ms;
    $display("TIMEOUT");
    tb_finish();
  end
endmodule

`default_nettype wire
