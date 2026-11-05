// =============================================================================
// SilicaFlux MemoryFlow :: sf_mc25_vport_bridge
// SF-MEM read + write slave  ->  SilicaFlux 2.5 memory_controller VECTOR port
//
// Lets MemoryFlow masters (sf_dma, sf_mem_router) use the EXISTING SilicaFlux
// 2.5 banked scratchpad (memory_controller.sf) unmodified, at its full
// 128-bit / 1-request-per-cycle vector-port rate.
//
//  * Addresses arrive as offsets (sf_mem_router convention); SPM_BASE is added.
//  * Reads and writes share the single vector port, round-robin arbitrated.
//  * The vector port returns ONE in-order response stream for both kinds.  If
//    that stream were back-pressured by one consumer it would block the other
//    (head-of-line), and a DMA that stops accepting read data until its write
//    acknowledgements return deadlocks.  The bridge therefore reserves a slot
//    in the matching response FIFO before it issues a request (credits) and
//    never back-pressures the controller: v_rsp_ready is tied high.
//  * Byte strobes must be lane-granular (each 32-bit lane all-on or all-off),
//    the granularity of the vector port's lane mask.  A write with a partial
//    lane is sent with lane_mask = 0 (writes nothing, keeps ordering) and
//    answered with err = 1; cnt_strobe_err counts them.  (A production bridge
//    would split it into scalar-port read-modify-writes.)
//  * Controller exceptions (range, domain, misalign, parity) -> err = 1.
// Request tag: [0] = write, [1] = poisoned (partial-lane write).
// Classification: SYNTHESIZABLE
// =============================================================================
`default_nettype none
module sf_mc25_vport_bridge
  import silicaflux_pkg::*;
#(
  parameter logic [31:0] SPM_BASE = 32'h1000_0000,
  parameter int          RD_DEPTH = 4,      // read-data buffering (>= controller round trip for full rate)
  parameter int          WR_DEPTH = 4,
  localparam int         DW       = SF_VLEN,
  localparam int         NB       = DW / 8
) (
  input  logic                 clk,
  input  logic                 rst_n,
  // SF-MEM read slave
  input  logic                 rd_req_valid,
  output logic                 rd_req_ready,
  input  logic [31:0]          rd_req_addr,
  output logic                 rd_rsp_valid,
  input  logic                 rd_rsp_ready,
  output logic [DW-1:0]        rd_rsp_rdata,
  output logic                 rd_rsp_err,
  // SF-MEM write slave
  input  logic                 wr_req_valid,
  output logic                 wr_req_ready,
  input  logic [31:0]          wr_req_addr,
  input  logic [DW-1:0]        wr_req_wdata,
  input  logic [NB-1:0]        wr_req_wstrb,
  output logic                 wr_rsp_valid,
  input  logic                 wr_rsp_ready,
  output logic                 wr_rsp_err,
  // SilicaFlux 2.5 memory_controller vector port
  output logic                 v_req_valid,
  input  logic                 v_req_ready,
  output sf_vector_mem_req_t   v_req,
  input  logic                 v_rsp_valid,
  output logic                 v_rsp_ready,
  input  sf_vector_mem_rsp_t   v_rsp,
  // status
  output logic [31:0]          cnt_strobe_err
);
  localparam int RCW = $clog2(RD_DEPTH + 1);
  localparam int WCW = $clog2(WR_DEPTH + 1);

  // ---------------------------------------------------------------- credits
  // reserved = in flight in the controller + waiting in the response FIFO
  logic [RCW-1:0] rd_res;
  logic [WCW-1:0] wr_res;
  wire rd_cred = (rd_res != RCW'(RD_DEPTH));
  wire wr_cred = (wr_res != WCW'(WR_DEPTH));

  // ---------------------------------------------------------------- arbitration
  logic last_wr;                                   // round-robin pointer
  wire  want_rd = rd_req_valid & rd_cred;
  wire  want_wr = wr_req_valid & wr_cred;
  wire  pick_wr = want_wr & (~want_rd | ~last_wr);
  wire  pick_rd = want_rd & ~pick_wr;

  // lane mask from byte strobes; poisoned if any lane is partially strobed
  logic [SF_VLANES-1:0] lmask;
  logic                 partial;
  always_comb begin
    partial = 1'b0;
    for (int l = 0; l < SF_VLANES; l++) begin
      lmask[l] = &wr_req_wstrb[l*SF_XBYTES +: SF_XBYTES];
      partial |= (|wr_req_wstrb[l*SF_XBYTES +: SF_XBYTES]) & ~lmask[l];
    end
  end

  always_comb begin
    v_req           = '0;
    v_req.hint      = SF_MEM_HINT_STREAM;
    if (pick_wr) begin
      v_req.op        = SF_MEM_STORE;
      v_req.addr      = SPM_BASE + wr_req_addr;
      v_req.wdata     = wr_req_wdata;
      v_req.lane_mask = partial ? '0 : lmask;
      v_req.tag       = {6'b0, partial, 1'b1};
    end else begin
      v_req.op        = SF_MEM_LOAD;
      v_req.addr      = SPM_BASE + rd_req_addr;
      v_req.lane_mask = '1;
      v_req.tag       = 8'h00;
    end
  end
  assign v_req_valid  = pick_wr | pick_rd;
  assign rd_req_ready = pick_rd & v_req_ready;
  assign wr_req_ready = pick_wr & v_req_ready;
  wire   rd_issue     = rd_req_valid & rd_req_ready;
  wire   wr_issue     = wr_req_valid & wr_req_ready;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n)                       last_wr <= 1'b0;
    else if (rd_issue | wr_issue)     last_wr <= wr_issue;
  end

  // ---------------------------------------------------------------- responses
  assign v_rsp_ready = 1'b1;                       // space is reserved by credit
  wire   rsp_wr      = v_rsp_valid & v_rsp.tag[0];
  wire   rsp_rd      = v_rsp_valid & ~v_rsp.tag[0];
  wire   rsp_err     = (v_rsp.exc != SF_MEM_EXC_NONE) | v_rsp.tag[1];

  logic rf_push_rdy, wf_push_rdy, rf_pop, wf_pop;
  logic [DW:0] rf_q;
  logic        wf_q;
  sf_fifo #(.WIDTH(DW + 1), .DEPTH(RD_DEPTH)) u_rf (
    .clk, .rst_n, .push_valid(rsp_rd), .push_ready(rf_push_rdy), .push_data({rsp_err, v_rsp.rdata}),
    .pop_valid(rd_rsp_valid), .pop_ready(rd_rsp_ready), .pop_data(rf_q), .count());
  sf_fifo #(.WIDTH(1), .DEPTH(WR_DEPTH)) u_wf (
    .clk, .rst_n, .push_valid(rsp_wr), .push_ready(wf_push_rdy), .push_data(rsp_err),
    .pop_valid(wr_rsp_valid), .pop_ready(wr_rsp_ready), .pop_data(wf_q), .count());
  assign rd_rsp_rdata = rf_q[DW-1:0];
  assign rd_rsp_err   = rf_q[DW];
  assign wr_rsp_err   = wf_q;
  assign rf_pop       = rd_rsp_valid & rd_rsp_ready;
  assign wf_pop       = wr_rsp_valid & wr_rsp_ready;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      rd_res <= '0; wr_res <= '0; cnt_strobe_err <= '0;
    end else begin
      rd_res <= rd_res + RCW'(rd_issue) - RCW'(rf_pop);
      wr_res <= wr_res + WCW'(wr_issue) - WCW'(wf_pop);
      if (wr_issue && partial) cnt_strobe_err <= cnt_strobe_err + 32'd1;
    end
  end

`ifndef SYNTHESIS
  // credit discipline: a response always finds room (otherwise it would be lost)
  always_ff @(posedge clk) if (rst_n) begin
    if (rsp_rd) assert (rf_push_rdy) else $error("sf_mc25_vport_bridge: read response overflow");
    if (rsp_wr) assert (wf_push_rdy) else $error("sf_mc25_vport_bridge: write response overflow");
  end
`endif
endmodule
`default_nettype wire
