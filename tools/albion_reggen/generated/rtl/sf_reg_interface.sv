// =============================================================================
//  sf_reg_interface.sv -- ALP v1 target link with stall-safe response slice
//  GENERATED FILE -- DO NOT EDIT.  Edit the register definition instead.
//  generator       : albion_reggen 1.0.0 (definition schema 1)
//  register map   : silicaflux_regs v1.0
//  semantic hash  : 99481283139d2dc0690f688325c0631d115617fc66330be250e7a560f5e43d39
//  definition hash: 322ccd28a62e3936e355677a25425f8609977deab94841f7ce2049bcd96525ba
//  Bus protocol    : Albion Link Protocol v1 (AlbionCore sf_albion_pkg)
// =============================================================================
`default_nettype none

// ALP v1 target front end for a register bank.
//
//   * req_ready_o = !rsp_valid_q || rsp_ready_i.  It depends only on registered state and on the
//     response channel's ready (a ready chain, ALP-REQ-03); never on req_valid_i or the payload.
//   * A request is ACCEPTED in the cycle req_valid_i && req_ready_o.  Accepting is the single commit
//     point: acc_valid_o is high for exactly that cycle, so register side effects occur exactly once.
//     A request that is stalled (valid && !ready) has no effect at all and is simply held by the
//     initiator (ALP-REQ-02).
//   * The response is registered: visible one cycle after acceptance at the earliest (ALP-RSP-03),
//     held with an unchanged payload until accepted (ALP-RSP-02).  A response that is not taken
//     therefore never re-triggers anything and never loses read data.
//   * Because a new request is accepted on the same edge on which the previous response leaves,
//     the link can have two requests in flight at the start of a cycle's accounting: the capacity
//     advertised to the fabric is sf_reg_pkg::SF_REG_MAX_OUTSTANDING (= 2).
//   * Response format (ALP-RSP-05): tag echo, meta.last = 1, meta.is_write from the request, data is
//     all-zero for writes and for every non-OKAY status, lanes not enabled by the request are zero.
module sf_reg_interface (
  input  wire logic                                  clk_i,
  input  wire logic                                  rst_ni,
  // ALP request channel
  input  wire logic                                  req_valid_i,
  output logic                                       req_ready_o,
  input  sf_albion_pkg::sf_req_t                     req_i,
  // ALP response channel
  output logic                                       rsp_valid_o,
  input  wire logic                                  rsp_ready_i,
  output sf_albion_pkg::sf_rsp_t                     rsp_o,
  // internal access port (to sf_reg_bank)
  output logic                                       acc_valid_o,   // request accepted this cycle
  output logic [sf_albion_pkg::SF_REQ_W-1:0]         acc_req_o,     // the request on the wire (valid with acc_valid_o)
  output logic [sf_albion_pkg::SF_STATUS_W-1:0]      acc_legal_o,   // ALP legality status of that request
  input  wire logic [sf_albion_pkg::SF_STATUS_W-1:0] acc_status_i,  // final status (combinational, same cycle)
  input  wire logic [sf_albion_pkg::SF_DATA_W-1:0]   acc_rdata_i    // read data, already lane-masked
);
  logic                   rsp_valid_q;
  sf_albion_pkg::sf_rsp_t rsp_q;
  sf_albion_pkg::sf_rsp_t rsp_d;

  assign req_ready_o = !rsp_valid_q || rsp_ready_i;
  assign acc_valid_o = req_valid_i && req_ready_o;
  assign acc_req_o   = req_i;
  assign acc_legal_o = sf_albion_pkg::sf_req_check_bits(acc_req_o);

  always_comb begin
    rsp_d               = '0;
    rsp_d.tag           = req_i.tag;
    rsp_d.status        = acc_status_i;
    rsp_d.meta.last     = 1'b1;
    rsp_d.meta.is_write = (req_i.op == sf_albion_pkg::SF_OP_WRITE);
    if ((acc_status_i == sf_albion_pkg::SF_ST_OKAY) && (req_i.op == sf_albion_pkg::SF_OP_READ))
      rsp_d.data = acc_rdata_i;
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      rsp_valid_q <= 1'b0;
      rsp_q       <= '0;
    end else if (acc_valid_o) begin
      rsp_valid_q <= 1'b1;
      rsp_q       <= rsp_d;
    end else if (rsp_ready_i) begin
      rsp_valid_q <= 1'b0;
    end
  end

  assign rsp_valid_o = rsp_valid_q;
  assign rsp_o       = rsp_q;
endmodule

`default_nettype wire
