// =============================================================================
// SilicaFlux DataFabric :: sfb_v1_slave_adapter -- legacy SFB slave on SFB2
//
// Connects an unmodified SilicaFlux-V SFB slave (req/gnt, rvalid/rdata/err,
// no response back-pressure: silicaflux-v docs/BUS.md) to an SFB2 slave port
// (32-bit data).  The legacy slave produces its response whether or not the
// master can take it; if rsp_ready is low in that cycle the response is parked
// in a one-entry holding register and presented (stable) until accepted.
// While a response is parked, no new request is passed to the legacy slave
// (req_ready = 0), so at most one response is ever in flight per adapter.
// Mapping: req_valid->req (gated), gnt->req_ready, req_write->we,
//          req_wstrb->be, rsp_* <- rvalid/rdata/err (or the parked copy).
// Cost: 34 flops (+ control).  Latency: none added.
// =============================================================================
`default_nettype none

module sfb_v1_slave_adapter (
  input  wire logic        clk,
  input  wire logic        rst_n,
  // SFB2 slave port (from the crossbar)
  input  wire logic        req_valid,
  output logic             req_ready,
  input  wire logic        req_write,
  input  wire logic [31:0] req_addr,
  input  wire logic [31:0] req_wdata,
  input  wire logic [3:0]  req_wstrb,
  output logic             rsp_valid,
  input  wire logic        rsp_ready,
  output logic [31:0]      rsp_rdata,
  output logic             rsp_error,
  // legacy SFB master port (to the unmodified slave)
  output logic             v1_req,
  input  wire logic        v1_gnt,
  output logic [31:0]      v1_addr,
  output logic             v1_we,
  output logic [3:0]       v1_be,
  output logic [31:0]      v1_wdata,
  input  wire logic        v1_rvalid,
  input  wire logic [31:0] v1_rdata,
  input  wire logic        v1_err
);
  logic        hold_q, herr_q;
  logic [31:0] hdata_q;

  assign v1_req    = req_valid && !hold_q;
  assign req_ready = v1_gnt && !hold_q;
  assign v1_addr   = req_addr;
  assign v1_we     = req_write;
  assign v1_be     = req_wstrb;
  assign v1_wdata  = req_wdata;

  assign rsp_valid = hold_q || v1_rvalid;
  assign rsp_rdata = hold_q ? hdata_q : v1_rdata;
  assign rsp_error = hold_q ? herr_q  : v1_err;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      hold_q <= 1'b0;
    end else if (hold_q) begin
      if (rsp_ready) hold_q <= 1'b0;
    end else if (v1_rvalid && !rsp_ready) begin
      hold_q <= 1'b1;
    end
  end

  always_ff @(posedge clk) begin
    if (!hold_q && v1_rvalid && !rsp_ready) begin
      hdata_q <= v1_rdata;
      herr_q  <= v1_err;
    end
  end
endmodule

`default_nettype wire
