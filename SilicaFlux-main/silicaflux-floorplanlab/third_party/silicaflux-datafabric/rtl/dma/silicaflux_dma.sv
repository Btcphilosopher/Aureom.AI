// =============================================================================
// SilicaFlux DataFabric :: silicaflux_dma -- single-channel DMA controller
//
//   register bus (sfv_periph_bridge page) --> dma_control_regs (+ dma_irq)
//                                                   | start/abort/src/dst/len
//                                                   v
//                    ENGINE = 0: dma_transfer_engine  (simple, default)
//                    ENGINE = 1: dma_burst_engine     (FIFO_DEPTH, BURST,
//                                                      DUAL_PORT, MAX_OUT)
//                                                   |
//                                       SFB2 master port(s) -> sfb_crossbar
// One channel.  Memory-to-memory copies between any SFB2 targets that behave
// like memory (SRAM, tile scratchpad, ROM as source).  The DMA has no memory
// map: illegal regions come back as bus errors, and the SoC access matrix
// (MST_SLV_EN) keeps the DMA out of the peripheral window (MMIO side effects
// have not been reviewed; see docs/datafabric/DMA.md).
// Ports: NP = 1, or 2 when ENGINE = 1 and DUAL_PORT = 1 ([0] read, [1] write).
// =============================================================================
`default_nettype none

module silicaflux_dma #(
  parameter int DW           = 32,
  parameter int ENGINE       = 0,
  parameter int FIFO_DEPTH   = 8,
  parameter int BURST        = 8,
  parameter int DUAL_PORT    = 0,
  parameter int MAX_OUT      = 2,
  parameter int MAX_LEN_LOG2 = 24,
  parameter int PERF         = 1,
  localparam int SB          = DW / 8,
  localparam int NP          = (ENGINE != 0 && DUAL_PORT != 0) ? 2 : 1
) (
  input  wire logic             clk,
  input  wire logic             rst_n,
  // register bus slave
  input  wire logic             rb_sel,
  input  wire logic             rb_we,
  input  wire logic [11:0]      rb_addr,
  input  wire logic [31:0]      rb_wdata,
  output logic [31:0]           rb_rdata,
  output logic                  rb_err,
  output logic                  irq,
  // SFB2 master port(s)
  output logic [NP-1:0]         m_req_valid,
  input  wire logic [NP-1:0]    m_req_ready,
  output logic [NP-1:0]         m_req_write,
  output logic [NP*32-1:0]      m_req_addr,
  output logic [NP*DW-1:0]      m_req_wdata,
  output logic [NP*SB-1:0]      m_req_wstrb,
  input  wire logic [NP-1:0]    m_rsp_valid,
  output logic [NP-1:0]         m_rsp_ready,
  input  wire logic [NP*DW-1:0] m_rsp_rdata,
  input  wire logic [NP-1:0]    m_rsp_error,
  // status / performance events
  output logic                  busy,
  output logic                  ev_done,
  output logic [31:0]           bytes_done,
  output logic [7:0]            fifo_level      // buffered engine FIFO occupancy (0 for the simple engine)
);
  logic        start, abort, done, fail, ev_stall;
  logic [31:0] cfg_src, cfg_dst, cfg_len, err_addr;
  logic [3:0]  err_code;
  logic [2:0]  state;

  dma_control_regs #(.DW(DW), .ENGINE(ENGINE), .FIFO_DEPTH((ENGINE != 0) ? FIFO_DEPTH : 1),
                     .MAX_LEN_LOG2(MAX_LEN_LOG2), .PERF(PERF)) u_regs (
    .clk, .rst_n, .rb_sel, .rb_we, .rb_addr, .rb_wdata, .rb_rdata, .rb_err,
    .start, .abort, .cfg_src, .cfg_dst, .cfg_len,
    .busy, .done, .fail, .err_code, .err_addr, .bytes_done, .state, .ev_stall, .irq
  );

  if (ENGINE == 0) begin : g_simple
    dma_transfer_engine #(.DW(DW), .MAX_LEN_LOG2(MAX_LEN_LOG2)) u_eng (
      .clk, .rst_n, .start, .abort, .cfg_src, .cfg_dst, .cfg_len,
      .busy, .done, .fail, .err_code, .err_addr, .bytes_done, .state, .ev_stall,
      .req_valid(m_req_valid[0]), .req_ready(m_req_ready[0]), .req_write(m_req_write[0]),
      .req_addr(m_req_addr[31:0]), .req_wdata(m_req_wdata[DW-1:0]), .req_wstrb(m_req_wstrb[SB-1:0]),
      .rsp_valid(m_rsp_valid[0]), .rsp_ready(m_rsp_ready[0]), .rsp_rdata(m_rsp_rdata[DW-1:0]),
      .rsp_error(m_rsp_error[0])
    );
    assign fifo_level = 8'd0;
  end else begin : g_burst
    dma_burst_engine #(.DW(DW), .MAX_LEN_LOG2(MAX_LEN_LOG2), .FIFO_DEPTH(FIFO_DEPTH), .BURST(BURST),
                       .DUAL_PORT(DUAL_PORT), .MAX_OUT(MAX_OUT)) u_eng (
      .clk, .rst_n, .start, .abort, .cfg_src, .cfg_dst, .cfg_len,
      .busy, .done, .fail, .err_code, .err_addr, .bytes_done, .state, .ev_stall, .fifo_level,
      .req_valid(m_req_valid), .req_ready(m_req_ready), .req_write(m_req_write),
      .req_addr(m_req_addr), .req_wdata(m_req_wdata), .req_wstrb(m_req_wstrb),
      .rsp_valid(m_rsp_valid), .rsp_ready(m_rsp_ready), .rsp_rdata(m_rsp_rdata),
      .rsp_error(m_rsp_error)
    );
  end
  assign ev_done = done;
endmodule

`default_nettype wire
