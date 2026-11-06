// =============================================================================
// SilicaFlux-V :: sfv_xbar -- SFB crossbar (NM masters x NS slaves)
//
// SFB protocol (docs/BUS.md):
//   request : req, addr, we, be, wdata  ->  gnt   (transfer when req & gnt)
//   response: rvalid, rdata, err        (one per transfer, in order,
//                                         >= 1 cycle after gnt, never stalled)
//   gnt may depend combinationally on req/addr; req must not depend on gnt.
//
// Properties of this implementation:
//   * address decode: slave s selected when (addr & SLV_MASK[s]) == SLV_BASE[s]
//     (first match wins); no match -> internal decode-error responder.
//   * per-master access mask MST_SLV_EN[m] (e.g. execute-never: the CPU
//     instruction port cannot reach peripherals) -> decode error.
//   * every master has at most ONE transaction outstanding (a new one may be
//     granted in the cycle the previous response returns), so responses can
//     never be re-ordered and need no IDs.
//   * every slave port likewise holds at most one transaction outstanding.
//   * arbitration per slave: fixed priority, master 0 highest (deterministic;
//     starvation-free here because every master waits for its own response
//     before issuing again and the highest-priority master is the JTAG
//     debug port, which is human/tester paced).
//   * decode errors are reported (err=1, rdata=0) one cycle after grant and
//     captured on the err_* outputs for the bus-error status register.
// =============================================================================
`default_nettype none

module sfv_xbar #(
  parameter int NM = 3,
  parameter int NS = 7,
  parameter logic [NS*32-1:0] SLV_BASE   = '0,
  parameter logic [NS*32-1:0] SLV_MASK   = '0,
  parameter logic [NM*NS-1:0] MST_SLV_EN = '1     // bit m*NS+s
) (
  input  wire logic                clk,
  input  wire logic                rst_n,
  // masters
  input  wire logic [NM-1:0]       m_req,
  output logic      [NM-1:0]       m_gnt,
  input  wire logic [NM*32-1:0]    m_addr,
  input  wire logic [NM-1:0]       m_we,
  input  wire logic [NM*4-1:0]     m_be,
  input  wire logic [NM*32-1:0]    m_wdata,
  output logic      [NM-1:0]       m_rvalid,
  output logic      [NM*32-1:0]    m_rdata,
  output logic      [NM-1:0]       m_err,
  // slaves
  output logic      [NS-1:0]       s_req,
  input  wire logic [NS-1:0]       s_gnt,
  output logic      [NS*32-1:0]    s_addr,
  output logic      [NS-1:0]       s_we,
  output logic      [NS*4-1:0]     s_be,
  output logic      [NS*32-1:0]    s_wdata,
  input  wire logic [NS-1:0]       s_rvalid,
  input  wire logic [NS*32-1:0]    s_rdata,
  input  wire logic [NS-1:0]       s_err,
  // decode-error capture (pulse + attributes)
  output logic                     err_evt,
  output logic [31:0]              err_addr,
  output logic [$clog2(NM)-1:0]    err_master,
  output logic                     err_we
);
  localparam int MW = (NM > 1) ? $clog2(NM) : 1;
  localparam int SW = (NS > 1) ? $clog2(NS) : 1;

  // ------------------------------------------------------------ state
  logic [NM-1:0]   out_q;          // master has a transaction outstanding
  logic [NM-1:0]   derr_q;         // outstanding transaction is a decode error
  logic [NS-1:0]   busy_q;         // slave has a transaction outstanding
  logic [MW-1:0]   owner_q [0:NS-1];

  // ------------------------------------------------------------ decode
  logic [NM-1:0]   m_hit;          // address maps to an allowed slave
  logic [SW-1:0]   m_sel [0:NM-1];
  always_comb begin
    for (int m = 0; m < NM; m++) begin
      m_hit[m] = 1'b0;
      m_sel[m] = '0;
      for (int s = NS - 1; s >= 0; s--) begin
        if (((m_addr[m*32 +: 32] & SLV_MASK[s*32 +: 32]) == SLV_BASE[s*32 +: 32]) &&
            MST_SLV_EN[m*NS + s]) begin
          m_hit[m] = 1'b1;
          m_sel[m] = SW'(s);
        end
      end
    end
  end

  // ------------------------------------------------------------ responses
  always_comb begin
    for (int m = 0; m < NM; m++) begin
      m_rvalid[m]            = derr_q[m];
      m_rdata[m*32 +: 32]    = 32'd0;
      m_err[m]               = derr_q[m];
      for (int s = 0; s < NS; s++) begin
        if (busy_q[s] && s_rvalid[s] && owner_q[s] == MW'(m)) begin
          m_rvalid[m]         = 1'b1;
          m_rdata[m*32 +: 32] = s_rdata[s*32 +: 32];
          m_err[m]            = s_err[s];
        end
      end
    end
  end

  // a master may issue when it has nothing outstanding or its response is now
  wire [NM-1:0] m_free = ~out_q | m_rvalid;

  // ------------------------------------------------------------ arbitration
  logic [NM-1:0] win [0:NS-1];       // one-hot winner per slave
  always_comb begin
    for (int s = 0; s < NS; s++) begin
      win[s] = '0;
      for (int m = NM - 1; m >= 0; m--) begin
        if (m_req[m] && m_free[m] && m_hit[m] && m_sel[m] == SW'(s)) win[s] = '0;
        if (m_req[m] && m_free[m] && m_hit[m] && m_sel[m] == SW'(s)) win[s][m] = 1'b1;
      end
    end
  end

  wire [NS-1:0] s_free = ~busy_q | s_rvalid;

  always_comb begin
    s_req   = '0;
    s_addr  = '0;
    s_we    = '0;
    s_be    = '0;
    s_wdata = '0;
    for (int s = 0; s < NS; s++) begin
      for (int m = 0; m < NM; m++) begin
        if (win[s][m]) begin
          s_req[s]             = s_free[s];
          s_addr[s*32 +: 32]   = m_addr[m*32 +: 32];
          s_we[s]              = m_we[m];
          s_be[s*4 +: 4]       = m_be[m*4 +: 4];
          s_wdata[s*32 +: 32]  = m_wdata[m*32 +: 32];
        end
      end
    end
  end

  // grants
  logic [NM-1:0] m_derr_gnt;
  always_comb begin
    for (int m = 0; m < NM; m++) begin
      m_derr_gnt[m] = m_req[m] && m_free[m] && !m_hit[m];
      m_gnt[m]      = m_derr_gnt[m];
      for (int s = 0; s < NS; s++)
        if (win[s][m] && s_req[s] && s_gnt[s]) m_gnt[m] = 1'b1;
    end
  end

  // ------------------------------------------------------------ state update
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      out_q  <= '0;
      derr_q <= '0;
      busy_q <= '0;
      for (int s = 0; s < NS; s++) owner_q[s] <= '0;
    end else begin
      for (int m = 0; m < NM; m++) begin
        if (m_gnt[m])         out_q[m] <= 1'b1;
        else if (m_rvalid[m]) out_q[m] <= 1'b0;
        derr_q[m] <= m_derr_gnt[m];
      end
      for (int s = 0; s < NS; s++) begin
        if (s_req[s] && s_gnt[s]) begin
          busy_q[s] <= 1'b1;
          for (int m = 0; m < NM; m++) if (win[s][m]) owner_q[s] <= MW'(m);
        end else if (s_rvalid[s]) begin
          busy_q[s] <= 1'b0;
        end
      end
    end
  end

  // ------------------------------------------------------------ error capture
  always_comb begin
    err_evt    = 1'b0;
    err_addr   = '0;
    err_master = '0;
    err_we     = 1'b0;
    for (int m = NM - 1; m >= 0; m--) begin
      if (m_derr_gnt[m]) begin
        err_evt    = 1'b1;
        err_addr   = m_addr[m*32 +: 32];
        err_master = MW'(m);
        err_we     = m_we[m];
      end
    end
  end

endmodule

`default_nettype wire
