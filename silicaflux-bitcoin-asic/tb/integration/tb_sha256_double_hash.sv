// tb_sha256_double_hash.sv -- integration test for sha256_double_hash.sv.
//
// Two passes over the same `DOUBLE_HASH_N` header vectors (genesis block
// + randomised headers):
//   Pass A (use_midstate=0): full 3-block path from raw header bytes.
//     Checks midstate_out against the Python golden model's midstate()
//     AND pow_hash against double_sha256(header) -- i.e. this is the
//     "Bitcoin-style... midstate vectors, double-SHA-256 vectors" check
//     from section 26.
//   Pass B (use_midstate=1): feeds the MIDSTATE RTL ITSELF COMPUTED in
//     pass A back in, along with the same header_tail4, and checks that
//     the 2-block midstate-reuse path produces the bit-identical
//     pow_hash as the 3-block path -- i.e. this is the correctness proof
//     that the midstate optimisation (section 13/14) doesn't change the
//     answer, cross-checked against RTL's own value, not just Python's.
`timescale 1ns/1ps
`include "tb/vectors/vector_counts.svh"

module tb_sha256_double_hash;
  localparam int N = `DOUBLE_HASH_N;

  logic [511:0] block1_v   [0:N-1];
  logic [127:0] tail4_v    [0:N-1];
  logic [255:0] midstate_v [0:N-1];
  logic [255:0] powhash_v  [0:N-1];

  logic         clk, rst_n;
  logic         start, use_midstate;
  logic [255:0] midstate_in;
  logic [511:0] header_block1;
  logic [127:0] header_tail4;
  logic         busy, done;
  logic [255:0] pow_hash;
  logic         midstate_out_valid;
  logic [255:0] midstate_out;

  sha256_double_hash dut (
    .clk(clk), .rst_n(rst_n), .start(start),
    .use_midstate(use_midstate), .midstate_in(midstate_in),
    .header_block1(header_block1), .header_tail4(header_tail4),
    .busy(busy), .done(done), .pow_hash(pow_hash),
    .midstate_out_valid(midstate_out_valid), .midstate_out(midstate_out)
  );

  always #5 clk = ~clk;

  int errors_midstate, errors_powhash_a, errors_powhash_b;
  logic [255:0] rtl_midstate [0:N-1];

  task automatic run_one(input logic use_ms, input logic [255:0] ms_in,
                          input logic [511:0] b1, input logic [127:0] t4,
                          output logic [255:0] ms_out, output logic [255:0] ph_out);
    logic finished;
    @(negedge clk);
    use_midstate  = use_ms;
    midstate_in   = ms_in;
    header_block1 = b1;
    header_tail4  = t4;
    start = 1;
    @(negedge clk);
    start = 0;
    ms_out = '0;
    finished = 1'b0;
    while (!finished) begin
      if (midstate_out_valid) ms_out = midstate_out;
      if (done) begin
        ph_out = pow_hash;
        finished = 1'b1;
      end else begin
        @(negedge clk);
      end
    end
  endtask

  initial begin
    $readmemh("tb/vectors/dh_header_block1.hex", block1_v);
    $readmemh("tb/vectors/dh_header_tail4.hex", tail4_v);
    $readmemh("tb/vectors/dh_midstate.hex", midstate_v);
    $readmemh("tb/vectors/dh_pow_hash.hex", powhash_v);

    clk = 0; rst_n = 0; start = 0; use_midstate = 0; midstate_in = '0;
    header_block1 = '0; header_tail4 = '0;
    errors_midstate = 0; errors_powhash_a = 0; errors_powhash_b = 0;
    @(negedge clk); rst_n = 1;

    // Pass A: raw header, 3-block path.
    for (int i = 0; i < N; i++) begin
      logic [255:0] ms_out, ph_out;
      run_one(1'b0, 256'h0, block1_v[i], tail4_v[i], ms_out, ph_out);
      rtl_midstate[i] = ms_out;
      if (ms_out !== midstate_v[i]) begin
        errors_midstate++;
        $display("[FAIL] double_hash passA case %0d midstate: got=%064h want=%064h", i, ms_out, midstate_v[i]);
      end
      if (ph_out !== powhash_v[i]) begin
        errors_powhash_a++;
        $display("[FAIL] double_hash passA case %0d pow_hash: got=%064h want=%064h", i, ph_out, powhash_v[i]);
      end
    end

    // Pass B: midstate-reuse path, fed the RTL's OWN pass-A midstate.
    for (int i = 0; i < N; i++) begin
      logic [255:0] ms_out, ph_out;
      run_one(1'b1, rtl_midstate[i], 512'h0, tail4_v[i], ms_out, ph_out);
      if (ph_out !== powhash_v[i]) begin
        errors_powhash_b++;
        $display("[FAIL] double_hash passB case %0d pow_hash: got=%064h want=%064h", i, ph_out, powhash_v[i]);
      end
    end

    if (errors_midstate == 0 && errors_powhash_a == 0 && errors_powhash_b == 0)
      $display("[PASS] tb_sha256_double_hash: %0d headers, both raw-header and midstate-reuse paths matched Python", N);
    else
      $display("[FAIL] tb_sha256_double_hash: midstate_err=%0d passA_err=%0d passB_err=%0d (of %0d)",
                errors_midstate, errors_powhash_a, errors_powhash_b, N);
    $finish;
  end

  initial begin
    #20_000_000;
    $display("[FAIL] tb_sha256_double_hash: TIMEOUT");
    $finish;
  end
endmodule : tb_sha256_double_hash
