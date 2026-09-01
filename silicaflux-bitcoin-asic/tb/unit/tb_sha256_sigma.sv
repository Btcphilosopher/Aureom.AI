// tb_sha256_sigma.sv -- self-checking unit testbench for the four
// sha256_sigma.sv modules against vectors from the Python golden model.
`timescale 1ns/1ps
`include "tb/vectors/vector_counts.svh"

module tb_sha256_sigma;
  localparam int N = `SIGMA_N;

  logic [31:0] xs [0:N-1];
  logic [31:0] bsig0_expected [0:N-1], bsig1_expected [0:N-1];
  logic [31:0] ssig0_expected [0:N-1], ssig1_expected [0:N-1];

  logic [31:0] x, bsig0_out, bsig1_out, ssig0_out, ssig1_out;

  sha256_big_sigma0   u_bsig0 (.x(x), .y(bsig0_out));
  sha256_big_sigma1   u_bsig1 (.x(x), .y(bsig1_out));
  sha256_small_sigma0 u_ssig0 (.x(x), .y(ssig0_out));
  sha256_small_sigma1 u_ssig1 (.x(x), .y(ssig1_out));

  int errors;

  task automatic check(input string name, input logic [31:0] got, input logic [31:0] want, input int i);
    if (got !== want) begin
      errors++;
      $display("[FAIL] %s case %0d: x=%08h got=%08h want=%08h", name, i, x, got, want);
    end
  endtask

  initial begin
    $readmemh("tb/vectors/sigma_x.hex", xs);
    $readmemh("tb/vectors/sigma_bsig0_expected.hex", bsig0_expected);
    $readmemh("tb/vectors/sigma_bsig1_expected.hex", bsig1_expected);
    $readmemh("tb/vectors/sigma_ssig0_expected.hex", ssig0_expected);
    $readmemh("tb/vectors/sigma_ssig1_expected.hex", ssig1_expected);

    errors = 0;
    for (int i = 0; i < N; i++) begin
      x = xs[i];
      #1;
      check("BigSigma0",   bsig0_out, bsig0_expected[i], i);
      check("BigSigma1",   bsig1_out, bsig1_expected[i], i);
      check("SmallSigma0", ssig0_out, ssig0_expected[i], i);
      check("SmallSigma1", ssig1_out, ssig1_expected[i], i);
    end

    if (errors == 0)
      $display("[PASS] tb_sha256_sigma: %0d cases (%0d checks) all matched", N, 4*N);
    else
      $display("[FAIL] tb_sha256_sigma: %0d/%0d checks failed", errors, 4*N);
    $finish;
  end
endmodule : tb_sha256_sigma
