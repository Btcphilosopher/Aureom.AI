// =============================================================================
// SilicaFlux MemoryFlow :: sf_mem_router
// 1-master -> NS-slave address router for the SF-MEM valid/ready protocol.
//
//  * Address decode by [BASE, BASE+SIZE) windows; slaves receive the OFFSET
//    (addr - BASE) so they are base-agnostic.
//  * Unmapped addresses get an error response generated locally (decode error)
//    -- they never reach a slave.
//  * Responses are returned IN ORDER even when slaves have different
//    latencies: an ordering FIFO records the target of every accepted request
//    and only the slave at its head may hand back a response.
//  * MAXOUT bounds outstanding requests (ordering FIFO depth).
// Requirement on slaves: one response per request, in request order.
// Classification: SYNTHESIZABLE
// =============================================================================
`default_nettype none

module sf_mem_router #(
  parameter int NS     = 2,
  parameter int AW     = 32,
  parameter int DW     = 64,
  parameter int MAXOUT = 8,
  parameter logic [NS*AW-1:0] BASES = '0,
  parameter logic [NS*AW-1:0] SIZES = '0,
  localparam int NB    = DW / 8,
  localparam int SIW   = (NS > 1) ? $clog2(NS) : 1
) (
  input  logic             clk,
  input  logic             rst_n,
  // master side
  input  logic             req_valid,
  output logic             req_ready,
  input  logic             req_we,
  input  logic [AW-1:0]    req_addr,
  input  logic [DW-1:0]    req_wdata,
  input  logic [NB-1:0]    req_wstrb,
  output logic             rsp_valid,
  input  logic             rsp_ready,
  output logic [DW-1:0]    rsp_rdata,
  output logic             rsp_err,
  // slave side (flattened)
  output logic [NS-1:0]    s_req_valid,
  input  logic [NS-1:0]    s_req_ready,
  output logic [NS-1:0]    s_req_we,
  output logic [NS*AW-1:0] s_req_addr,
  output logic [NS*DW-1:0] s_req_wdata,
  output logic [NS*NB-1:0] s_req_wstrb,
  input  logic [NS-1:0]    s_rsp_valid,
  output logic [NS-1:0]    s_rsp_ready,
  input  logic [NS*DW-1:0] s_rsp_rdata,
  input  logic [NS-1:0]    s_rsp_err
);
  // ---------------------------------------------------------------- decode
  logic [NS-1:0]  hit;
  logic [SIW-1:0] tgt;
  logic           any_hit;

  always_comb begin
    for (int s = 0; s < NS; s++) begin
      hit[s] = (req_addr >= BASES[s*AW +: AW]) &&
               ((req_addr - BASES[s*AW +: AW]) < SIZES[s*AW +: AW]);
    end
    tgt     = '0;
    any_hit = 1'b0;
    for (int s = NS - 1; s >= 0; s--) begin
      if (hit[s]) begin
        tgt     = SIW'(s);
        any_hit = 1'b1;
      end
    end
  end

  // ---------------------------------------------------------------- order FIFO
  logic           of_push_ready, of_pop_valid;
  logic [SIW:0]   of_head;                 // {is_decode_err, target}
  logic           of_pop;
  logic [$clog2(MAXOUT+1)-1:0] of_cnt_unused;

  wire tgt_ready = any_hit ? s_req_ready[tgt] : 1'b1;
  assign req_ready = of_push_ready && tgt_ready;
  wire accept      = req_valid && req_ready;

  sf_fifo #(.WIDTH(SIW + 1), .DEPTH(MAXOUT)) u_order (
    .clk, .rst_n,
    .push_valid(accept), .push_ready(of_push_ready), .push_data({~any_hit, tgt}),
    .pop_valid(of_pop_valid), .pop_ready(of_pop), .pop_data(of_head),
    .count(of_cnt_unused)
  );

  // ---------------------------------------------------------------- request fan-out
  always_comb begin
    for (int s = 0; s < NS; s++) begin
      s_req_valid[s]           = req_valid && any_hit && (tgt == SIW'(s)) && of_push_ready;
      s_req_we[s]              = req_we;
      s_req_addr[s*AW +: AW]   = req_addr - BASES[s*AW +: AW];
      s_req_wdata[s*DW +: DW]  = req_wdata;
      s_req_wstrb[s*NB +: NB]  = req_wstrb;
    end
  end

  // ---------------------------------------------------------------- response mux
  wire           h_err = of_head[SIW];
  wire [SIW-1:0] h_tgt = of_head[SIW-1:0];

  always_comb begin
    s_rsp_ready = '0;
    rsp_valid   = 1'b0;
    rsp_rdata   = '0;
    rsp_err     = 1'b0;
    if (of_pop_valid) begin
      if (h_err) begin
        rsp_valid = 1'b1;
        rsp_err   = 1'b1;
      end else begin
        rsp_valid          = s_rsp_valid[h_tgt];
        rsp_rdata          = s_rsp_rdata[h_tgt*DW +: DW];
        rsp_err            = s_rsp_err[h_tgt];
        s_rsp_ready[h_tgt] = rsp_ready;
      end
    end
  end

  assign of_pop = rsp_valid && rsp_ready;

endmodule

`default_nettype wire
