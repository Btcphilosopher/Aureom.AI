// =============================================================================
// SilicaFlux MemoryFlow :: sf_ecc_secded_dec
// Combinational extended-Hamming SECDED decoder / corrector.
//   single-bit error anywhere in the codeword  -> corrected, err_corr = 1
//   double-bit error                           -> detected,  err_uncorr = 1
//   syndrome pointing outside the codeword     -> detected,  err_uncorr = 1
// Classification: SYNTHESIZABLE
// =============================================================================
`default_nettype none

module sf_ecc_secded_dec #(
  parameter  int K = 64,
  localparam int R = $clog2(K + 1 + $clog2(K + 1)),
  localparam int N = K + R + 1
) (
  input  logic [N-1:0] code,
  output logic [K-1:0] data,
  output logic         err_corr,     // single error corrected
  output logic         err_uncorr,   // uncorrectable error detected
  output logic [R-1:0] syndrome
);
  `include "sf_ecc_funcs.svh"

  localparam int MAXPOS = K + R;     // highest legal Hamming position

  wire [K-1:0] d_rx  = code[K-1:0];
  wire [R-1:0] c_rx  = code[K+R-1:K];
  wire         p_all = ^code;        // 1 => odd number of flipped bits

  logic [R-1:0] c_re;
  genvar gi;
  generate
    for (gi = 0; gi < R; gi++) begin : g_chk
      localparam logic [K-1:0] MASK = sf_ecc_cmask(gi);
      assign c_re[gi] = ^(d_rx & MASK);
    end
  endgenerate

  assign syndrome = c_re ^ c_rx;

  wire syn_nz     = |syndrome;
  wire syn_in_rng = ({1'b0, syndrome} <= (R+1)'(MAXPOS));

  // single error: odd overall parity and syndrome addresses a real position
  // (syndrome == 0 with odd parity => the overall-parity bit itself flipped)
  wire single = p_all & (~syn_nz | syn_in_rng);

  generate
    for (gi = 0; gi < K; gi++) begin : g_cor
      localparam int POS = sf_ecc_dpos(gi);
      assign data[gi] = d_rx[gi] ^ (single & (syndrome == R'(POS)));
    end
  endgenerate

  assign err_corr   = single;
  assign err_uncorr = (~p_all & syn_nz) | (p_all & syn_nz & ~syn_in_rng);

endmodule

`default_nettype wire
