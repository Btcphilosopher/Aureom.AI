// tb_target_compare.sv -- unit test for nbits_expand and target_compare
// against python/silicaflux_bitcoin/reference/block_header.py's
// bits_to_target() and target_meets().
`timescale 1ns/1ps
`include "tb/vectors/vector_counts.svh"

module tb_target_compare;
  localparam int NB = `NBITS_EXPAND_N;
  localparam int NT = `TARGET_COMPARE_N;

  // --- nbits_expand ---
  logic [31:0]  bits_v   [0:NB-1];
  logic [255:0] target_v [0:NB-1];
  logic [31:0]  bits_in;
  logic [255:0] target_out;
  nbits_expand u_expand (.bits(bits_in), .target(target_out));

  // --- target_compare ---
  logic [255:0] hash_v   [0:NT-1];
  logic [255:0] tgt_v    [0:NT-1];
  logic         meets_v  [0:NT-1];
  logic [255:0] hash_in, target_in;
  logic         meets_out;
  target_compare u_cmp (.hash(hash_in), .target(target_in), .meets_target(meets_out));

  int errors_expand, errors_compare;

  initial begin
    $readmemh("tb/vectors/target_bits.hex", bits_v);
    $readmemh("tb/vectors/target_expected.hex", target_v);
    $readmemh("tb/vectors/target_hash_in.hex", hash_v);
    $readmemh("tb/vectors/target_target_in.hex", tgt_v);
    $readmemh("tb/vectors/target_meets_expected.hex", meets_v);

    errors_expand = 0;
    for (int i = 0; i < NB; i++) begin
      bits_in = bits_v[i];
      #1;
      if (target_out !== target_v[i]) begin
        errors_expand++;
        $display("[FAIL] nbits_expand case %0d: bits=%08h got=%064h want=%064h", i, bits_in, target_out, target_v[i]);
      end
    end

    errors_compare = 0;
    for (int i = 0; i < NT; i++) begin
      hash_in   = hash_v[i];
      target_in = tgt_v[i];
      #1;
      if (meets_out !== meets_v[i]) begin
        errors_compare++;
        $display("[FAIL] target_compare case %0d: hash=%064h target=%064h got=%0d want=%0d",
                  i, hash_in, target_in, meets_out, meets_v[i]);
      end
    end

    if (errors_expand == 0 && errors_compare == 0)
      $display("[PASS] tb_target_compare: nbits_expand %0d/%0d, target_compare %0d/%0d all matched", NB, NB, NT, NT);
    else
      $display("[FAIL] tb_target_compare: nbits_expand_err=%0d/%0d target_compare_err=%0d/%0d",
                errors_expand, NB, errors_compare, NT);
    $finish;
  end
endmodule : tb_target_compare
