// =============================================================================
//  sf_albion_link_checker.sv  --  Albion Link Protocol (ALP v1) checker
// -----------------------------------------------------------------------------
//  Passive monitor for one initiator <-> target link (request channel +
//  response channel).  Each rule is an immediate assertion whose label starts
//  with the contract rule id it enforces, e.g. a_alp_ord_01.  The traceability
//  tool (tools/albion/build/contract_trace.py) requires every rule id of the contract
//  that is classified as "checker" to appear in this file.
//
//  Rules checked
//    ALP-REQ-02  request valid/payload held until accepted   (chan checker)
//    ALP-RSP-02  response valid/payload held until accepted  (chan checker)
//    ALP-OUT-01  accepted requests never exceed MAX_OUTSTANDING
//    ALP-TAG-01  a tag is not reused while its transaction is outstanding
//    ALP-RSP-03  a response never appears without an earlier accepted request
//                (this also enforces the minimum latency of one cycle)
//    ALP-ORD-01  responses return in request-acceptance order
//    ALP-TAG-02  the response tag equals the request tag     (same assertion as ALP-ORD-01: a_alp_ord_01)
//    ALP-RSP-04  the response operation (read/write) equals the request's
//    ALP-RSP-05  responses are well-formed (sf_rsp_wellformed)
//    ALP-RSP-07  a read response carries zero in every byte lane that was not enabled
//    ALP-LEG-01  an illegal request is answered with its legality status
//    ALP-RST-01  valids are low while reset is asserted
//    ALP-RST-02  reset abandons all outstanding transactions (counter cleared)
//
//  Modes (formal): ASSUME_REQ / ASSUME_RSP turn the initiator-side / target-side
//  obligations into assumptions so a component can be proven against its
//  environment.  In simulation both are 0 and every rule is asserted.
//
//  Written in the synthesizable subset (no queues, no strings) so that the same
//  module runs in Verilator and in Yosys formal.
// =============================================================================
`default_nettype none

module sf_albion_link_checker #(
  parameter int unsigned MAX_OUTSTANDING = 8,
  parameter bit          CHECK_LEGALITY  = 1'b1,
  parameter bit          CHECK_LANES     = 1'b1,     // ALP-RSP-07 (needs the request byte enables)
  parameter bit          ASSUME_REQ      = 1'b0,
  parameter bit          ASSUME_RSP      = 1'b0
) (
  input wire logic                  clk_i,
  input wire logic                  rst_ni,
  input wire logic                  req_valid_i,
  input wire logic                  req_ready_i,
  input sf_albion_pkg::sf_req_t     req_i,
  input wire logic                  rsp_valid_i,
  input wire logic                  rsp_ready_i,
  input sf_albion_pkg::sf_rsp_t     rsp_i,
  input wire logic                  waive_req_i,   // flush exception for the request channel
  output logic [15:0]               outstanding_o
);
  localparam int unsigned CNT_W = $clog2(MAX_OUTSTANDING + 1);
  localparam int unsigned PTR_W = (MAX_OUTSTANDING > 1) ? $clog2(MAX_OUTSTANDING) : 1;

  if (MAX_OUTSTANDING < 1 || MAX_OUTSTANDING > sf_albion_pkg::SF_MAX_OUTSTANDING_LIMIT) begin : gen_param_check
    $error("sf_albion_link_checker: MAX_OUTSTANDING out of range");
  end

  // ---------------------------------------------------------------------------
  // Channel stability rules
  // ---------------------------------------------------------------------------
  sf_albion_chan_checker #(.WIDTH(sf_albion_pkg::SF_REQ_W), .ASSUME_MODE(ASSUME_REQ)) u_req_chan (
    .clk_i, .rst_ni,
    .valid_i   (req_valid_i),
    .ready_i   (req_ready_i),
    .payload_i (req_i),
    .waive_i   (waive_req_i)
  );

  sf_albion_chan_checker #(.WIDTH(sf_albion_pkg::SF_RSP_W), .ASSUME_MODE(ASSUME_RSP)) u_rsp_chan (
    .clk_i, .rst_ni,
    .valid_i   (rsp_valid_i),
    .ready_i   (rsp_ready_i),
    .payload_i (rsp_i),
    .waive_i   (1'b0)
  );

  // ---------------------------------------------------------------------------
  // Outstanding-transaction bookkeeping
  // ---------------------------------------------------------------------------
  logic [CNT_W-1:0]                  cnt_q;
  logic [PTR_W-1:0]                  wr_ptr_q;
  logic [PTR_W-1:0]                  rd_ptr_q;
  logic [sf_albion_pkg::SF_TAG_W-1:0] q_tag     [MAX_OUTSTANDING];
  logic                              q_is_write [MAX_OUTSTANDING];
  logic [sf_albion_pkg::SF_STATUS_W-1:0] q_legal [MAX_OUTSTANDING];
  logic [sf_albion_pkg::SF_BE_W-1:0]  q_be       [MAX_OUTSTANDING];
  logic [sf_albion_pkg::SF_MAX_OUTSTANDING_LIMIT-1:0] busy_q;

  logic req_acc;
  logic rsp_acc;
  assign req_acc = req_valid_i && req_ready_i;
  assign rsp_acc = rsp_valid_i && rsp_ready_i;

  logic [sf_albion_pkg::SF_TAG_W-1:0]    head_tag;
  logic                                  head_is_write;
  logic [sf_albion_pkg::SF_STATUS_W-1:0] head_legal;
  logic [sf_albion_pkg::SF_DATA_W-1:0]   head_unsel;      // data bits of the byte lanes NOT enabled by the oldest request
  logic [sf_albion_pkg::SF_STATUS_W-1:0] req_legal;

  assign head_tag      = q_tag[rd_ptr_q];
  assign head_is_write = q_is_write[rd_ptr_q];
  assign head_legal    = q_legal[rd_ptr_q];
  always_comb begin
    for (int unsigned b = 0; b < sf_albion_pkg::SF_BE_W; b++) head_unsel[b*8 +: 8] = {8{!q_be[rd_ptr_q][b]}};
  end
  assign req_legal     = sf_albion_pkg::sf_req_check_bits(req_i);

  assign outstanding_o = 16'(cnt_q);

  function automatic logic [PTR_W-1:0] ptr_inc(input logic [PTR_W-1:0] p);
    if (p == PTR_W'(MAX_OUTSTANDING - 1)) ptr_inc = '0;
    else                                   ptr_inc = p + 1'b1;
  endfunction

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      cnt_q    <= '0;
      wr_ptr_q <= '0;
      rd_ptr_q <= '0;
      busy_q   <= '0;
    end else begin
      if (req_acc) begin
        q_tag[wr_ptr_q]      <= req_i.tag;
        q_is_write[wr_ptr_q] <= (req_i.op == sf_albion_pkg::SF_OP_WRITE);
        q_legal[wr_ptr_q]    <= req_legal;
        q_be[wr_ptr_q]       <= req_i.be;
        wr_ptr_q             <= ptr_inc(wr_ptr_q);
        busy_q[req_i.tag]    <= 1'b1;
      end
      if (rsp_acc && cnt_q != '0) begin
        rd_ptr_q          <= ptr_inc(rd_ptr_q);
        busy_q[head_tag]  <= 1'b0;
      end
      // An accepted request and an accepted response in the same cycle: the
      // new request must not have reused the tag being retired (ALP-TAG-01
      // is evaluated against busy_q before the edge), so the two updates to
      // busy_q never target the same bit.
      if (req_acc && !(rsp_acc && cnt_q != '0)) cnt_q <= cnt_q + 1'b1;
      else if (!req_acc && (rsp_acc && cnt_q != '0)) cnt_q <= cnt_q - 1'b1;
    end
  end

  // ---------------------------------------------------------------------------
  // Rules
  // ---------------------------------------------------------------------------
  logic cnt_nonzero;
  assign cnt_nonzero = (cnt_q != '0);

  if (ASSUME_REQ) begin : gen_req_assume
    always_ff @(posedge clk_i) begin
      if (rst_ni) begin
        a_alp_out_01: assume (!req_acc || (cnt_q < CNT_W'(MAX_OUTSTANDING)));
        a_alp_tag_01: assume (!req_acc || !busy_q[req_i.tag]);
      end
    end
  end else begin : gen_req_assert
    always_ff @(posedge clk_i) begin
      if (rst_ni) begin
        a_alp_out_01: assert (!req_acc || (cnt_q < CNT_W'(MAX_OUTSTANDING)));
        a_alp_tag_01: assert (!req_acc || !busy_q[req_i.tag]);
      end
    end
  end

  if (ASSUME_RSP) begin : gen_rsp_assume
    always_ff @(posedge clk_i) begin
      if (rst_ni) begin
        a_alp_rsp_03: assume (!rsp_valid_i || cnt_nonzero);
        a_alp_ord_01: assume (!rsp_valid_i || !cnt_nonzero || (rsp_i.tag == head_tag));
        a_alp_rsp_04: assume (!rsp_valid_i || !cnt_nonzero || (rsp_i.meta.is_write == head_is_write));
        a_alp_rsp_05: assume (!rsp_valid_i || sf_albion_pkg::sf_rsp_wellformed_bits(rsp_i));
        a_alp_rsp_07: assume (!CHECK_LANES || !rsp_valid_i || !cnt_nonzero || ((rsp_i.data & head_unsel) == '0));
        a_alp_leg_01: assume (!CHECK_LEGALITY || !rsp_valid_i || !cnt_nonzero ||
                              (head_legal == sf_albion_pkg::SF_ST_OKAY) || (rsp_i.status == head_legal));
      end
    end
  end else begin : gen_rsp_assert
    always_ff @(posedge clk_i) begin
      if (rst_ni) begin
        a_alp_rsp_03: assert (!rsp_valid_i || cnt_nonzero);
        a_alp_ord_01: assert (!rsp_valid_i || !cnt_nonzero || (rsp_i.tag == head_tag));
        a_alp_rsp_04: assert (!rsp_valid_i || !cnt_nonzero || (rsp_i.meta.is_write == head_is_write));
        a_alp_rsp_05: assert (!rsp_valid_i || sf_albion_pkg::sf_rsp_wellformed_bits(rsp_i));
        a_alp_rsp_07: assert (!CHECK_LANES || !rsp_valid_i || !cnt_nonzero || ((rsp_i.data & head_unsel) == '0));
        a_alp_leg_01: assert (!CHECK_LEGALITY || !rsp_valid_i || !cnt_nonzero ||
                              (head_legal == sf_albion_pkg::SF_ST_OKAY) || (rsp_i.status == head_legal));
      end
    end
  end

  // ALP-RST-01 / ALP-RST-02.  Checked on every clock edge while reset is low.
  if (ASSUME_REQ) begin : gen_rst_req_assume
    always_ff @(posedge clk_i) begin
      a_alp_rst_01_req: assume (rst_ni || !req_valid_i);
    end
  end else begin : gen_rst_req_assert
    always_ff @(posedge clk_i) begin
      a_alp_rst_01_req: assert (rst_ni || !req_valid_i);
    end
  end

  if (ASSUME_RSP) begin : gen_rst_rsp_assume
    always_ff @(posedge clk_i) begin
      a_alp_rst_01_rsp: assume (rst_ni || !rsp_valid_i);
    end
  end else begin : gen_rst_rsp_assert
    always_ff @(posedge clk_i) begin
      a_alp_rst_01_rsp: assert (rst_ni || !rsp_valid_i);
      a_alp_rst_02:     assert (rst_ni || (cnt_q == '0));
    end
  end
endmodule

`default_nettype wire
