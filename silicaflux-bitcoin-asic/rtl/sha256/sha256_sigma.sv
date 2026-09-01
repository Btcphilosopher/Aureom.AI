// sha256_sigma.sv -- the four SHA-256 rotate/shift-xor functions
// (FIPS 180-4 section 4.1.2). Four small modules in one file, grouped
// here (rather than one file each) because they share the same shape and
// the shared sha256_pkg::rotr32 helper; each is independently
// instantiable and independently covered by tb/unit/tb_sha256_sigma.sv.
//
//   Big Sigma0(x) = ROTR2(x)  XOR ROTR13(x) XOR ROTR22(x)   -- used on 'a' in the round function
//   Big Sigma1(x) = ROTR6(x)  XOR ROTR11(x) XOR ROTR25(x)   -- used on 'e' in the round function
//   Small sigma0(x) = ROTR7(x) XOR ROTR18(x) XOR SHR3(x)    -- used in the message schedule
//   Small sigma1(x) = ROTR17(x) XOR ROTR19(x) XOR SHR10(x)  -- used in the message schedule
//
// Calls sha256_pkg::rotr32(...) fully-qualified rather than using a
// module-header `import sha256_pkg::rotr32;`: confirmed during bring-up
// that yosys 0.33's built-in `read_verilog -sv` frontend (used for this
// project's synthesis/area estimates, see scripts/ and
// python/silicaflux_bitcoin/optimisation/design_space_explore.py)
// rejects the `module foo import pkg::*; (...)` header-import form
// outright, while fully-qualified `pkg::item(...)` calls work cleanly --
// and are already the convention used everywhere else in rtl/ (e.g.
// sha256_pkg::k_const(...), sha256_pkg::H0_0).

module sha256_big_sigma0 (
  input  logic [31:0] x,
  output logic [31:0] y
);
  assign y = sha256_pkg::rotr32(x, 2) ^ sha256_pkg::rotr32(x, 13) ^ sha256_pkg::rotr32(x, 22);
endmodule : sha256_big_sigma0

module sha256_big_sigma1 (
  input  logic [31:0] x,
  output logic [31:0] y
);
  assign y = sha256_pkg::rotr32(x, 6) ^ sha256_pkg::rotr32(x, 11) ^ sha256_pkg::rotr32(x, 25);
endmodule : sha256_big_sigma1

module sha256_small_sigma0 (
  input  logic [31:0] x,
  output logic [31:0] y
);
  assign y = sha256_pkg::rotr32(x, 7) ^ sha256_pkg::rotr32(x, 18) ^ (x >> 3);
endmodule : sha256_small_sigma0

module sha256_small_sigma1 (
  input  logic [31:0] x,
  output logic [31:0] y
);
  assign y = sha256_pkg::rotr32(x, 17) ^ sha256_pkg::rotr32(x, 19) ^ (x >> 10);
endmodule : sha256_small_sigma1
