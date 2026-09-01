// sha256_compressor.sv -- ITERATIVE SHA-256 compression core.
//
// One round per clock cycle via a round-counter FSM: `sha256_round` is
// instantiated ONCE and its output is registered back into {a..h} each
// cycle, driven by `sha256_message_schedule` in SLIDING_WINDOW mode
// (one new W[t] per cycle). A single block compression takes exactly 64
// clock cycles of active computation (plus the start/done edges).
//
// This is the minimum-area core micro-architecture (silicaflux.
// architecture.spec.CoreArchitecture.ITERATIVE): 1 round-function
// instance, 1 message-schedule instance, 8 state registers -- versus
// sha256_pipeline.sv's 64 spatially-unrolled round instances. Throughput
// is recovered by replicating many of these cheap cores in
// hash_core_array.sv rather than by unrolling any individual core.
//
// state_in/state_out are the 8-word SHA-256 state (word 0 = MSB). For a
// fresh hash, feed state_in = the fixed IV (see hash_core.sv, which owns
// the actual H0 constant); to continue from a previous block (including
// a pre-computed midstate), feed state_in = that block's state_out.
// block_bits is the 512-bit message block, word 0 = bits [511:480].
module sha256_compressor (
  input  logic         clk,
  input  logic         rst_n,
  input  logic         start,       // pulse: begin compressing block_bits from state_in
  input  logic [255:0] state_in,
  input  logic [511:0] block_bits,
  output logic         busy,
  output logic         done,        // one-cycle pulse; state_out valid this cycle and held after
  output logic [255:0] state_out
);

  typedef enum logic [0:0] { ST_IDLE, ST_RUN } state_e;
  state_e state_r;

  logic [31:0] a_r, b_r, c_r, d_r, e_r, f_r, g_r, h_r;
  logic [31:0] save0, save1, save2, save3, save4, save5, save6, save7;
  logic [5:0]  round_cnt;

  logic        sched_load, sched_advance;
  logic [31:0] w_t_val;
  logic [5:0]  t_q_val;
  logic [31:0] k_t_val;

  assign sched_load    = (state_r == ST_IDLE) && start;
  assign sched_advance = (state_r == ST_RUN)  && (round_cnt < 6'd63);
  assign k_t_val        = sha256_pkg::k_const(32'(t_q_val));

  sha256_message_schedule u_sched (
    .clk(clk), .rst_n(rst_n),
    .load(sched_load), .block_bits(block_bits),
    .advance(sched_advance),
    .w_t(w_t_val), .t_q(t_q_val)
  );

  logic [31:0] a_n, b_n, c_n, d_n, e_n, f_n, g_n, h_n;

  sha256_round u_round (
    .a_in(a_r), .b_in(b_r), .c_in(c_r), .d_in(d_r),
    .e_in(e_r), .f_in(f_r), .g_in(g_r), .h_in(h_r),
    .w_t(w_t_val), .k_t(k_t_val),
    .a_out(a_n), .b_out(b_n), .c_out(c_n), .d_out(d_n),
    .e_out(e_n), .f_out(f_n), .g_out(g_n), .h_out(h_n)
  );

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      state_r   <= ST_IDLE;
      busy      <= 1'b0;
      done      <= 1'b0;
      round_cnt <= '0;
      {a_r, b_r, c_r, d_r, e_r, f_r, g_r, h_r} <= '0;
      {save0, save1, save2, save3, save4, save5, save6, save7} <= '0;
      state_out <= '0;
    end else begin
      done <= 1'b0;  // default; pulsed for exactly one cycle below
      unique case (state_r)
        ST_IDLE: begin
          if (start) begin
            a_r <= state_in[255:224]; b_r <= state_in[223:192];
            c_r <= state_in[191:160]; d_r <= state_in[159:128];
            e_r <= state_in[127:96];  f_r <= state_in[95:64];
            g_r <= state_in[63:32];   h_r <= state_in[31:0];
            save0 <= state_in[255:224]; save1 <= state_in[223:192];
            save2 <= state_in[191:160]; save3 <= state_in[159:128];
            save4 <= state_in[127:96];  save5 <= state_in[95:64];
            save6 <= state_in[63:32];   save7 <= state_in[31:0];
            round_cnt <= '0;
            busy    <= 1'b1;
            state_r <= ST_RUN;
          end
        end

        ST_RUN: begin
          a_r <= a_n; b_r <= b_n; c_r <= c_n; d_r <= d_n;
          e_r <= e_n; f_r <= f_n; g_r <= g_n; h_r <= h_n;
          if (round_cnt == 6'd63) begin
            // Davies-Meyer feedback: new state = old state + compressed chunk.
            state_out <= { save0 + a_n, save1 + b_n, save2 + c_n, save3 + d_n,
                           save4 + e_n, save5 + f_n, save6 + g_n, save7 + h_n };
            done    <= 1'b1;
            busy    <= 1'b0;
            state_r <= ST_IDLE;
          end else begin
            round_cnt <= round_cnt + 6'd1;
          end
        end

        default: state_r <= ST_IDLE;
      endcase
    end
  end

endmodule : sha256_compressor
