// =============================================================================
// tb_sf25_dma_bridge :: MemoryFlow DMA <-> the EXISTING SilicaFlux 2.5 SPM
//
//   sf_dma (APB, 2 ch, 128-bit) --rd--> sf_mem_router --+--> sf_mc25_vport_bridge --> memory_controller.sf
//                               --wr--> sf_mem_router --+                              (unmodified, vector port)
//                                                       +--> sf_extmem_model (DRAM stand-in, 20-cycle latency)
//
// Data correctness is proven by round trips (EXT -> SPM -> EXT, SPM -> SPM ->
// EXT) compared byte-for-byte through the external model's backdoor; the
// SilicaFlux controller's own exceptions are checked to reach the DMA as bus
// errors.  Bandwidths are RTL_SIMULATION metrics.
// =============================================================================
`timescale 1ns/1ps
`include "tb_common.svh"

module tb_sf25_dma_bridge;
  import silicaflux_pkg::*;

  localparam int DW = 128, NB = 16, AW = 32;
  localparam logic [31:0] SPM_BASE = 32'h1000_0000, EXT_BASE = 32'h8000_0000;
  localparam int SPM_SIZE = 65536, EXT_SIZE = 262144;
  localparam logic [31:0] VDOM = 32'h4000;          // first vector-domain byte offset (1024 lines)

  logic clk = 0, rst_n = 0;
  always #5 clk = ~clk;
  longint cyc = 0;
  always @(posedge clk) cyc <= cyc + 1;

  // ---------------------------------------------------------------- DMA
  logic psel = 0, penable = 0, pwrite = 0, pready, pslverr, irq;
  logic [11:0] paddr = '0;
  logic [31:0] pwdata = '0, prdata;
  logic rd_req_valid, rd_req_ready, rd_rsp_valid, rd_rsp_ready, rd_rsp_err;
  logic [AW-1:0] rd_req_addr;
  logic [DW-1:0] rd_rsp_rdata;
  logic wr_req_valid, wr_req_ready, wr_rsp_valid, wr_rsp_ready, wr_rsp_err;
  logic [AW-1:0] wr_req_addr;
  logic [DW-1:0] wr_req_wdata;
  logic [NB-1:0] wr_req_wstrb;
  logic [0:0] so_valid, so_ready = 1'b1, si_valid = 1'b0, si_ready;
  logic [DW-1:0] so_data;
  logic [NB-1:0] so_strb;
  logic so_last;

  sf_dma #(.NCH(2), .DW(DW), .NSO(1), .NSI(1), .DFIFO_DEPTH(16), .MAX_BURST_LOG2(4)) u_dma (
    .clk, .rst_n, .psel, .penable, .pwrite, .paddr, .pwdata, .prdata, .pready, .pslverr, .irq,
    .rd_req_valid, .rd_req_ready, .rd_req_addr, .rd_rsp_valid, .rd_rsp_ready, .rd_rsp_rdata, .rd_rsp_err,
    .wr_req_valid, .wr_req_ready, .wr_req_addr, .wr_req_wdata, .wr_req_wstrb,
    .wr_rsp_valid, .wr_rsp_ready, .wr_rsp_err,
    .so_valid, .so_ready, .so_data, .so_strb, .so_last, .si_valid, .si_ready, .si_data('0));

  // ---------------------------------------------------------------- routers (slave 0 = SPM, 1 = EXT)
  localparam logic [2*AW-1:0] BASES = {EXT_BASE, SPM_BASE};
  localparam logic [2*AW-1:0] SIZES = {32'(EXT_SIZE), 32'(SPM_SIZE)};
  logic [1:0] rs_vld, rs_rdy, rs_we, rs_rvld, rs_rrdy, rs_err;
  logic [2*AW-1:0] rs_addr; logic [2*DW-1:0] rs_wd, rs_rd; logic [2*NB-1:0] rs_st;
  logic [1:0] ws_vld, ws_rdy, ws_we, ws_rvld, ws_rrdy, ws_err;
  logic [2*AW-1:0] ws_addr; logic [2*DW-1:0] ws_wd, ws_rd; logic [2*NB-1:0] ws_st;
  logic [DW-1:0] unused_wr_rdata;

  sf_mem_router #(.NS(2), .AW(AW), .DW(DW), .MAXOUT(16), .BASES(BASES), .SIZES(SIZES)) u_rr (
    .clk, .rst_n, .req_valid(rd_req_valid), .req_ready(rd_req_ready), .req_we(1'b0), .req_addr(rd_req_addr),
    .req_wdata('0), .req_wstrb('0), .rsp_valid(rd_rsp_valid), .rsp_ready(rd_rsp_ready),
    .rsp_rdata(rd_rsp_rdata), .rsp_err(rd_rsp_err),
    .s_req_valid(rs_vld), .s_req_ready(rs_rdy), .s_req_we(rs_we), .s_req_addr(rs_addr), .s_req_wdata(rs_wd),
    .s_req_wstrb(rs_st), .s_rsp_valid(rs_rvld), .s_rsp_ready(rs_rrdy), .s_rsp_rdata(rs_rd), .s_rsp_err(rs_err));
  sf_mem_router #(.NS(2), .AW(AW), .DW(DW), .MAXOUT(16), .BASES(BASES), .SIZES(SIZES)) u_wr (
    .clk, .rst_n, .req_valid(wr_req_valid), .req_ready(wr_req_ready), .req_we(1'b1), .req_addr(wr_req_addr),
    .req_wdata(wr_req_wdata), .req_wstrb(wr_req_wstrb), .rsp_valid(wr_rsp_valid), .rsp_ready(wr_rsp_ready),
    .rsp_rdata(unused_wr_rdata), .rsp_err(wr_rsp_err),
    .s_req_valid(ws_vld), .s_req_ready(ws_rdy), .s_req_we(ws_we), .s_req_addr(ws_addr), .s_req_wdata(ws_wd),
    .s_req_wstrb(ws_st), .s_rsp_valid(ws_rvld), .s_rsp_ready(ws_rrdy), .s_rsp_rdata(ws_rd), .s_rsp_err(ws_err));
  assign ws_rd[DW +: DW] = '0;

  // ---------------------------------------------------------------- external memory (offsets)
  sf_extmem_model #(.DW(DW), .AW(AW), .BASE(32'h0), .SIZE(EXT_SIZE), .LATENCY(20), .INTERVAL(1), .MAXOUT(16)) u_ext (
    .clk, .rst_n,
    .rd_req_valid(rs_vld[1]), .rd_req_ready(rs_rdy[1]), .rd_req_addr(rs_addr[AW +: AW]),
    .rd_rsp_valid(rs_rvld[1]), .rd_rsp_ready(rs_rrdy[1]), .rd_rsp_rdata(rs_rd[DW +: DW]), .rd_rsp_err(rs_err[1]),
    .wr_req_valid(ws_vld[1]), .wr_req_ready(ws_rdy[1]), .wr_req_addr(ws_addr[AW +: AW]),
    .wr_req_wdata(ws_wd[DW +: DW]), .wr_req_wstrb(ws_st[NB +: NB]),
    .wr_rsp_valid(ws_rvld[1]), .wr_rsp_ready(ws_rrdy[1]), .wr_rsp_err(ws_err[1]));

  // ---------------------------------------------------------------- bridge + SilicaFlux 2.5 SPM
  logic v_vld, v_rdy, v_rvld, v_rrdy;
  sf_vector_mem_req_t v_req;
  sf_vector_mem_rsp_t v_rsp;
  logic [31:0] strobe_errs;
  sf_mc25_vport_bridge #(.SPM_BASE(SPM_BASE), .RD_DEPTH(4), .WR_DEPTH(4)) u_br (
    .clk, .rst_n,
    .rd_req_valid(rs_vld[0]), .rd_req_ready(rs_rdy[0]), .rd_req_addr(rs_addr[0 +: AW]),
    .rd_rsp_valid(rs_rvld[0]), .rd_rsp_ready(rs_rrdy[0]), .rd_rsp_rdata(rs_rd[0 +: DW]), .rd_rsp_err(rs_err[0]),
    .wr_req_valid(ws_vld[0]), .wr_req_ready(ws_rdy[0]), .wr_req_addr(ws_addr[0 +: AW]),
    .wr_req_wdata(ws_wd[0 +: DW]), .wr_req_wstrb(ws_st[0 +: NB]),
    .wr_rsp_valid(ws_rvld[0]), .wr_rsp_ready(ws_rrdy[0]), .wr_rsp_err(ws_err[0]),
    .v_req_valid(v_vld), .v_req_ready(v_rdy), .v_req(v_req), .v_rsp_valid(v_rvld), .v_rsp_ready(v_rrdy),
    .v_rsp(v_rsp), .cnt_strobe_err(strobe_errs));
  assign ws_rd[0 +: DW] = '0;

  logic s_rdy, s_rvld, b_rdy, b_wrdy, b_rvld, b_dvld, init_done, mc_busy, mc_conf;
  sf_scalar_mem_rsp_t s_rsp; sf_burst_rbeat_t b_r; sf_burst_done_t b_d;
  logic [7:0] coh_v; sf_paddr_t [7:0] coh_a;
  memory_controller u_mc (
    .clk_i(clk), .rst_ni(rst_n), .flush_i(1'b0), .burst_kill_i(1'b0),
    .scalar_req_valid_i(1'b0), .scalar_req_ready_o(s_rdy), .scalar_req_i('0),
    .scalar_rsp_valid_o(s_rvld), .scalar_rsp_ready_i(1'b1), .scalar_rsp_o(s_rsp),
    .vector_req_valid_i(v_vld), .vector_req_ready_o(v_rdy), .vector_req_i(v_req),
    .vector_rsp_valid_o(v_rvld), .vector_rsp_ready_i(v_rrdy), .vector_rsp_o(v_rsp),
    .burst_req_valid_i(1'b0), .burst_req_ready_o(b_rdy), .burst_req_i('0),
    .burst_wdata_valid_i(1'b0), .burst_wdata_ready_o(b_wrdy), .burst_wdata_i('0),
    .burst_rdata_valid_o(b_rvld), .burst_rdata_ready_i(1'b1), .burst_rdata_o(b_r),
    .burst_done_valid_o(b_dvld), .burst_done_ready_i(1'b1), .burst_done_o(b_d),
    .coh_wr_valid_o(coh_v), .coh_wr_addr_o(coh_a),
    .init_done_o(init_done), .busy_o(mc_busy), .bank_conflict_o(mc_conf));

  // ---------------------------------------------------------------- APB / DMA helpers
  task automatic apb_write(input logic [11:0] a, input logic [31:0] d);
    psel = 1; penable = 0; pwrite = 1; paddr = a; pwdata = d;
    @(negedge clk); penable = 1;
    @(negedge clk); psel = 0; penable = 0; pwrite = 0;
  endtask
  task automatic apb_read(input logic [11:0] a, output logic [31:0] d);
    psel = 1; penable = 0; pwrite = 0; paddr = a;
    @(negedge clk); penable = 1;
    #1 d = prdata;
    @(negedge clk); psel = 0; penable = 0;
  endtask
  function automatic logic [11:0] creg(int ch, int off); return 12'(12'h100 + ch * 12'h40 + off); endfunction

  task automatic dma_start(int ch, logic [31:0] src, logic [31:0] dst, int len, int bl2);
    apb_write(creg(ch, 8'h04), 32'h6);                       // clear DONE / ERR
    apb_write(creg(ch, 8'h08), src);
    apb_write(creg(ch, 8'h0C), dst);
    apb_write(creg(ch, 8'h10), 32'(len));
    apb_write(creg(ch, 8'h14), 32'd1);
    apb_write(creg(ch, 8'h00), 32'h1 | (32'(bl2) << 4));
  endtask
  task automatic dma_wait(int ch, output logic [31:0] st);
    int n; n = 0;
    do begin apb_read(creg(ch, 8'h04), st); n++; end while (st[0] && n < 400000);
    `CHECK(!st[0], $sformatf("ch%0d completes (no hang)", ch))
  endtask
  // one copy, returns achieved bytes/cycle
  task automatic copy(int ch, logic [31:0] src, logic [31:0] dst, int len, int bl2, string tag, output real bpc);
    logic [31:0] st; longint c0;
    dma_start(ch, src, dst, len, bl2);
    c0 = cyc;
    dma_wait(ch, st);
    bpc = real'(len) / real'(cyc - c0);
    `CHECK_EQ(st[2:0], 3'b010, $sformatf("%s: DONE without error", tag))
  endtask

  // ---------------------------------------------------------------- backdoor helpers
  task automatic ext_fill(int lo, int n, int unsigned salt);
    for (int i = 0; i < n; i++) u_ext.mem[lo + i] = 8'((i * 131 + salt) ^ (i >> 7));
  endtask
  task automatic ext_compare(int a, int b, int n, string tag);
    int bad; bad = 0;
    for (int i = 0; i < n; i++) if (u_ext.mem[a + i] !== u_ext.mem[b + i]) bad++;
    `CHECK(bad == 0, $sformatf("%s: %0d of %0d bytes differ", tag, bad, n))
    tb_checks += n / 16;
  endtask

  real bpc;
  initial begin
    logic [31:0] st;
    repeat (3) @(negedge clk); rst_n = 1;
    while (!init_done) @(negedge clk);
    repeat (4) @(negedge clk);
    ext_fill(0, 65536, 7);

    // 1. EXT -> SilicaFlux SPM (vector domain), 16 KiB, 16-beat bursts
    copy(0, EXT_BASE + 32'h0000, SPM_BASE + VDOM, 16384, 4, "EXT->SPM", bpc);
    tb_metric("sf25_dma_ext_to_spm_bytes_per_cycle", bpc);
    // 2. SPM -> EXT, compare round trip
    copy(0, SPM_BASE + VDOM, EXT_BASE + 32'h1_0000, 16384, 4, "SPM->EXT", bpc);
    tb_metric("sf25_dma_spm_to_ext_bytes_per_cycle", bpc);
    ext_compare(32'h0000, 32'h1_0000, 16384, "round trip EXT->SPM->EXT");
    // 3. SPM -> SPM through the single vector port, then out and compare
    copy(1, SPM_BASE + VDOM, SPM_BASE + VDOM + 32'h4000, 16384, 4, "SPM->SPM", bpc);
    tb_metric("sf25_dma_spm_to_spm_bytes_per_cycle", bpc);
    copy(1, SPM_BASE + VDOM + 32'h4000, EXT_BASE + 32'h2_0000, 16384, 4, "SPM->EXT (2)", bpc);
    ext_compare(32'h0000, 32'h2_0000, 16384, "SPM->SPM copy");
    // 4. burst-length sweep EXT -> SPM
    for (int bl2 = 0; bl2 <= 4; bl2++) begin
      copy(0, EXT_BASE + 32'h4000, SPM_BASE + VDOM + 32'h8000, 8192, bl2, $sformatf("sweep bl2=%0d", bl2), bpc);
      tb_metric($sformatf("sf25_dma_ext_to_spm_bytes_per_cycle_burst%0d", 1 << bl2), bpc);
    end
    copy(0, SPM_BASE + VDOM + 32'h8000, EXT_BASE + 32'h3_0000, 8192, 4, "sweep readback", bpc);
    ext_compare(32'h4000, 32'h3_0000, 8192, "burst-sweep data");
    // 5. both channels concurrently: EXT->SPM and SPM->EXT on disjoint regions
    begin
      longint c0;
      ext_fill(32'h5000, 8192, 99);
      dma_start(0, EXT_BASE + 32'h5000, SPM_BASE + VDOM + 32'hA000, 8192, 4);
      dma_start(1, SPM_BASE + VDOM, EXT_BASE + 32'h3_8000, 16384, 4);
      c0 = cyc;
      dma_wait(0, st); `CHECK_EQ(st[2:0], 3'b010, "concurrent ch0 done")
      dma_wait(1, st); `CHECK_EQ(st[2:0], 3'b010, "concurrent ch1 done")
      tb_metric("sf25_dma_concurrent_bytes_per_cycle", real'(8192 + 16384) / real'(cyc - c0));
      ext_compare(32'h0000, 32'h3_8000, 16384, "concurrent SPM->EXT");
      copy(0, SPM_BASE + VDOM + 32'hA000, EXT_BASE + 32'h3_C000, 8192, 4, "concurrent readback", bpc);
      ext_compare(32'h5000, 32'h3_C000, 8192, "concurrent EXT->SPM");
    end
    // 6. the SilicaFlux controller's protection reaches the DMA as a write bus error
    dma_start(0, EXT_BASE, SPM_BASE + 32'h0000, 256, 4);            // scalar domain: DOMAIN exception
    dma_wait(0, st);
    `CHECK_EQ(st[7:4], 4'd5, "write into SilicaFlux scalar domain -> DMA WR_BUS error")
    dma_start(0, SPM_BASE + 32'h0010, EXT_BASE + 32'h3_F000, 64, 4); // scalar-domain read: DOMAIN
    dma_wait(0, st);
    `CHECK_EQ(st[7:4], 4'd4, "read from SilicaFlux scalar domain -> DMA RD_BUS error")
    // 7. byte-granular tail: last beat has a partial lane -> poisoned, reported, nothing written
    //    (SPM offset VDOM+0x9000 holds the burst-sweep data, mirrored at EXT 0x3_1000)
    dma_start(0, EXT_BASE, SPM_BASE + VDOM + 32'h9000, 18, 4);
    dma_wait(0, st);
    `CHECK_EQ(st[7:4], 4'd5, "partial-lane tail strobe -> WR_BUS error (vector port is lane-granular)")
    `CHECK_EQ(strobe_errs, 32'd1, "bridge poisoned exactly the partial-lane write")
    copy(0, SPM_BASE + VDOM + 32'h9000, EXT_BASE + 32'h3_F100, 32, 4, "poison readback", bpc);
    ext_compare(32'h0000, 32'h3_F100, 16, "full first beat was written");
    ext_compare(32'h3_1010, 32'h3_F110, 16, "poisoned partial beat wrote nothing");
    tb_metric("sf25_bridge_strobe_errors", real'(strobe_errs));
    tb_finish();
  end
  initial begin #40_000_000; `CHECK(0, "global timeout"); tb_finish(); end
endmodule
