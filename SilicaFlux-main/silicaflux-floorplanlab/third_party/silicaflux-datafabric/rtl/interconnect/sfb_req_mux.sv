// =============================================================================
// SilicaFlux DataFabric :: sfb_req_mux -- request payload multiplexer
// AND-OR multiplexer selecting one master's request payload with a one-hot
// grant (from sfb_arbiter).  Zero grant -> all-zero payload (no X/garbage on
// an idle slave port).  Purely combinational.
// =============================================================================
`default_nettype none

module sfb_req_mux #(
  parameter int NM = 4,
  parameter int AW = 32,
  parameter int DW = 32,
  localparam int SB = DW / 8
) (
  input  wire logic [NM-1:0]    grant,
  input  wire logic [NM-1:0]    m_write,
  input  wire logic [NM*AW-1:0] m_addr,
  input  wire logic [NM*DW-1:0] m_wdata,
  input  wire logic [NM*SB-1:0] m_wstrb,
  output logic                  s_write,
  output logic [AW-1:0]         s_addr,
  output logic [DW-1:0]         s_wdata,
  output logic [SB-1:0]         s_wstrb
);
  always_comb begin
    s_write = 1'b0;
    s_addr  = '0;
    s_wdata = '0;
    s_wstrb = '0;
    for (int m = 0; m < NM; m++) begin
      s_write = s_write | (grant[m] & m_write[m]);
      s_addr  = s_addr  | ({AW{grant[m]}} & m_addr[m*AW +: AW]);
      s_wdata = s_wdata | ({DW{grant[m]}} & m_wdata[m*DW +: DW]);
      s_wstrb = s_wstrb | ({SB{grant[m]}} & m_wstrb[m*SB +: SB]);
    end
  end
endmodule

`default_nettype wire
