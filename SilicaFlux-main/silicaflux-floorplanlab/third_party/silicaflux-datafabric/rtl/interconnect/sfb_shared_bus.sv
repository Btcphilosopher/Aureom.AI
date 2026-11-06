// =============================================================================
// SilicaFlux DataFabric :: sfb_shared_bus -- single shared bus (comparison topology)
//
// NM masters share ONE transaction slot: an NM x 1 sfb_crossbar (arbitration
// only, every address maps to its single port) feeds a 1 x NS sfb_crossbar
// (address decode, decode errors, response routing).  Same SFB2 ports as
// sfb_crossbar, so it is a drop-in alternative.  Built only from the verified
// crossbar; at most one transaction is in flight in the whole fabric, so the
// aggregate bandwidth is that of one slave port.  The per-master access matrix
// cannot be applied after arbitration and is therefore not supported
// (MST_SLV_EN must be all ones) -- one of the reasons the crossbar is the
// SilicaFlux-V choice (docs/datafabric/PPA.md).
// =============================================================================
`default_nettype none

module sfb_shared_bus #(
  parameter int                  NM          = 2,
  parameter int                  NS          = 2,
  parameter int                  AW          = 32,
  parameter int                  DW          = 32,
  parameter int                  ARB_MODE    = 1,
  parameter int                  CHECK_ALIGN = 1,
  parameter logic [NS*AW-1:0]    SLV_BASE    = {(NS*AW){1'b0}},
  parameter logic [NS*AW-1:0]    SLV_MASK    = {(NS*AW){1'b0}},
  localparam int                 SB          = DW / 8,
  localparam int                 MW          = (NM > 1) ? $clog2(NM) : 1
) (
  input  wire logic                clk,
  input  wire logic                rst_n,
  input  wire logic [NM-1:0]       m_req_valid,
  output logic      [NM-1:0]       m_req_ready,
  input  wire logic [NM-1:0]       m_req_write,
  input  wire logic [NM*AW-1:0]    m_req_addr,
  input  wire logic [NM*DW-1:0]    m_req_wdata,
  input  wire logic [NM*SB-1:0]    m_req_wstrb,
  output logic      [NM-1:0]       m_rsp_valid,
  input  wire logic [NM-1:0]       m_rsp_ready,
  output logic      [NM*DW-1:0]    m_rsp_rdata,
  output logic      [NM-1:0]       m_rsp_error,
  output logic      [NS-1:0]       s_req_valid,
  input  wire logic [NS-1:0]       s_req_ready,
  output logic      [NS-1:0]       s_req_write,
  output logic      [NS*AW-1:0]    s_req_addr,
  output logic      [NS*DW-1:0]    s_req_wdata,
  output logic      [NS*SB-1:0]    s_req_wstrb,
  input  wire logic [NS-1:0]       s_rsp_valid,
  output logic      [NS-1:0]       s_rsp_ready,
  input  wire logic [NS*DW-1:0]    s_rsp_rdata,
  input  wire logic [NS-1:0]       s_rsp_error,
  output logic                     err_evt,
  output logic [AW-1:0]            err_addr,
  output logic [MW-1:0]            err_master,
  output logic                     err_write,
  output logic [NM-1:0]            ev_req_accept,
  output logic [NM-1:0]            ev_req_stall,
  output logic [NM-1:0]            ev_arb_loss,
  output logic [NM-1:0]            ev_rsp_stall
);
  logic          b_req_valid, b_req_ready, b_req_write, b_rsp_valid, b_rsp_ready, b_rsp_error;
  logic [AW-1:0] b_req_addr;
  logic [DW-1:0] b_req_wdata, b_rsp_rdata;
  logic [SB-1:0] b_req_wstrb;
  logic          e1_evt, e1_w, e2_w;
  logic [AW-1:0] e1_a;
  logic [MW-1:0] e1_m;
  logic          e2_m;
  logic [0:0]    a0, a1, a2, a3;

  // stage 1: arbitration (all addresses map to the single bus port; no alignment check here)
  sfb_crossbar #(.NM(NM), .NS(1), .AW(AW), .DW(DW), .ARB_MODE(ARB_MODE), .CHECK_ALIGN(0),
                 .SLV_BASE({AW{1'b0}}), .SLV_MASK({AW{1'b0}}), .MST_SLV_EN({NM{1'b1}})) u_arb (
    .clk, .rst_n,
    .m_req_valid, .m_req_ready, .m_req_write, .m_req_addr, .m_req_wdata, .m_req_wstrb,
    .m_rsp_valid, .m_rsp_ready, .m_rsp_rdata, .m_rsp_error,
    .s_req_valid(b_req_valid), .s_req_ready(b_req_ready), .s_req_write(b_req_write),
    .s_req_addr(b_req_addr), .s_req_wdata(b_req_wdata), .s_req_wstrb(b_req_wstrb),
    .s_rsp_valid(b_rsp_valid), .s_rsp_ready(b_rsp_ready), .s_rsp_rdata(b_rsp_rdata),
    .s_rsp_error(b_rsp_error),
    .err_evt(e1_evt), .err_addr(e1_a), .err_master(e1_m), .err_write(e1_w),
    .ev_req_accept, .ev_req_stall, .ev_arb_loss, .ev_rsp_stall
  );

  // stage 2: decode / routing on the shared bus
  sfb_crossbar #(.NM(1), .NS(NS), .AW(AW), .DW(DW), .ARB_MODE(0), .CHECK_ALIGN(CHECK_ALIGN),
                 .SLV_BASE(SLV_BASE), .SLV_MASK(SLV_MASK), .MST_SLV_EN({NS{1'b1}})) u_dec (
    .clk, .rst_n,
    .m_req_valid(b_req_valid), .m_req_ready(b_req_ready), .m_req_write(b_req_write),
    .m_req_addr(b_req_addr), .m_req_wdata(b_req_wdata), .m_req_wstrb(b_req_wstrb),
    .m_rsp_valid(b_rsp_valid), .m_rsp_ready(b_rsp_ready), .m_rsp_rdata(b_rsp_rdata),
    .m_rsp_error(b_rsp_error),
    .s_req_valid, .s_req_ready, .s_req_write, .s_req_addr, .s_req_wdata, .s_req_wstrb,
    .s_rsp_valid, .s_rsp_ready, .s_rsp_rdata, .s_rsp_error,
    .err_evt, .err_addr, .err_master(e2_m), .err_write(e2_w),
    .ev_req_accept(a0), .ev_req_stall(a1), .ev_arb_loss(a2), .ev_rsp_stall(a3)
  );
  // the decode error belongs to the master that currently owns the bus
  always_comb begin
    err_master = '0;
    err_write  = e2_w;
    for (int m = 0; m < NM; m++) if (ev_req_accept[m]) err_master = MW'(m);
  end
  /* verilator lint_off UNUSEDSIGNAL */
  wire unused = e1_evt ^ e1_w ^ ^e1_a ^ ^e1_m ^ e2_m ^ a0[0] ^ a1[0] ^ a2[0] ^ a3[0];
  /* verilator lint_on UNUSEDSIGNAL */
endmodule

`default_nettype wire
