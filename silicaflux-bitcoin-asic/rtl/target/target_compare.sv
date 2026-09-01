// target_compare.sv -- Bitcoin proof-of-work target comparison, plus the
// nBits ("compact") -> 256-bit target expansion.
//
// Byte-order (see docs/sha256_spec_notes.md and python/silicaflux_bitcoin/
// reference/block_header.py -- this is the exact RTL counterpart of
// target_meets()/bits_to_target()): every 256-bit hash value elsewhere in
// this RTL (state_in, pow_hash, midstate, ...) is packed MSB-first in the
// literal byte order SHA-256 produces -- i.e. hash[255:248] is the FIRST
// byte of the digest. Bitcoin's actual proof-of-work rule reads those
// same digest bytes as a LITTLE-ENDIAN integer (first byte = least
// significant) and requires that integer <= target. That is the opposite
// byte order from our normal MSB-first packing, so target_compare must
// byte-reverse `hash` (8-bit granularity, NOT 32-bit word granularity)
// before the unsigned comparison. `target` itself is a plain magnitude
// (e.g. from nbits_expand below, or precomputed in software) with no
// byte-order ambiguity -- it is never a byte string, just a number.
module target_compare (
  input  logic [255:0] hash,           // raw pow_hash, byte 0 = hash[255:248]
  input  logic [255:0] target,
  output logic          meets_target
);
  logic [255:0] hash_as_int;

  genvar gb;
  generate
    for (gb = 0; gb < 32; gb++) begin : g_byte_reverse
      // Byte gb of `hash` (its (gb)-th most-significant byte) becomes
      // byte (31-gb) of hash_as_int, i.e. a full 32-byte reversal.
      assign hash_as_int[255 - 8*(31-gb) -: 8] = hash[255 - 8*gb -: 8];
    end
  endgenerate

  assign meets_target = (hash_as_int <= target);

endmodule : target_compare


// nbits_expand -- Bitcoin's compact ("nBits") difficulty encoding to a
// full 256-bit target. bits = (exponent:8)(mantissa:24); bit 23 of the
// mantissa field is a sign flag that consensus rules treat as "target 0"
// (unconditional PoW failure) rather than a negative number, matching
// python/silicaflux_bitcoin/reference/block_header.py:bits_to_target().
//
// This uses a runtime-variable-amount shift (the byte shift depends on
// `exponent`, which is a real input, not a compile-time constant like
// every rotate amount elsewhere in this design) and so synthesizes to an
// actual barrel shifter -- unlike the SHA-256 datapath's rotates, this is
// deliberately NOT in the per-hash hot path: nBits changes once per job
// at most, so this module is meant to be instantiated once in the
// control plane (miner_controller.sv), not once per hash_core.
module nbits_expand (
  input  logic [31:0]  bits,
  output logic [255:0] target
);
  logic [7:0]  exponent;
  logic [23:0] mantissa_raw;
  logic [23:0] mantissa;
  logic        is_negative;
  // Widened past 8 bits deliberately: exponent is a full byte (0..255),
  // so the required left-shift amount (exponent-3)*8 can reach 2016 --
  // an 8-bit shift_bytes silently wraps mod 256 for exponent >= 35 (a
  // real bug caught by tb_target_compare.sv's vectors, which deliberately
  // sweep the full byte range rather than only realistic Bitcoin
  // difficulties ~1..34). 16 bits comfortably covers the full range with
  // no wraparound; SystemVerilog's `<<`/`>>` correctly produce an
  // all-zero result once the shift amount reaches the operand width.
  logic [15:0]  shift_bytes;
  logic [255:0] mantissa_ext;

  assign exponent     = bits[31:24];
  assign mantissa_raw = bits[23:0];
  assign is_negative  = mantissa_raw[23];
  assign mantissa     = {1'b0, mantissa_raw[22:0]};  // mask sign bit, matches Python's & 0x007FFFFF
  assign mantissa_ext = {232'b0, mantissa};

  always_comb begin
    if (is_negative || mantissa == 24'd0) begin
      target      = 256'd0;
      shift_bytes = 16'd0;
    end else if (exponent <= 8'd3) begin
      shift_bytes = (16'd3 - 16'(exponent)) * 16'd8;
      target      = mantissa_ext >> shift_bytes;
    end else begin
      shift_bytes = (16'(exponent) - 16'd3) * 16'd8;
      target      = mantissa_ext << shift_bytes;
    end
  end

endmodule : nbits_expand
