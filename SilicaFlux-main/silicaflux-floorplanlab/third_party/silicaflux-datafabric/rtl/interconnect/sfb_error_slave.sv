// =============================================================================
// SilicaFlux DataFabric :: sfb_error_slave -- default (decode-error) slave
//
// A complete SFB2 slave that answers every request with rsp_error = 1 and
// rsp_rdata = 0, one cycle after acceptance, and has no side effect.  The
// crossbar instantiates one per master port as the target of unmapped,
// access-matrix-denied and misaligned requests; it can also terminate an
// unused slave port of a shared bus.
//   req_ready = !pending || rsp_ready   (one response buffered; full throughput)
//   rsp_valid = pending (registered; held until rsp_ready)
// =============================================================================
`default_nettype none

module sfb_error_slave #(
  parameter int DW = 32
) (
  input  wire logic          clk,
  input  wire logic          rst_n,
  input  wire logic          req_valid,
  output logic               req_ready,
  output logic               rsp_valid,
  input  wire logic          rsp_ready,
  output logic [DW-1:0]      rsp_rdata,
  output logic               rsp_error
);
  logic pend_q;
  assign req_ready = !pend_q || rsp_ready;
  assign rsp_valid = pend_q;
  assign rsp_rdata = '0;
  assign rsp_error = pend_q;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) pend_q <= 1'b0;
    else        pend_q <= (req_valid && req_ready) || (pend_q && !rsp_ready);
  end
endmodule

`default_nettype wire
