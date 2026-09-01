// nonce_allocator.sv -- deterministic, duplicate-free nonce range
// allocation across NUM_CORES parallel hash cores (section 9).
//
// Core i (i = 0..NUM_CORES-1) is assigned the arithmetic sequence
//     nonce_start + i*nonce_stride,
//     nonce_start + (NUM_CORES+i)*nonce_stride,
//     nonce_start + (2*NUM_CORES+i)*nonce_stride,
//     ...
// i.e. core i's FIRST value is core_nonce_init[i] = nonce_start +
// i*nonce_stride, and every core advances its own counter locally by the
// SAME fixed step core_nonce_step = NUM_CORES*nonce_stride (computed
// once here, applied per-core in hash_core.sv -- this module only
// produces the per-core starting points, not a live per-cycle arbiter,
// since nothing about the split needs to be renegotiated between nonce
// trials).
//
// No duplicate assignment: for any nonce_stride >= 1, the NUM_CORES
// initial offsets i*nonce_stride (i=0..NUM_CORES-1) are pairwise
// distinct modulo NUM_CORES*nonce_stride, and every subsequent value in
// core i's sequence differs from every value in core j's sequence
// (i != j) by construction -- verified exhaustively for representative
// (NUM_CORES, stride, attempt-count) combinations in
// tb/unit/tb_nonce_allocator.sv.
//
// Ports use a packed, flattened vector rather than an unpacked array
// (see rtl/sha256/sha256_message_schedule.sv header comment for why:
// Icarus Verilog 12.0 does not propagate unpacked-array *output* ports
// through instantiation). core_nonce_init_flat packs NUM_CORES words,
// core 0 in the most-significant slot: core i occupies bits
// [(NUM_CORES-i)*NONCE_WIDTH-1 -: NONCE_WIDTH].
module nonce_allocator #(
  parameter int NUM_CORES   = 4,
  parameter int NONCE_WIDTH = 32
) (
  input  logic [NONCE_WIDTH-1:0] nonce_start,
  input  logic [NONCE_WIDTH-1:0] nonce_stride,
  output logic [NUM_CORES*NONCE_WIDTH-1:0] core_nonce_init_flat,
  output logic [NONCE_WIDTH-1:0]           core_nonce_step
);

  assign core_nonce_step = nonce_stride * NUM_CORES;

  genvar gi;
  generate
    for (gi = 0; gi < NUM_CORES; gi++) begin : g_core
      assign core_nonce_init_flat[(NUM_CORES-gi)*NONCE_WIDTH-1 -: NONCE_WIDTH] =
        nonce_start + nonce_stride * gi;
    end
  endgenerate

endmodule : nonce_allocator
