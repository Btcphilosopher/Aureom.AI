// sha256_ch.sv -- SHA-256 "Choose" function: Ch(x,y,z) = (x AND y) XOR ((NOT x) AND z).
// FIPS 180-4 section 4.1.2. Purely combinational, bit-exact.
module sha256_ch (
  input  logic [31:0] x,
  input  logic [31:0] y,
  input  logic [31:0] z,
  output logic [31:0] ch
);
  assign ch = (x & y) ^ (~x & z);
endmodule : sha256_ch
