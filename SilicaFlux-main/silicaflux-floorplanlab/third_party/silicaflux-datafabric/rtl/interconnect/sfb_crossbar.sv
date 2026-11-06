// =============================================================================
// SilicaFlux DataFabric :: sfb_crossbar -- SFB2 interconnect, NM masters x NS slaves
//
// Protocol: SFB2 (docs/datafabric/PROTOCOL.md), a backward-compatible
// extension of the SilicaFlux-V SFB (silicaflux-v docs/BUS.md) that adds
// response back-pressure (rsp_ready) and configurable data width.
//   request : req_valid/req_ready, req_write, req_addr, req_wdata, req_wstrb
//   response: rsp_valid/rsp_ready, rsp_rdata, rsp_error
//
// Architecture (same transaction model as silicaflux-v rtl/bus/sfv_xbar.sv,
// which this module supersedes in sfv_soc_df):
//   * per master: sfb_addr_decoder (+ access matrix MST_SLV_EN, alignment
//     check) and an sfb_error_slave answering unmapped/denied/misaligned
//     requests with rsp_error = 1 one cycle after acceptance;
//   * per slave: sfb_arbiter (fixed priority or round robin, grant lock under
//     back-pressure) and sfb_req_mux;
//   * one sfb_rsp_router steering each slave response to the master that owns
//     the outstanding transaction.
//   * every master port has at most ONE transaction outstanding; a new request
//     is accepted no earlier than the cycle in which the previous response is
//     accepted (full throughput: back-to-back transactions with no bubble).
//   * every slave port has at most ONE transaction outstanding (same rule);
//     responses therefore can never be re-ordered and need no IDs.
//   * latency added: 0 cycles in both directions (combinational); insert
//     sfb_reg_slice on long paths.
//   * a partial crossbar is obtained with MST_SLV_EN: disabled master/slave
//     pairs are removed by constant propagation (no mux input, no arbiter
//     request) and map to the decode-error slave.
// Combinational paths: m_req_* -> s_req_*; s_req_ready -> m_req_ready;
//   s_rsp_* -> m_rsp_*; m_rsp_ready -> s_rsp_ready; m_rsp_ready, s_rsp_valid
//   -> s_req_valid (slave freed in the cycle its response is accepted).
//   Loop-free when attached components obey PROTOCOL.md rules R3/R4.
// =============================================================================
`default_nettype none

module sfb_crossbar #(
  parameter int                  NM          = 2,
  parameter int                  NS          = 2,
  parameter int                  AW          = 32,
  parameter int                  DW          = 32,
  parameter int                  ARB_MODE    = 1,     // 0 fixed priority, 1 round robin
  parameter int                  CHECK_ALIGN = 1,
  // NOTE: sized fill literals only -- Yosys 0.33 treats an unsized '1 in a
  // parameter default/override as a 1-bit 1 (docs/datafabric/PROTOCOL.md sec. 9)
  parameter logic [NS*AW-1:0]    SLV_BASE    = {(NS*AW){1'b0}},
  parameter logic [NS*AW-1:0]    SLV_MASK    = {(NS*AW){1'b0}},
  parameter logic [NM*NS-1:0]    MST_SLV_EN  = {(NM*NS){1'b1}},    // bit m*NS+s
  localparam int                 SB          = DW / 8,
  localparam int                 MW          = (NM > 1) ? $clog2(NM) : 1,
  localparam int                 SW          = (NS > 1) ? $clog2(NS) : 1
) (
  input  wire logic                clk,
  input  wire logic                rst_n,
  // ---------------------------------------------------------------- masters
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
  // ---------------------------------------------------------------- slaves
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
  // ---------------------------------------------------------------- decode-error capture
  output logic                     err_evt,        // a decode error was accepted this cycle
  output logic [AW-1:0]            err_addr,
  output logic [MW-1:0]            err_master,
  output logic                     err_write,
  // ---------------------------------------------------------------- per-master events (perf/trace)
  output logic [NM-1:0]            ev_req_accept,  // request handshake
  output logic [NM-1:0]            ev_req_stall,   // req_valid && !req_ready
  output logic [NM-1:0]            ev_arb_loss,    // eligible but another master won the slave
  output logic [NM-1:0]            ev_rsp_stall    // rsp_valid && !rsp_ready
);
  // ---------------------------------------------------------------- state
  logic [NM-1:0]    out_q;           // master has a transaction outstanding
  logic [NS-1:0]    busy_q;          // slave has a transaction outstanding
  logic [NS*NM-1:0] owner_q;         // one-hot owner per slave

  // ---------------------------------------------------------------- decode
  logic [NM*NS-1:0] dec_oh;          // bit m*NS+s
  logic [NM-1:0]    dec_hit;
  genvar gm, gs;
  for (gm = 0; gm < NM; gm++) begin : g_dec
    logic [SW-1:0] sel_unused;
    logic          mis_unused;
    sfb_addr_decoder #(
      .NS(NS), .AW(AW), .DW(DW), .CHECK_ALIGN(CHECK_ALIGN),
      .SLV_BASE(SLV_BASE), .SLV_MASK(SLV_MASK), .EN(MST_SLV_EN[gm*NS +: NS])
    ) u_dec (
      .addr(m_req_addr[gm*AW +: AW]), .hit(dec_hit[gm]), .sel(sel_unused),
      .sel_oh(dec_oh[gm*NS +: NS]), .misaligned(mis_unused)
    );
  end

  // ---------------------------------------------------------------- responses
  logic [NM-1:0] e_rsp_valid, e_rsp_error, e_req_ready, e_req_valid;
  sfb_rsp_router #(.NM(NM), .NS(NS), .DW(DW)) u_rsp (
    .busy(busy_q), .owner_oh(owner_q),
    .s_rsp_valid, .s_rsp_ready, .s_rsp_rdata, .s_rsp_error,
    .e_rsp_valid, .e_rsp_error,
    .m_rsp_valid, .m_rsp_ready, .m_rsp_rdata, .m_rsp_error
  );

  wire [NM-1:0] m_rsp_hs = m_rsp_valid & m_rsp_ready;
  wire [NS-1:0] s_rsp_hs = s_rsp_valid & s_rsp_ready & busy_q;
  // a master may issue when nothing is outstanding or its response is accepted now
  wire [NM-1:0] m_free = ~out_q | m_rsp_hs;
  // a slave may accept when idle or its response is accepted now
  wire [NS-1:0] s_free = ~busy_q | s_rsp_hs;

  // ---------------------------------------------------------------- decode-error slaves
  for (gm = 0; gm < NM; gm++) begin : g_err
    logic [DW-1:0] e_rdata_unused;   // constant zero by construction
    assign e_req_valid[gm] = m_req_valid[gm] && m_free[gm] && !dec_hit[gm];
    sfb_error_slave #(.DW(DW)) u_err (
      .clk, .rst_n,
      .req_valid(e_req_valid[gm]), .req_ready(e_req_ready[gm]),
      .rsp_valid(e_rsp_valid[gm]), .rsp_ready(m_rsp_ready[gm]),
      .rsp_rdata(e_rdata_unused), .rsp_error(e_rsp_error[gm])
    );
  end

  // ---------------------------------------------------------------- arbitration + request mux
  logic [NS*NM-1:0] grant;           // bit s*NM+m
  logic [NS-1:0]    gvalid;
  for (gs = 0; gs < NS; gs++) begin : g_slv
    logic [NM-1:0] cand;
    logic [MW-1:0] gidx_unused;
    for (gm = 0; gm < NM; gm++) begin : g_cand
      // constant MST_SLV_EN term lets synthesis prune disabled pairs
      assign cand[gm] = MST_SLV_EN[gm*NS + gs] && m_req_valid[gm] && m_free[gm] &&
                        dec_oh[gm*NS + gs];
    end
    sfb_arbiter #(.N(NM), .MODE(ARB_MODE)) u_arb (
      .clk, .rst_n, .req(cand),
      .stall(s_req_valid[gs] && !s_req_ready[gs]),
      .accept(s_req_valid[gs] && s_req_ready[gs]),
      .grant(grant[gs*NM +: NM]), .grant_idx(gidx_unused), .grant_valid(gvalid[gs])
    );
    assign s_req_valid[gs] = gvalid[gs] && s_free[gs];
    sfb_req_mux #(.NM(NM), .AW(AW), .DW(DW)) u_mux (
      .grant(grant[gs*NM +: NM]),
      .m_write(m_req_write), .m_addr(m_req_addr), .m_wdata(m_req_wdata), .m_wstrb(m_req_wstrb),
      .s_write(s_req_write[gs]), .s_addr(s_req_addr[gs*AW +: AW]),
      .s_wdata(s_req_wdata[gs*DW +: DW]), .s_wstrb(s_req_wstrb[gs*SB +: SB])
    );
  end

  // ---------------------------------------------------------------- master ready / events
  always_comb begin
    for (int m = 0; m < NM; m++) begin
      m_req_ready[m] = e_req_valid[m] && e_req_ready[m];
      ev_arb_loss[m] = 1'b0;
      for (int s = 0; s < NS; s++) begin
        if (grant[s*NM + m] && s_req_valid[s] && s_req_ready[s]) m_req_ready[m] = 1'b1;
        if (MST_SLV_EN[m*NS + s] && m_req_valid[m] && m_free[m] && dec_oh[m*NS + s] &&
            !grant[s*NM + m] && gvalid[s])
          ev_arb_loss[m] = 1'b1;
      end
    end
  end
  assign ev_req_accept = m_req_valid & m_req_ready;
  assign ev_req_stall  = m_req_valid & ~m_req_ready;
  assign ev_rsp_stall  = m_rsp_valid & ~m_rsp_ready;

  // ---------------------------------------------------------------- state update
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      out_q   <= '0;
      busy_q  <= '0;
      owner_q <= '0;
    end else begin
      for (int m = 0; m < NM; m++) begin
        if (m_req_valid[m] && m_req_ready[m]) out_q[m] <= 1'b1;
        else if (m_rsp_hs[m])                 out_q[m] <= 1'b0;
      end
      for (int s = 0; s < NS; s++) begin
        if (s_req_valid[s] && s_req_ready[s]) begin
          busy_q[s]             <= 1'b1;
          owner_q[s*NM +: NM]   <= grant[s*NM +: NM];
        end else if (s_rsp_hs[s]) begin
          busy_q[s]             <= 1'b0;
        end
      end
    end
  end

  // ---------------------------------------------------------------- decode-error capture
  always_comb begin
    err_evt    = 1'b0;
    err_addr   = '0;
    err_master = '0;
    err_write  = 1'b0;
    for (int m = NM - 1; m >= 0; m--) begin
      if (e_req_valid[m] && e_req_ready[m]) begin
        err_evt    = 1'b1;
        err_addr   = m_req_addr[m*AW +: AW];
        err_master = MW'(m);
        err_write  = m_req_write[m];
      end
    end
  end
endmodule

`default_nettype wire
