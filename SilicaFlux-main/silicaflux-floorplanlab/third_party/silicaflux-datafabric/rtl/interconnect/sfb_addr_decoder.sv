// =============================================================================
// SilicaFlux DataFabric :: sfb_addr_decoder -- one master's address decoder
//
// Slave s is selected when (addr & SLV_MASK[s]) == SLV_BASE[s] and the access
// matrix bit EN[s] for this master is set.  Regions must not overlap (checked
// by python/datafabric/memmap_gen.py, which also produces BASE/MASK); if they
// did, the lowest slave index would win (same rule as sfv_xbar).
// CHECK_ALIGN = 1: an address with addr[OFF-1:0] != 0 (OFF = log2(DW/8)) is
// treated as unmapped -> decode-error response, no slave sees it.
// Purely combinational.
// =============================================================================
`default_nettype none

module sfb_addr_decoder #(
  parameter int              NS          = 4,
  parameter int              AW          = 32,
  parameter int              DW          = 32,
  parameter int              CHECK_ALIGN = 1,
  parameter logic [NS*AW-1:0] SLV_BASE   = {(NS*AW){1'b0}},
  parameter logic [NS*AW-1:0] SLV_MASK   = {(NS*AW){1'b0}},
  parameter logic [NS-1:0]    EN         = {NS{1'b1}},      // sized: see sfb_crossbar
  localparam int             SW          = (NS > 1) ? $clog2(NS) : 1,
  localparam int             OFF         = (DW > 8) ? $clog2(DW / 8) : 1
) (
  input  wire logic [AW-1:0] addr,
  output logic               hit,       // maps to a permitted slave, aligned
  output logic [SW-1:0]      sel,       // slave index (valid when hit)
  output logic [NS-1:0]      sel_oh,    // one-hot slave select (zero when !hit)
  output logic               misaligned
);
  always_comb begin
    hit        = 1'b0;
    sel        = '0;
    sel_oh     = '0;
    misaligned = (CHECK_ALIGN != 0) && (DW > 8) && (addr[OFF-1:0] != '0);
    for (int s = NS - 1; s >= 0; s--) begin
      if (((addr & SLV_MASK[s*AW +: AW]) == SLV_BASE[s*AW +: AW]) && EN[s]) begin
        hit = 1'b1;
        sel = SW'(s);
      end
    end
    if (misaligned) hit = 1'b0;
    if (hit) sel_oh = NS'(1) << sel;
  end
endmodule

`default_nettype wire
