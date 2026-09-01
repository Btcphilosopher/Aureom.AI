// tb_sha256_ch_maj.sv -- self-checking unit testbench for sha256_ch and
// sha256_maj against vectors generated from the Python golden model
// (python/silicaflux_bitcoin/vectors/generate_vectors.py:gen_ch_maj_vectors).
`timescale 1ns/1ps
`include "tb/vectors/vector_counts.svh"

module tb_sha256_ch_maj;
  localparam int N = `CH_MAJ_N;

  logic [31:0] xs [0:N-1], ys [0:N-1], zs [0:N-1];
  logic [31:0] ch_expected [0:N-1], maj_expected [0:N-1];

  logic [31:0] x, y, z, ch_out, maj_out;

  sha256_ch  u_ch  (.x(x), .y(y), .z(z), .ch(ch_out));
  sha256_maj u_maj (.x(x), .y(y), .z(z), .maj(maj_out));

  int errors;

  initial begin
    $readmemh("tb/vectors/ch_maj_x.hex", xs);
    $readmemh("tb/vectors/ch_maj_y.hex", ys);
    $readmemh("tb/vectors/ch_maj_z.hex", zs);
    $readmemh("tb/vectors/ch_expected.hex", ch_expected);
    $readmemh("tb/vectors/maj_expected.hex", maj_expected);

    errors = 0;
    for (int i = 0; i < N; i++) begin
      x = xs[i]; y = ys[i]; z = zs[i];
      #1;
      if (ch_out !== ch_expected[i]) begin
        errors++;
        $display("[FAIL] Ch case %0d: x=%08h y=%08h z=%08h got=%08h want=%08h",
                  i, x, y, z, ch_out, ch_expected[i]);
      end
      if (maj_out !== maj_expected[i]) begin
        errors++;
        $display("[FAIL] Maj case %0d: x=%08h y=%08h z=%08h got=%08h want=%08h",
                  i, x, y, z, maj_out, maj_expected[i]);
      end
    end

    if (errors == 0)
      $display("[PASS] tb_sha256_ch_maj: %0d cases (%0d checks) all matched", N, 2*N);
    else
      $display("[FAIL] tb_sha256_ch_maj: %0d/%0d checks failed", errors, 2*N);
    $finish;
  end
endmodule : tb_sha256_ch_maj
