// sha256_round.sv -- one SHA-256 compression round, purely combinational.
//
//   T1 = h + Sigma1(e) + Ch(e,f,g) + K[t] + W[t]
//   T2 = Sigma0(a) + Maj(a,b,c)
//   a' = T1 + T2      e' = d + T1
//   b' = a            f' = e
//   c' = b            g' = f
//   d' = c            h' = g
//
// Reused two ways elsewhere in rtl/: sha256_compressor.sv instantiates
// exactly one copy and feeds it back through registers 64 times
// (iterative core); sha256_pipeline.sv instantiates 64 copies chained
// combinationally/registered across pipeline stages (spatial core). This
// module itself has no notion of "which architecture" -- it is the one
// piece of the datapath both share, so a correctness fix here fixes both.
module sha256_round (
  input  logic [31:0] a_in, b_in, c_in, d_in, e_in, f_in, g_in, h_in,
  input  logic [31:0] w_t,
  input  logic [31:0] k_t,
  output logic [31:0] a_out, b_out, c_out, d_out, e_out, f_out, g_out, h_out
);

  logic [31:0] sigma1_e, sigma0_a, ch_efg, maj_abc, t1, t2;

  sha256_big_sigma1 u_sigma1 (.x(e_in), .y(sigma1_e));
  sha256_big_sigma0 u_sigma0 (.x(a_in), .y(sigma0_a));
  sha256_ch         u_ch     (.x(e_in), .y(f_in), .z(g_in), .ch(ch_efg));
  sha256_maj        u_maj    (.x(a_in), .y(b_in), .z(c_in), .maj(maj_abc));

  assign t1 = h_in + sigma1_e + ch_efg + k_t + w_t;
  assign t2 = sigma0_a + maj_abc;

  assign a_out = t1 + t2;
  assign b_out = a_in;
  assign c_out = b_in;
  assign d_out = c_in;
  assign e_out = d_in + t1;
  assign f_out = e_in;
  assign g_out = f_in;
  assign h_out = g_in;

endmodule : sha256_round
