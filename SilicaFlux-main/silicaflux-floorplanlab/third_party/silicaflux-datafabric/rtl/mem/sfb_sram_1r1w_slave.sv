// =============================================================================
// SilicaFlux DataFabric :: sfb_sram_1r1w_slave -- SFB2 slave on a SilicaFlux
// SRAM Wrapper Library 1R1W SRAM (silicaflux-sramlib rtl/mem/sram_1r1w.sv).
//
// One SFB2 port drives both library channels: reads -> rd_* / rsp_*, writes ->
// wr_* (posted in the library).  SFB2 needs a completion for every write, so
// the adapter generates the write response one cycle AFTER wr_valid && wr_ready
// (the edge at which the array is written): a write is never acknowledged
// before the memory took it.  wr_err (invalid address) is returned as
// rsp_error.  The adapter holds at most one transaction (in_q) and accepts the
// next one in the cycle the previous response is accepted (full throughput for
// back-to-back transfers, same contract as the crossbar slave port).
// Exploiting true read/write concurrency of a 1R1W macro needs two crossbar
// ports (one read-only, one write-only alias) -- future work, see ROADMAP.
// =============================================================================
`include "sram_defs.svh"
`default_nettype none

module sfb_sram_1r1w_slave #(
  parameter int DW           = 32,
  parameter int DEPTH        = 1024,
  parameter int READ_LATENCY = 1,
  parameter int BACKEND      = `SRAM_BACKEND_GENERIC,
  parameter int MACRO        = 0,
  localparam int SB          = DW / 8,
  localparam int OFF         = (DW > 8) ? $clog2(DW / 8) : 0,
  localparam int AW          = (DEPTH > 1) ? $clog2(DEPTH) : 1
) (
  input  wire logic          clk,
  input  wire logic          rst_n,
  input  wire logic          req_valid,
  output logic               req_ready,
  input  wire logic          req_write,
  /* verilator lint_off UNUSEDSIGNAL */
  input  wire logic [31:0]   req_addr,
  /* verilator lint_on UNUSEDSIGNAL */
  input  wire logic [DW-1:0] req_wdata,
  input  wire logic [SB-1:0] req_wstrb,
  output logic               rsp_valid,
  input  wire logic          rsp_ready,
  output logic [DW-1:0]      rsp_rdata,
  output logic               rsp_error
);
  logic          in_q;                         // one transaction inside the adapter
  logic          wack_q, werr_q;               // pending write acknowledgement
  logic          wr_ready, rd_ready, wr_err, r_valid, r_err;
  logic [DW-1:0] r_rdata, tst_rdata_unused;
  logic [0:0]    r_id_unused;
  logic          busy_unused;

  wire rsp_hs = rsp_valid && rsp_ready;
  wire free   = !in_q || rsp_hs;
  wire do_wr  = req_valid && req_write && free;
  wire do_rd  = req_valid && !req_write && free;

  sram_1r1w #(
    .DATA_WIDTH(DW), .DEPTH(DEPTH), .MASK_WIDTH(SB), .READ_LATENCY(READ_LATENCY),
    .BACKEND(BACKEND), .MACRO(MACRO), .COLLISION(`SRAM_COLL_STALL),
    .RSP_FIFO_DEPTH(READ_LATENCY + 1), .ID_WIDTH(1), .TEST_EN(0)
  ) u_sram (
    .clk, .rst_n,
    .wr_valid(do_wr), .wr_ready, .wr_addr(req_addr[OFF +: AW]), .wr_data(req_wdata),
    .wr_mask(req_wstrb), .wr_err,
    .rd_valid(do_rd), .rd_ready, .rd_addr(req_addr[OFF +: AW]), .rd_id(1'b0),
    .rsp_valid(r_valid), .rsp_ready(rsp_ready && !wack_q), .rsp_rdata(r_rdata), .rsp_err(r_err),
    .rsp_id(r_id_unused),
    .tst_active(1'b0), .tst_ce(1'b0), .tst_we(1'b0), .tst_addr('0), .tst_wdata('0),
    .tst_rdata(tst_rdata_unused), .busy(busy_unused)
  );

  assign req_ready = req_write ? (do_wr && wr_ready) : (do_rd && rd_ready);
  assign rsp_valid = wack_q || r_valid;
  assign rsp_rdata = wack_q ? '0 : r_rdata;
  assign rsp_error = wack_q ? werr_q : r_err;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      in_q   <= 1'b0;
      wack_q <= 1'b0;
      werr_q <= 1'b0;
    end else begin
      if (req_valid && req_ready) in_q <= 1'b1;
      else if (rsp_hs)            in_q <= 1'b0;
      if (do_wr && wr_ready) begin
        wack_q <= 1'b1;
        werr_q <= wr_err;
      end else if (wack_q && rsp_ready) begin
        wack_q <= 1'b0;
      end
    end
  end
endmodule

`default_nettype wire
