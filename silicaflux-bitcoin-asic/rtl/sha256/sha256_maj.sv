// sha256_maj.sv -- SHA-256 "Majority" function: Maj(x,y,z) = (x AND y) XOR (x AND z) XOR (y AND z).
// FIPS 180-4 section 4.1.2. Purely combinational, bit-exact.
module sha256_maj (
  input  logic [31:0] x,
  input  logic [31:0] y,
  input  logic [31:0] z,
  output logic [31:0] maj
);
  assign maj = (x & y) ^ (x & z) ^ (y & z);
endmodule : sha256_maj
