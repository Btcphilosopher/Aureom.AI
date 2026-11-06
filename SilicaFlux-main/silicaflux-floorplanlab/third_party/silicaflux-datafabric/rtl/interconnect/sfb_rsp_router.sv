// =============================================================================
// SilicaFlux DataFabric :: sfb_rsp_router -- response routing
//
// Each slave port s holds at most one transaction (busy[s]) whose owner is the
// one-hot owner_oh[s*NM +: NM] recorded at acceptance.  The slave's response
// is steered only to that owner; the owner's rsp_ready is steered back as the
// slave's rsp_ready.  Responses of the per-master decode-error slaves
// (e_rsp_valid) are merged in.  A master never receives a response it does
// not own: every m_rsp_valid term is qualified by busy & owner (or by the
// master's own error slave).  Purely combinational.
// =============================================================================
`default_nettype none

module sfb_rsp_router #(
  parameter int NM = 4,
  parameter int NS = 4,
  parameter int DW = 32
) (
  input  wire logic [NS-1:0]    busy,
  input  wire logic [NS*NM-1:0] owner_oh,
  input  wire logic [NS-1:0]    s_rsp_valid,
  output logic      [NS-1:0]    s_rsp_ready,
  input  wire logic [NS*DW-1:0] s_rsp_rdata,
  input  wire logic [NS-1:0]    s_rsp_error,
  input  wire logic [NM-1:0]    e_rsp_valid,     // decode-error slave responses
  input  wire logic [NM-1:0]    e_rsp_error,
  output logic      [NM-1:0]    m_rsp_valid,
  input  wire logic [NM-1:0]    m_rsp_ready,
  output logic      [NM*DW-1:0] m_rsp_rdata,
  output logic      [NM-1:0]    m_rsp_error
);
  always_comb begin
    m_rsp_valid = e_rsp_valid;
    m_rsp_error = e_rsp_valid & e_rsp_error;
    m_rsp_rdata = '0;
    s_rsp_ready = '0;
    for (int s = 0; s < NS; s++) begin
      for (int m = 0; m < NM; m++) begin
        if (busy[s] && owner_oh[s*NM + m]) begin
          s_rsp_ready[s] = m_rsp_ready[m];
          if (s_rsp_valid[s]) begin
            m_rsp_valid[m]          = 1'b1;
            m_rsp_error[m]          = s_rsp_error[s];
            m_rsp_rdata[m*DW +: DW] = s_rsp_rdata[s*DW +: DW];
          end
        end
      end
    end
  end
endmodule

`default_nettype wire
