// sha256_pipeline.sv -- PIPELINED (spatially-unrolled) SHA-256
// compression core, section 7/8 "configurable pipeline architectures".
//
// All 64 rounds are unrolled into PIPELINE_DEPTH pipeline stages of
// ROUNDS_PER_STAGE = 64/PIPELINE_DEPTH rounds each (PIPELINE_DEPTH must
// be one of 1/2/4/8/16/32/64 -- checked at elaboration below). Within a
// stage, ROUNDS_PER_STAGE copies of sha256_round + sha256_schedule_step
// are chained purely combinationally (REGISTER_PIPELINED schedule
// architecture: each pipeline register carries the running 16-word
// schedule window forward, section 6); a register sits only at stage
// boundaries. Round-hardware count is fixed at 64 sha256_round instances
// regardless of PIPELINE_DEPTH -- PIPELINE_DEPTH only chooses *where*
// pipeline registers are inserted, trading combinational depth per stage
// (lower PIPELINE_DEPTH => deeper logic per stage => lower achievable
// Fmax) against register count (higher PIPELINE_DEPTH => more flops).
//
// Fully pipelined streaming interface: a new block may be presented
// every clock cycle (valid_in), and after a fixed latency (SEE the
// `LATENCY_CYCLES` localparam; verified empirically in
// tb/integration/tb_sha256_pipeline.sv rather than asserted from
// hand-derivation) the corresponding result appears on valid_out/
// state_out, in the same order presented (no reordering, no stalls --
// this block never needs to apply backpressure).
module sha256_pipeline #(
  parameter int PIPELINE_DEPTH = 64
) (
  input  logic         clk,
  input  logic         rst_n,
  input  logic         valid_in,
  input  logic [255:0] state_in,
  input  logic [511:0] block_bits,
  output logic         valid_out,
  output logic [255:0] state_out
);

  localparam int ROUNDS_PER_STAGE = 64 / PIPELINE_DEPTH;
  localparam int LATENCY_CYCLES = PIPELINE_DEPTH + 1;  // stage-0 input register + PIPELINE_DEPTH stage registers

  // Elaboration-time configuration guard (mirrors silicaflux.architecture.
  // spec.VALID_PIPELINE_DEPTHS / PipelineConfig.validate()): PIPELINE_DEPTH
  // must divide 64 evenly or the round-to-stage assignment below is invalid.
  initial begin
    if (PIPELINE_DEPTH * ROUNDS_PER_STAGE != 64) begin
      $fatal(1, "sha256_pipeline: PIPELINE_DEPTH=%0d does not evenly divide 64", PIPELINE_DEPTH);
    end
  end

  // Per-stage-boundary registers (index 0 = primary input register,
  // index PIPELINE_DEPTH = final output before the Davies-Meyer sum).
  // Kept as flat parallel arrays rather than a packed struct array:
  // Icarus Verilog 12.0 was found to crash (internal assertion) on a
  // generate-indexed struct-member assignment of this shape during
  // bring-up; flat arrays are the portable equivalent and are used
  // consistently with the rest of rtl/sha256/*.sv.
  logic [31:0]  stage_a [0:PIPELINE_DEPTH], stage_b [0:PIPELINE_DEPTH];
  logic [31:0]  stage_c [0:PIPELINE_DEPTH], stage_d [0:PIPELINE_DEPTH];
  logic [31:0]  stage_e [0:PIPELINE_DEPTH], stage_f [0:PIPELINE_DEPTH];
  logic [31:0]  stage_g [0:PIPELINE_DEPTH], stage_h [0:PIPELINE_DEPTH];
  logic [511:0] stage_window [0:PIPELINE_DEPTH];
  logic [255:0] stage_saved  [0:PIPELINE_DEPTH];
  logic         stage_valid  [0:PIPELINE_DEPTH];

  // Stage 0: primary input register.
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      stage_a[0] <= '0; stage_b[0] <= '0; stage_c[0] <= '0; stage_d[0] <= '0;
      stage_e[0] <= '0; stage_f[0] <= '0; stage_g[0] <= '0; stage_h[0] <= '0;
      stage_window[0] <= '0; stage_saved[0] <= '0; stage_valid[0] <= 1'b0;
    end else begin
      stage_a[0] <= state_in[255:224]; stage_b[0] <= state_in[223:192];
      stage_c[0] <= state_in[191:160]; stage_d[0] <= state_in[159:128];
      stage_e[0] <= state_in[127:96];  stage_f[0] <= state_in[95:64];
      stage_g[0] <= state_in[63:32];   stage_h[0] <= state_in[31:0];
      stage_window[0] <= block_bits;
      stage_saved[0]  <= state_in;
      stage_valid[0]  <= valid_in;
    end
  end

  genvar gs, gr;
  generate
    for (gs = 0; gs < PIPELINE_DEPTH; gs++) begin : g_stage
      // Local, purely-combinational chain of ROUNDS_PER_STAGE rounds
      // within this stage. local index 0 = stage_{a..h,window}[gs];
      // local index ROUNDS_PER_STAGE = combinational input to the next
      // stage's register (stage_{a..h,window}[gs+1]).
      logic [31:0]  a_l [0:ROUNDS_PER_STAGE], b_l [0:ROUNDS_PER_STAGE];
      logic [31:0]  c_l [0:ROUNDS_PER_STAGE], d_l [0:ROUNDS_PER_STAGE];
      logic [31:0]  e_l [0:ROUNDS_PER_STAGE], f_l [0:ROUNDS_PER_STAGE];
      logic [31:0]  g_l [0:ROUNDS_PER_STAGE], h_l [0:ROUNDS_PER_STAGE];
      logic [511:0] window_l [0:ROUNDS_PER_STAGE];
      logic [31:0]  w_l [0:ROUNDS_PER_STAGE];

      assign a_l[0] = stage_a[gs]; assign b_l[0] = stage_b[gs];
      assign c_l[0] = stage_c[gs]; assign d_l[0] = stage_d[gs];
      assign e_l[0] = stage_e[gs]; assign f_l[0] = stage_f[gs];
      assign g_l[0] = stage_g[gs]; assign h_l[0] = stage_h[gs];
      assign window_l[0] = stage_window[gs];

      for (gr = 0; gr < ROUNDS_PER_STAGE; gr++) begin : g_round
        localparam int GLOBAL_T = gs * ROUNDS_PER_STAGE + gr;  // 0..63, elaboration-constant per instance

        sha256_schedule_step u_step (
          .window_in(window_l[gr]), .t_in(6'(GLOBAL_T)),
          .w_out(w_l[gr]), .window_out(window_l[gr+1]), .t_out()
        );

        sha256_round u_round (
          .a_in(a_l[gr]), .b_in(b_l[gr]), .c_in(c_l[gr]), .d_in(d_l[gr]),
          .e_in(e_l[gr]), .f_in(f_l[gr]), .g_in(g_l[gr]), .h_in(h_l[gr]),
          .w_t(w_l[gr]), .k_t(sha256_pkg::k_const(GLOBAL_T)),
          .a_out(a_l[gr+1]), .b_out(b_l[gr+1]), .c_out(c_l[gr+1]), .d_out(d_l[gr+1]),
          .e_out(e_l[gr+1]), .f_out(f_l[gr+1]), .g_out(g_l[gr+1]), .h_out(h_l[gr+1])
        );
      end

      always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
          stage_a[gs+1] <= '0; stage_b[gs+1] <= '0; stage_c[gs+1] <= '0; stage_d[gs+1] <= '0;
          stage_e[gs+1] <= '0; stage_f[gs+1] <= '0; stage_g[gs+1] <= '0; stage_h[gs+1] <= '0;
          stage_window[gs+1] <= '0; stage_saved[gs+1] <= '0; stage_valid[gs+1] <= 1'b0;
        end else begin
          stage_a[gs+1] <= a_l[ROUNDS_PER_STAGE]; stage_b[gs+1] <= b_l[ROUNDS_PER_STAGE];
          stage_c[gs+1] <= c_l[ROUNDS_PER_STAGE]; stage_d[gs+1] <= d_l[ROUNDS_PER_STAGE];
          stage_e[gs+1] <= e_l[ROUNDS_PER_STAGE]; stage_f[gs+1] <= f_l[ROUNDS_PER_STAGE];
          stage_g[gs+1] <= g_l[ROUNDS_PER_STAGE]; stage_h[gs+1] <= h_l[ROUNDS_PER_STAGE];
          stage_window[gs+1] <= window_l[ROUNDS_PER_STAGE];
          stage_saved[gs+1]  <= stage_saved[gs];
          stage_valid[gs+1]  <= stage_valid[gs];
        end
      end
    end
  endgenerate

  // Final Davies-Meyer feedback (new state = old state + compressed
  // chunk), combinational from the last stage's registered outputs --
  // does not add an extra pipeline cycle.
  assign valid_out = stage_valid[PIPELINE_DEPTH];
  assign state_out = {
    stage_saved[PIPELINE_DEPTH][255:224] + stage_a[PIPELINE_DEPTH],
    stage_saved[PIPELINE_DEPTH][223:192] + stage_b[PIPELINE_DEPTH],
    stage_saved[PIPELINE_DEPTH][191:160] + stage_c[PIPELINE_DEPTH],
    stage_saved[PIPELINE_DEPTH][159:128] + stage_d[PIPELINE_DEPTH],
    stage_saved[PIPELINE_DEPTH][127:96]  + stage_e[PIPELINE_DEPTH],
    stage_saved[PIPELINE_DEPTH][95:64]   + stage_f[PIPELINE_DEPTH],
    stage_saved[PIPELINE_DEPTH][63:32]   + stage_g[PIPELINE_DEPTH],
    stage_saved[PIPELINE_DEPTH][31:0]    + stage_h[PIPELINE_DEPTH]
  };

endmodule : sha256_pipeline
