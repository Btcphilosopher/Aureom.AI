// sha256_message_schedule.sv -- SLIDING_WINDOW message-schedule generator.
//
// Holds a 16-word circular buffer w_mem[0:15]. After `load`, w_mem holds
// W[0..15] directly and w_t presents W[t] for the current round index
// t_q (starting at 0). Each `advance` pulse moves to round t+1; for
// t+1 < 16 the word is already present (no computation), for t+1 >= 16
// the new word
//     W[t+1] = sigma1(W[t-1]) + W[t-6] + sigma0(W[t-14]) + W[t+1-16]
// (indices taken mod 16 of the *current* round t, see derivation in
// docs/architecture.md section 6) is computed combinationally from the
// current window contents and written into the slot being vacated --
// which is exactly the slot whose old value (W[t+1-16]) is no longer
// needed by any future round. This is the minimum-storage schedule
// architecture (16 words vs. 64 for full storage), used by the iterative
// core (sha256_compressor.sv).
//
// One new word is produced per `advance`, i.e. one round per clock --
// matched 1:1 to how sha256_compressor.sv drives this module.
//
// Port convention: message words cross module boundaries as a single
// packed vector (block_bits[511:0], word 0 = bits [511:480], i.e.
// big-endian word order matching sha256_model.block_to_words()) rather
// than an unpacked array. This is standard, technology-independent
// interface style, and also sidesteps a real Icarus Verilog 12.0
// limitation confirmed during bring-up: unpacked-array *output* ports do
// not propagate values through instantiation, while packed vectors of
// any width are fully portable across every tool used in this project
// (Icarus, Verilator, Yosys). Internally we still unpack into a 16-entry
// array for readability.
module sha256_message_schedule (
  input  logic        clk,
  input  logic         rst_n,
  input  logic          load,               // synchronous: latch block_bits, t_q <= 0
  input  logic [511:0]  block_bits,         // W[0..15], word 0 = bits [511:480]
  input  logic          advance,            // synchronous: move from t_q to t_q+1
  output logic [31:0]   w_t,                // W[t_q], combinational read of the current slot
  output logic [5:0]    t_q                 // current round index (0..63)
);

  logic [31:0] w_mem [0:15];
  logic [31:0] block_words [0:15];
  logic [5:0]  t_r;
  logic [3:0]  idx;

  genvar gi;
  generate
    for (gi = 0; gi < 16; gi++) begin : g_unpack
      assign block_words[gi] = block_bits[511 - 32*gi -: 32];
    end
  endgenerate

  logic [31:0] w_tm2, w_tm7, w_tm15, w_tm16, sigma1_val, sigma0_val, next_w;

  assign idx = t_r[3:0];

  // Operand indices relative to the word about to be produced, t' = t_r+1:
  //   W[t'-2]  -> slot (idx-1)   W[t'-7]  -> slot (idx-6)
  //   W[t'-15] -> slot (idx-14) W[t'-16] -> slot (idx+1)  (the slot written this cycle)
  assign w_tm2  = w_mem[idx - 4'd1];
  assign w_tm7  = w_mem[idx - 4'd6];
  assign w_tm15 = w_mem[idx - 4'd14];
  assign w_tm16 = w_mem[idx + 4'd1];

  sha256_small_sigma1 u_sigma1 (.x(w_tm2),  .y(sigma1_val));
  sha256_small_sigma0 u_sigma0 (.x(w_tm15), .y(sigma0_val));

  assign next_w = sigma1_val + w_tm7 + sigma0_val + w_tm16;

  assign w_t = w_mem[idx];
  assign t_q = t_r;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      t_r <= '0;
      for (int i = 0; i < 16; i++) w_mem[i] <= '0;
    end else if (load) begin
      t_r <= '0;
      for (int i = 0; i < 16; i++) w_mem[i] <= block_words[i];
    end else if (advance) begin
      t_r <= t_r + 6'd1;
      if (t_r >= 6'd15) begin
        w_mem[idx + 4'd1] <= next_w;
      end
    end
  end

endmodule : sha256_message_schedule
