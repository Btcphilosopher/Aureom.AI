// sha256_pkg.sv -- shared SHA-256 constants and helper function.
//
// FIPS 180-4 initial hash value H(0) and round constants K(0..63), plus a
// single synthesizable ROTR helper reused by sha256_sigma.sv. Keeping the
// constants in one package (rather than duplicating literals across
// modules) is the single source of truth every other rtl/sha256/*.sv file
// and the Python golden model (python/silicaflux_bitcoin/reference/
// sha256_model.py) must agree with -- see tb/unit/tb_sha256_pkg_consts.sv.
//
// Fully synthesizable: `automatic` function, static constant arrays, no
// delays, no dynamic/unbounded constructs.
package sha256_pkg;

  localparam int unsigned WORD_W    = 32;
  localparam int unsigned NUM_ROUNDS = 64;
  localparam int unsigned BLOCK_BITS = 512;
  localparam int unsigned BLOCK_BYTES = 64;
  localparam int unsigned DIGEST_BITS = 256;

  // Initial hash value H(0): first 32 bits of the fractional parts of the
  // square roots of the first 8 primes (2..19). FIPS 180-4 section 5.3.3.
  //
  // Kept as 8 named scalars rather than an unpacked-array localparam: some
  // simulators in this project's toolchain (Icarus Verilog 12.0) do not
  // support `localparam <type> name [dim] = '{...}` assignment-pattern
  // initializers (confirmed by isolated repro; a packed-array rewrite
  // trips a separate Icarus internal assertion). Scalars are 100%
  // portable and every consumer needs the full 8-word vector at once
  // (there is no runtime-indexed access to H0 anywhere in this design),
  // so nothing is lost.
  localparam logic [31:0] H0_0 = 32'h6a09e667;
  localparam logic [31:0] H0_1 = 32'hbb67ae85;
  localparam logic [31:0] H0_2 = 32'h3c6ef372;
  localparam logic [31:0] H0_3 = 32'ha54ff53a;
  localparam logic [31:0] H0_4 = 32'h510e527f;
  localparam logic [31:0] H0_5 = 32'h9b05688c;
  localparam logic [31:0] H0_6 = 32'h1f83d9ab;
  localparam logic [31:0] H0_7 = 32'h5be0cd19;

  // Round constants K(0..63): first 32 bits of the fractional parts of the
  // cube roots of the first 64 primes (2..311). FIPS 180-4 section 4.2.2.
  //
  // Implemented as a lookup function (case statement) rather than an
  // indexed array localparam, for the same Icarus-portability reason as
  // H0 above. This also happens to be exactly the right shape for both
  // consumers: sha256_compressor.sv calls it with a *runtime* round
  // counter (synthesizes to a 64:1 mux / small ROM), while
  // sha256_pipeline.sv's generate blocks call it with an elaboration-time
  // constant genvar per round (synthesis/simulation constant-folds it to
  // a literal, no mux at all).
  function automatic logic [31:0] k_const(input int unsigned t);
    case (t)
      0:  k_const = 32'h428a2f98;  1:  k_const = 32'h71374491;
      2:  k_const = 32'hb5c0fbcf;  3:  k_const = 32'he9b5dba5;
      4:  k_const = 32'h3956c25b;  5:  k_const = 32'h59f111f1;
      6:  k_const = 32'h923f82a4;  7:  k_const = 32'hab1c5ed5;
      8:  k_const = 32'hd807aa98;  9:  k_const = 32'h12835b01;
      10: k_const = 32'h243185be;  11: k_const = 32'h550c7dc3;
      12: k_const = 32'h72be5d74;  13: k_const = 32'h80deb1fe;
      14: k_const = 32'h9bdc06a7;  15: k_const = 32'hc19bf174;
      16: k_const = 32'he49b69c1;  17: k_const = 32'hefbe4786;
      18: k_const = 32'h0fc19dc6;  19: k_const = 32'h240ca1cc;
      20: k_const = 32'h2de92c6f;  21: k_const = 32'h4a7484aa;
      22: k_const = 32'h5cb0a9dc;  23: k_const = 32'h76f988da;
      24: k_const = 32'h983e5152;  25: k_const = 32'ha831c66d;
      26: k_const = 32'hb00327c8;  27: k_const = 32'hbf597fc7;
      28: k_const = 32'hc6e00bf3;  29: k_const = 32'hd5a79147;
      30: k_const = 32'h06ca6351;  31: k_const = 32'h14292967;
      32: k_const = 32'h27b70a85;  33: k_const = 32'h2e1b2138;
      34: k_const = 32'h4d2c6dfc;  35: k_const = 32'h53380d13;
      36: k_const = 32'h650a7354;  37: k_const = 32'h766a0abb;
      38: k_const = 32'h81c2c92e;  39: k_const = 32'h92722c85;
      40: k_const = 32'ha2bfe8a1;  41: k_const = 32'ha81a664b;
      42: k_const = 32'hc24b8b70;  43: k_const = 32'hc76c51a3;
      44: k_const = 32'hd192e819;  45: k_const = 32'hd6990624;
      46: k_const = 32'hf40e3585;  47: k_const = 32'h106aa070;
      48: k_const = 32'h19a4c116;  49: k_const = 32'h1e376c08;
      50: k_const = 32'h2748774c;  51: k_const = 32'h34b0bcb5;
      52: k_const = 32'h391c0cb3;  53: k_const = 32'h4ed8aa4a;
      54: k_const = 32'h5b9cca4f;  55: k_const = 32'h682e6ff3;
      56: k_const = 32'h748f82ee;  57: k_const = 32'h78a5636f;
      58: k_const = 32'h84c87814;  59: k_const = 32'h8cc70208;
      60: k_const = 32'h90befffa;  61: k_const = 32'ha4506ceb;
      62: k_const = 32'hbef9a3f7;  63: k_const = 32'hc67178f2;
      default: k_const = 32'hxxxxxxxx;  // out-of-range: never reached by valid RTL
    endcase
  endfunction

  // 32-bit rotate-right. `n` is always a compile-time-constant literal at
  // every call site in this project (2/6/7/11/13/17/18/19/22/25), so
  // synthesis constant-folds this to pure wiring (a bit permutation) with
  // no actual shifter hardware -- there is no barrel shifter in the
  // SHA-256 datapath.
  function automatic logic [31:0] rotr32(input logic [31:0] x, input int unsigned n);
    rotr32 = (x >> n) | (x << (32 - n));
  endfunction

endpackage : sha256_pkg
