// =============================================================================
// SilicaFlux DataFabric :: sfb_sram_slave -- SFB2 slave on a SilicaFlux SRAM
// Wrapper Library single-port SRAM (silicaflux-sramlib rtl/mem/sram_sp.sv,
// Project 01, vendored unmodified under third_party/silicaflux-sramlib).
//
//   SFB2 req_*  -> sram_sp req_* (req_we = req_write, req_wmask = req_wstrb,
//                  word address = req_addr[OFF +: AW], req_id unused)
//   sram_sp rsp_* -> SFB2 rsp_* (rsp_err -> rsp_error)
// WRITE_ACK = 1: every write gets exactly one response, issued by sram_sp
// after the array has been written at the acceptance edge -> a write is never
// acknowledged before the memory took it.  Reads return READ_LATENCY cycles
// after acceptance (1..N, any value supported by the library); back-pressure
// is absorbed by the library's response FIFO (RSP_FIFO_DEPTH, credit based).
// Out-of-range words (non-power-of-two DEPTH) -> rsp_error.  The crossbar
// decode window must equal DEPTH*DW/8 bytes (power-of-two DEPTH) or be larger.
// The MBIST test port is passed through (tst_*); tie tst_active low if unused.
// =============================================================================
`include "sram_defs.svh"
`default_nettype none

module sfb_sram_slave #(
  parameter int DW           = 32,
  parameter int DEPTH        = 1024,          // words
  parameter int READ_LATENCY = 1,
  parameter int BACKEND      = `SRAM_BACKEND_GENERIC,
  parameter int MACRO        = 0,
  localparam int SB          = DW / 8,
  localparam int OFF         = (DW > 8) ? $clog2(DW / 8) : 0,
  localparam int AW          = (DEPTH > 1) ? $clog2(DEPTH) : 1
) (
  input  wire logic          clk,
  input  wire logic          rst_n,
  // SFB2 slave
  input  wire logic          req_valid,
  output logic               req_ready,
  input  wire logic          req_write,
  /* verilator lint_off UNUSEDSIGNAL */
  input  wire logic [31:0]   req_addr,        // bits above the window decoded by the crossbar
  /* verilator lint_on UNUSEDSIGNAL */
  input  wire logic [DW-1:0] req_wdata,
  input  wire logic [SB-1:0] req_wstrb,
  output logic               rsp_valid,
  input  wire logic          rsp_ready,
  output logic [DW-1:0]      rsp_rdata,
  output logic               rsp_error,
  // MBIST test port (sram_sp contract)
  input  wire logic          tst_active,
  input  wire logic          tst_ce,
  input  wire logic          tst_we,
  input  wire logic [AW-1:0] tst_addr,
  input  wire logic [DW-1:0] tst_wdata,
  output logic [DW-1:0]      tst_rdata
);
  logic       rsp_we_unused, busy_unused;
  logic [0:0] rsp_id_unused;

  sram_sp #(
    .DATA_WIDTH(DW), .DEPTH(DEPTH), .MASK_WIDTH(SB), .READ_LATENCY(READ_LATENCY),
    .BACKEND(BACKEND), .MACRO(MACRO), .RSP_FIFO_DEPTH(READ_LATENCY + 1), .WRITE_ACK(1),
    .ID_WIDTH(1), .TEST_EN(1)
  ) u_sram (
    .clk, .rst_n,
    .req_valid, .req_ready, .req_we(req_write), .req_addr(req_addr[OFF +: AW]),
    .req_wdata, .req_wmask(req_wstrb), .req_id(1'b0),
    .rsp_valid, .rsp_ready, .rsp_rdata, .rsp_err(rsp_error), .rsp_we(rsp_we_unused),
    .rsp_id(rsp_id_unused),
    .tst_active, .tst_ce, .tst_we, .tst_addr, .tst_wdata, .tst_rdata, .busy(busy_unused)
  );
endmodule

`default_nettype wire
