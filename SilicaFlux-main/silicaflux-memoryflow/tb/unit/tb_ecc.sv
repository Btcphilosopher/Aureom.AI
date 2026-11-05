// =============================================================================
// tb_ecc :: SECDED encoder/decoder verification (K = 32 and K = 64)
//  1. Encoder output == Python golden codewords (bit-exact cross-check).
//  2. Clean decode returns data, no error flags.
//  3. EXHAUSTIVE single-bit injection at every codeword position -> corrected.
//  4. EXHAUSTIVE double-bit injection (all position pairs) on a subset of
//     words -> detected as uncorrectable, never mis-corrected silently.
// =============================================================================
`timescale 1ns/1ps
`default_nettype none
`include "tb_common.svh"

module tb_ecc;
  localparam int K64 = 64, N64 = 72;
  localparam int K32 = 32, N32 = 39;
  localparam int NV  = 256;

  logic [K64-1:0] d64;  logic [N64-1:0] c64, c64_rx;  logic [K64-1:0] o64;
  logic corr64, unc64;  logic [6:0] syn64;
  logic [K32-1:0] d32;  logic [N32-1:0] c32, c32_rx;  logic [K32-1:0] o32;
  logic corr32, unc32;  logic [5:0] syn32;

  sf_ecc_secded_enc #(.K(K64)) u_e64 (.data(d64), .code(c64));
  sf_ecc_secded_dec #(.K(K64)) u_d64 (.code(c64_rx), .data(o64), .err_corr(corr64),
                                      .err_uncorr(unc64), .syndrome(syn64));
  sf_ecc_secded_enc #(.K(K32)) u_e32 (.data(d32), .code(c32));
  sf_ecc_secded_dec #(.K(K32)) u_d32 (.code(c32_rx), .data(o32), .err_corr(corr32),
                                      .err_uncorr(unc32), .syndrome(syn32));

  logic [K64-1:0] v64_d [NV];  logic [N64-1:0] v64_c [NV];
  logic [K32-1:0] v32_d [NV];  logic [N32-1:0] v32_c [NV];

  int singles, doubles;

  initial begin
    $readmemh("ecc_k64_data.hex", v64_d);
    $readmemh("ecc_k64_code.hex", v64_c);
    $readmemh("ecc_k32_data.hex", v32_d);
    $readmemh("ecc_k32_code.hex", v32_c);
    singles = 0;
    doubles = 0;

    for (int v = 0; v < NV; v++) begin
      // ------------------------------------------------ K = 64
      d64 = v64_d[v];
      #1;
      `CHECK_EQ(c64, v64_c[v], "K64 encoder vs Python golden")
      c64_rx = c64; #1;
      `CHECK(o64 == d64 && !corr64 && !unc64, "K64 clean decode")
      for (int i = 0; i < N64; i++) begin
        c64_rx = c64 ^ (N64'(1) << i); #1;
        `CHECK(o64 == d64 && corr64 && !unc64, $sformatf("K64 single-bit pos %0d", i))
        singles++;
      end
      if (v < 24) begin
        for (int i = 0; i < N64; i++) begin
          for (int j = i + 1; j < N64; j++) begin
            c64_rx = c64 ^ (N64'(1) << i) ^ (N64'(1) << j); #1;
            `CHECK(unc64 && !corr64, $sformatf("K64 double-bit %0d,%0d", i, j))
            doubles++;
          end
        end
      end
      // ------------------------------------------------ K = 32
      d32 = v32_d[v];
      #1;
      `CHECK_EQ(c32, v32_c[v], "K32 encoder vs Python golden")
      c32_rx = c32; #1;
      `CHECK(o32 == d32 && !corr32 && !unc32, "K32 clean decode")
      for (int i = 0; i < N32; i++) begin
        c32_rx = c32 ^ (N32'(1) << i); #1;
        `CHECK(o32 == d32 && corr32 && !unc32, $sformatf("K32 single-bit pos %0d", i))
        singles++;
      end
      if (v < 24) begin
        for (int i = 0; i < N32; i++) begin
          for (int j = i + 1; j < N32; j++) begin
            c32_rx = c32 ^ (N32'(1) << i) ^ (N32'(1) << j); #1;
            `CHECK(unc32 && !corr32, $sformatf("K32 double-bit %0d,%0d", i, j))
            doubles++;
          end
        end
      end
    end
    tb_metric("ecc_single_bit_injections", real'(singles));
    tb_metric("ecc_double_bit_injections", real'(doubles));
    tb_finish();
  end
endmodule

`default_nettype wire
