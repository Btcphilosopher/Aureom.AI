// =============================================================================
// SilicaFlux MemoryFlow :: sf_ecc_secded_enc
// Combinational extended-Hamming SECDED encoder, parameterised on data width.
//   K=32 -> 39-bit codeword (R=6),  K=64 -> 72-bit codeword (R=7).
// Output layout: { overall_parity, check[R-1:0], data[K-1:0] }
// Classification: SYNTHESIZABLE
// =============================================================================
`default_nettype none

module sf_ecc_secded_enc #(
  parameter  int K = 64,
  localparam int R = $clog2(K + 1 + $clog2(K + 1)),
  localparam int N = K + R + 1
) (
  input  logic [K-1:0] data,
  output logic [N-1:0] code
);
  `include "sf_ecc_funcs.svh"

  logic [R-1:0] chk;

  genvar gi;
  generate
    for (gi = 0; gi < R; gi++) begin : g_chk
      localparam logic [K-1:0] MASK = sf_ecc_cmask(gi);
      assign chk[gi] = ^(data & MASK);
    end
  endgenerate

  assign code = {(^data) ^ (^chk), chk, data};

endmodule

`default_nettype wire
