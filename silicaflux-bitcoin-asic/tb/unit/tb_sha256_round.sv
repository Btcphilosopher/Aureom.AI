// tb_sha256_round.sv -- self-checking unit testbench for sha256_round.sv
// against vectors from the Python golden model (directed real round
// traces from compressing "abc"/empty/"bitcoinbitcoinbitcoin", plus
// random {a..h,w,k} combinations).
`timescale 1ns/1ps
`include "tb/vectors/vector_counts.svh"

module tb_sha256_round;
  localparam int N = `ROUND_N;

  logic [31:0] a_in[0:N-1], b_in[0:N-1], c_in[0:N-1], d_in[0:N-1];
  logic [31:0] e_in[0:N-1], f_in[0:N-1], g_in[0:N-1], h_in[0:N-1];
  logic [31:0] w_in[0:N-1], k_in[0:N-1];
  logic [31:0] a_exp[0:N-1], b_exp[0:N-1], c_exp[0:N-1], d_exp[0:N-1];
  logic [31:0] e_exp[0:N-1], f_exp[0:N-1], g_exp[0:N-1], h_exp[0:N-1];

  logic [31:0] a, b, c, d, e, f, g, h, w_t, k_t;
  logic [31:0] a_o, b_o, c_o, d_o, e_o, f_o, g_o, h_o;

  sha256_round dut (
    .a_in(a), .b_in(b), .c_in(c), .d_in(d),
    .e_in(e), .f_in(f), .g_in(g), .h_in(h),
    .w_t(w_t), .k_t(k_t),
    .a_out(a_o), .b_out(b_o), .c_out(c_o), .d_out(d_o),
    .e_out(e_o), .f_out(f_o), .g_out(g_o), .h_out(h_o)
  );

  int errors;

  task automatic check1(input string name, input logic [31:0] got, input logic [31:0] want, input int i);
    if (got !== want) begin
      errors++;
      $display("[FAIL] round %s case %0d: got=%08h want=%08h", name, i, got, want);
    end
  endtask

  initial begin
    $readmemh("tb/vectors/round_a_in.hex", a_in);
    $readmemh("tb/vectors/round_b_in.hex", b_in);
    $readmemh("tb/vectors/round_c_in.hex", c_in);
    $readmemh("tb/vectors/round_d_in.hex", d_in);
    $readmemh("tb/vectors/round_e_in.hex", e_in);
    $readmemh("tb/vectors/round_f_in.hex", f_in);
    $readmemh("tb/vectors/round_g_in.hex", g_in);
    $readmemh("tb/vectors/round_h_in.hex", h_in);
    $readmemh("tb/vectors/round_w_in.hex", w_in);
    $readmemh("tb/vectors/round_k_in.hex", k_in);
    $readmemh("tb/vectors/round_a_out.hex", a_exp);
    $readmemh("tb/vectors/round_b_out.hex", b_exp);
    $readmemh("tb/vectors/round_c_out.hex", c_exp);
    $readmemh("tb/vectors/round_d_out.hex", d_exp);
    $readmemh("tb/vectors/round_e_out.hex", e_exp);
    $readmemh("tb/vectors/round_f_out.hex", f_exp);
    $readmemh("tb/vectors/round_g_out.hex", g_exp);
    $readmemh("tb/vectors/round_h_out.hex", h_exp);

    errors = 0;
    for (int i = 0; i < N; i++) begin
      a = a_in[i]; b = b_in[i]; c = c_in[i]; d = d_in[i];
      e = e_in[i]; f = f_in[i]; g = g_in[i]; h = h_in[i];
      w_t = w_in[i]; k_t = k_in[i];
      #1;
      check1("a", a_o, a_exp[i], i); check1("b", b_o, b_exp[i], i);
      check1("c", c_o, c_exp[i], i); check1("d", d_o, d_exp[i], i);
      check1("e", e_o, e_exp[i], i); check1("f", f_o, f_exp[i], i);
      check1("g", g_o, g_exp[i], i); check1("h", h_o, h_exp[i], i);
    end

    if (errors == 0)
      $display("[PASS] tb_sha256_round: %0d cases (%0d checks) all matched", N, 8*N);
    else
      $display("[FAIL] tb_sha256_round: %0d/%0d checks failed", errors, 8*N);
    $finish;
  end
endmodule : tb_sha256_round
