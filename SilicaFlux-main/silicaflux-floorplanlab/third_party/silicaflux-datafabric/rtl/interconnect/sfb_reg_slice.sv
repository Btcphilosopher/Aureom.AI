// =============================================================================
// SilicaFlux DataFabric :: sfb_reg_slice -- SFB2 pipeline register slice
//
// Inserted between an SFB2 master port (s_*: towards the master) and an SFB2
// slave port (m_*: towards the slave) to cut long combinational paths.
//   REQ_SLICE = 1 : request channel through a 2-entry skid buffer (valid, data
//                   AND ready registered); +1 cycle request latency.
//   RSP_SLICE = 1 : same for the response channel; +1 cycle response latency.
//   0             : channel passes straight through (wires).
// Both slices sustain one transfer per cycle with full back-pressure.  The
// slice is protocol-transparent (in order, exactly one response per request,
// stable payloads under back-pressure); it adds up to one transaction of
// buffering per sliced channel, so it must not be placed between a master and
// a crossbar master port if that master relies on the crossbar to limit it to
// one outstanding transaction (see PROTOCOL.md section 7).
// =============================================================================
`default_nettype none

module sfb_reg_slice #(
  parameter int AW        = 32,
  parameter int DW        = 32,
  parameter int REQ_SLICE = 1,
  parameter int RSP_SLICE = 1,
  localparam int SB       = DW / 8
) (
  input  wire logic          clk,
  input  wire logic          rst_n,
  // upstream (master side)
  input  wire logic          s_req_valid,
  output logic               s_req_ready,
  input  wire logic          s_req_write,
  input  wire logic [AW-1:0] s_req_addr,
  input  wire logic [DW-1:0] s_req_wdata,
  input  wire logic [SB-1:0] s_req_wstrb,
  output logic               s_rsp_valid,
  input  wire logic          s_rsp_ready,
  output logic [DW-1:0]      s_rsp_rdata,
  output logic               s_rsp_error,
  // downstream (slave side)
  output logic               m_req_valid,
  input  wire logic          m_req_ready,
  output logic               m_req_write,
  output logic [AW-1:0]      m_req_addr,
  output logic [DW-1:0]      m_req_wdata,
  output logic [SB-1:0]      m_req_wstrb,
  input  wire logic          m_rsp_valid,
  output logic               m_rsp_ready,
  input  wire logic [DW-1:0] m_rsp_rdata,
  input  wire logic          m_rsp_error
);
  localparam int QW = 1 + AW + DW + SB;
  localparam int PW = DW + 1;

  if (REQ_SLICE != 0) begin : g_req
    sfb_skid_buffer #(.WIDTH(QW)) u_req (
      .clk, .rst_n,
      .s_valid(s_req_valid), .s_ready(s_req_ready),
      .s_data({s_req_write, s_req_addr, s_req_wdata, s_req_wstrb}),
      .m_valid(m_req_valid), .m_ready(m_req_ready),
      .m_data({m_req_write, m_req_addr, m_req_wdata, m_req_wstrb})
    );
  end else begin : g_req_bypass
    assign m_req_valid = s_req_valid;
    assign s_req_ready = m_req_ready;
    assign m_req_write = s_req_write;
    assign m_req_addr  = s_req_addr;
    assign m_req_wdata = s_req_wdata;
    assign m_req_wstrb = s_req_wstrb;
  end

  if (RSP_SLICE != 0) begin : g_rsp
    sfb_skid_buffer #(.WIDTH(PW)) u_rsp (
      .clk, .rst_n,
      .s_valid(m_rsp_valid), .s_ready(m_rsp_ready), .s_data({m_rsp_rdata, m_rsp_error}),
      .m_valid(s_rsp_valid), .m_ready(s_rsp_ready), .m_data({s_rsp_rdata, s_rsp_error})
    );
  end else begin : g_rsp_bypass
    assign s_rsp_valid = m_rsp_valid;
    assign m_rsp_ready = s_rsp_ready;
    assign s_rsp_rdata = m_rsp_rdata;
    assign s_rsp_error = m_rsp_error;
  end
endmodule

`default_nettype wire
