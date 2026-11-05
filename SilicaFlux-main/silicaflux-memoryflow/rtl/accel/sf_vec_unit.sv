// =============================================================================
// SilicaFlux MemoryFlow :: sf_vec_unit
// Streaming SIMD vector unit: LANES = DW/EW signed lanes per beat.
//
//   OP 0 ADD  : r = a + b                (lane-wise, wraps at EW bits)
//   OP 1 MUL  : r = a * b                (lane-wise, low EW bits)
//   OP 2 DOT  : acc += sum_l a_l * b_l   one result beat (64-bit signed,
//                                         low DW bits) emitted on a_last
//   OP 3 AXPY : r = alpha * a + b        (lane-wise, low EW bits)
//
// Two operand streams are JOINED: a beat is consumed only when both A and B
// heads are valid.  Each input has an elastic FIFO of IN_FIFO beats.  When the
// two operands are delivered by one DMA engine in alternating bursts, IN_FIFO
// must be >= the DMA burst length, otherwise the producer blocks on one
// stream while the consumer waits on the other -> DEADLOCK.  This is a real
// producer/consumer hazard exercised by tb_dataflow_deadlock.
//
// Perf: cnt_active (beats computed), cnt_starve (exactly one operand ready),
//       cnt_ostall (result ready but sink not ready).
// Classification: SYNTHESIZABLE
// =============================================================================
`default_nettype none

module sf_vec_unit #(
  parameter int DW      = 64,
  parameter int EW      = 16,
  parameter int IN_FIFO = 16,
  localparam int LANES  = DW / EW
) (
  input  logic          clk,
  input  logic          rst_n,
  input  logic [1:0]    cfg_op,
  input  logic [EW-1:0] cfg_alpha,
  input  logic          perf_clear,
  // operand A
  input  logic          a_valid,
  output logic          a_ready,
  input  logic [DW-1:0] a_data,
  input  logic          a_last,
  // operand B
  input  logic          b_valid,
  output logic          b_ready,
  input  logic [DW-1:0] b_data,
  // result
  output logic          r_valid,
  input  logic          r_ready,
  output logic [DW-1:0] r_data,
  output logic          r_last,
  // perf
  output logic [31:0]   cnt_active,
  output logic [31:0]   cnt_starve,
  output logic [31:0]   cnt_ostall
);
  localparam int CW = $clog2(IN_FIFO + 1);

  logic          fa_valid, fb_valid, fa_pop, fb_pop;
  logic [DW:0]   fa_dout;
  logic [DW-1:0] fb_dout;
  logic [CW-1:0] fa_cnt_unused, fb_cnt_unused;

  sf_fifo #(.WIDTH(DW + 1), .DEPTH(IN_FIFO)) u_fa (
    .clk, .rst_n, .push_valid(a_valid), .push_ready(a_ready), .push_data({a_last, a_data}),
    .pop_valid(fa_valid), .pop_ready(fa_pop), .pop_data(fa_dout), .count(fa_cnt_unused));
  sf_fifo #(.WIDTH(DW), .DEPTH(IN_FIFO)) u_fb (
    .clk, .rst_n, .push_valid(b_valid), .push_ready(b_ready), .push_data(b_data),
    .pop_valid(fb_valid), .pop_ready(fb_pop), .pop_data(fb_dout), .count(fb_cnt_unused));

  wire          both = fa_valid && fb_valid;
  wire          hl   = fa_dout[DW];
  wire [DW-1:0] ha   = fa_dout[DW-1:0];
  wire [DW-1:0] hb   = fb_dout;

  // lane-wise datapath
  logic [DW-1:0]      ew_res;
  logic signed [63:0] lane_prod [LANES];
  logic signed [63:0] dot_beat;
  genvar gl;
  generate
    for (gl = 0; gl < LANES; gl++) begin : g_lane
      wire signed [EW-1:0]   xa   = ha[gl*EW +: EW];
      wire signed [EW-1:0]   xb   = hb[gl*EW +: EW];
      wire signed [2*EW-1:0] prod = xa * xb;
      wire signed [EW-1:0]   ax   = $signed(cfg_alpha) * xa;   // low EW bits
      assign lane_prod[gl] = 64'(prod);
      always_comb begin
        case (cfg_op)
          2'd0:    ew_res[gl*EW +: EW] = xa + xb;
          2'd1:    ew_res[gl*EW +: EW] = prod[EW-1:0];
          default: ew_res[gl*EW +: EW] = ax + xb;
        endcase
      end
    end
  endgenerate
  always_comb begin
    dot_beat = '0;
    for (int l = 0; l < LANES; l++) dot_beat = dot_beat + lane_prod[l];
  end

  // DOT accumulator
  logic signed [63:0] acc;
  wire is_dot = (cfg_op == 2'd2);

  // output skid
  logic          o_s_valid, o_s_ready;
  logic [DW:0]   o_s_data, o_m_data;
  sf_skid_buffer #(.WIDTH(DW + 1)) u_out (
    .clk, .rst_n, .s_valid(o_s_valid), .s_ready(o_s_ready), .s_data(o_s_data),
    .m_valid(r_valid), .m_ready(r_ready), .m_data(o_m_data));
  assign r_data = o_m_data[DW-1:0];
  assign r_last = o_m_data[DW];

  logic signed [63:0] acc_next;
  assign acc_next = acc + dot_beat;

  always_comb begin
    o_s_valid = 1'b0;
    o_s_data  = {hl, ew_res};
    if (both) begin
      if (!is_dot) o_s_valid = 1'b1;
      else if (hl) begin
        o_s_valid = 1'b1;
        o_s_data  = {1'b1, DW'(acc_next)};
      end
    end
  end

  // consume when the result (if any) can be accepted
  wire fire = both && (o_s_ready || (is_dot && !hl));
  assign fa_pop = fire;
  assign fb_pop = fire;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      acc        <= '0;
      cnt_active <= '0;
      cnt_starve <= '0;
      cnt_ostall <= '0;
    end else begin
      if (fire && is_dot) acc <= hl ? '0 : acc_next;
      if (perf_clear) begin
        cnt_active <= '0;
        cnt_starve <= '0;
        cnt_ostall <= '0;
      end else begin
        if (fire)                  cnt_active <= cnt_active + 32'd1;
        if (fa_valid ^ fb_valid)   cnt_starve <= cnt_starve + 32'd1;
        if (r_valid && !r_ready)   cnt_ostall <= cnt_ostall + 32'd1;
      end
    end
  end

endmodule

`default_nettype wire
