// =============================================================================
// tb_sf1_tensor :: SilicaFlux v1 sequential 4x4 tensor unit (tensor_unit.sv,
//                  unmodified, from silicaflux.zip)
//   A[r][c] = mat_a_row<r>[c*32 +: 32], B[k][c] = mat_b_col<c>[k*32 +: 32],
//   C[r][c] = result_row<r>[c*32 +: 32], low 32 bits (wrap-around).
// Measures start-to-done latency and back-to-back operation rate; checks every
// result against a golden model.
// =============================================================================
`timescale 1ns/1ps
`include "tb_common.svh"

module tb_sf1_tensor;
  logic clk = 0, rst_n = 0;
  always #5 clk = ~clk;
  longint cyc = 0;
  always @(posedge clk) cyc <= cyc + 1;

  logic start = 0, done, busy;
  logic [127:0] ar [4], bc [4];
  logic [127:0] rr [4];

  tensor_unit dut (.clk, .rst_n, .start,
    .mat_a_row0(ar[0]), .mat_a_row1(ar[1]), .mat_a_row2(ar[2]), .mat_a_row3(ar[3]),
    .mat_b_col0(bc[0]), .mat_b_col1(bc[1]), .mat_b_col2(bc[2]), .mat_b_col3(bc[3]),
    .done, .busy,
    .result_row0(rr[0]), .result_row1(rr[1]), .result_row2(rr[2]), .result_row3(rr[3]));

  int A [4][4], B [4][4];
  longint t_start, lat_sum = 0, nops = 0;

  task automatic run_one(int kind);
    logic [127:0] ta [4], tb [4];
    for (int r = 0; r < 4; r++)
      for (int c = 0; c < 4; c++) begin
        A[r][c] = kind == 0 ? int'($urandom) : int'($urandom_range(0, 200)) - 100;
        B[r][c] = kind == 0 ? int'($urandom) : int'($urandom_range(0, 200)) - 100;
      end
    for (int r = 0; r < 4; r++)
      for (int c = 0; c < 4; c++) begin
        ta[r][c*32 +: 32] = A[r][c];
        tb[c][r*32 +: 32] = B[r][c];        // column c holds B[0..3][c]
      end
    for (int i = 0; i < 4; i++) begin ar[i] = ta[i]; bc[i] = tb[i]; end
    while (busy) @(negedge clk);
    start = 1; t_start = cyc;
    @(negedge clk); start = 0;
    while (!done) @(posedge clk);
    lat_sum += cyc - t_start; nops++;
    @(negedge clk);
    for (int r = 0; r < 4; r++)
      for (int c = 0; c < 4; c++) begin
        int exp;
        exp = 0;
        for (int k = 0; k < 4; k++) exp += A[r][k] * B[k][c];       // 32-bit wrap, as the RTL
        `CHECK_EQ(rr[r][c*32 +: 32], 32'(exp), $sformatf("C[%0d][%0d]", r, c))
      end
  endtask

  initial begin
    longint c0;
    int unsigned seed;
    if (!$value$plusargs("seed=%d", seed)) seed = 1;
    void'($urandom(seed));
    for (int i = 0; i < 4; i++) begin ar[i] = '0; bc[i] = '0; end
    repeat (3) @(negedge clk); rst_n = 1; repeat (2) @(negedge clk);
    run_one(1);
    tb_metric("sf1_tensor_latency_cycles", real'(lat_sum));
    c0 = cyc; nops = 0;
    for (int k = 0; k < 200; k++) run_one(k % 2);
    tb_metric("sf1_tensor_products_per_cycle", real'(nops) / real'(cyc - c0));
    tb_metric("sf1_tensor_macs_per_cycle", 64.0 * real'(nops) / real'(cyc - c0));
    tb_finish();
  end
  initial begin #5_000_000; `CHECK(0, "global timeout"); tb_finish(); end
endmodule
