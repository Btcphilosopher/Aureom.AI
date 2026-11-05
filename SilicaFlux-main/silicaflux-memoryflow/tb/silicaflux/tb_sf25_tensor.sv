// =============================================================================
// tb_sf25_tensor :: characterisation of the EXISTING SilicaFlux 2.5 tensor
//                   unit (tensor_unit.sf, unmodified)
//
//   C[i][j] = sum_k A[i][k] * B[k][j]   (signed OP_W operands, exact ACC_W
//   accumulation, narrowed to OUT_W by wrap or saturate, per-element enable)
//
// Phases
//   1  idle issue-to-result latency
//   2  sustained issue rate, results always accepted
//   3  sustained rate with random 50 % result backpressure
//   4  sustained rate when results drain 1 cycle in 4 (a 512-bit result through
//      ONE 128-bit vector-register write port, the Gen-2.5 register_bank)
//   5  random A/B/element-enable/overflow-mode traffic vs the golden model
//   6  flush with work in flight: nothing from before the flush is delivered
// Every delivered result is checked (data, overflow flags, enables, tag order).
// =============================================================================
`timescale 1ns/1ps
`include "tb_common.svh"

module tb_sf25_tensor #(
  parameter int unsigned DIM = 4,
  parameter int unsigned OP_W = 8,
  parameter int unsigned OUT_W = 32
);
  localparam int unsigned PROD_W = 2 * OP_W;
  localparam int unsigned ACC_W  = PROD_W + $clog2(DIM);
  localparam int unsigned TAG_W  = 8;

  logic clk = 0, rst_n = 0;
  always #5 clk = ~clk;
  longint cyc = 0;
  always @(posedge clk) cyc <= cyc + 1;

  typedef logic [DIM-1:0][DIM-1:0][OP_W-1:0]  mat_t;
  typedef logic [DIM-1:0][DIM-1:0][OUT_W-1:0] res_t;
  typedef logic [DIM-1:0][DIM-1:0]            msk_t;

  logic flush = 0, i_vld = 0, i_rdy, r_vld, r_rdy = 1, busy;
  mat_t a = '0, b = '0;
  msk_t en = '1, en_o, ovf_o;
  logic [1:0] mode = 2'b00;
  logic [TAG_W-1:0] tag = '0, tag_o;
  res_t c_o;

  tensor_unit #(.DIM(DIM), .OP_W(OP_W), .OUT_W(OUT_W), .TAG_W(TAG_W)) dut (
    .clk_i(clk), .rst_ni(rst_n), .flush_i(flush),
    .issue_valid_i(i_vld), .issue_ready_o(i_rdy), .mat_a_i(a), .mat_b_i(b), .elem_en_i(en),
    .ovf_mode_i(mode), .tag_i(tag),
    .res_valid_o(r_vld), .res_ready_i(r_rdy), .mat_c_o(c_o), .elem_en_o(en_o), .elem_ovf_o(ovf_o),
    .tag_o(tag_o), .busy_o(busy));

  // ------------------------------------------------------------------ golden model
  typedef struct packed { res_t c; msk_t ovf; msk_t en; logic [TAG_W-1:0] tag; } exp_t;

  function automatic exp_t golden(mat_t A, mat_t B, msk_t E, logic [1:0] M, logic [TAG_W-1:0] T);
    exp_t e;
    longint acc, lo, hi;
    lo = -(longint'(1) <<< (OUT_W - 1));
    hi = (longint'(1) <<< (OUT_W - 1)) - 1;
    e.tag = T; e.en = E;
    for (int i = 0; i < int'(DIM); i++)
      for (int j = 0; j < int'(DIM); j++) begin
        acc = 0;
        for (int k = 0; k < int'(DIM); k++)
          acc += longint'($signed(A[i][k])) * longint'($signed(B[k][j]));
        e.ovf[i][j] = E[i][j] && (acc < lo || acc > hi);
        if (!E[i][j])                         e.c[i][j] = '0;
        else if (M == 2'b00)                  e.c[i][j] = OUT_W'(acc);                // wrap
        else if (acc > hi)                    e.c[i][j] = OUT_W'(hi);                 // saturate
        else if (acc < lo)                    e.c[i][j] = OUT_W'(lo);
        else                                  e.c[i][j] = OUT_W'(acc);
      end
    return e;
  endfunction

  localparam int QD = 4096;
  exp_t ring [QD];
  int   qh = 0, qt = 0;
  longint issued = 0, retired = 0, first_issue = -1, last_issue = 0, last_ret = 0, flushed = 0;

  always @(posedge clk) if (rst_n) begin
    if (flush) begin
      flushed += (qt - qh); qh = qt;                        // in-flight work is killed
    end else begin
      if (i_vld && i_rdy) begin
        ring[qt % QD] = golden(a, b, en, mode, tag); qt++;
        issued++; last_issue = cyc;
        if (first_issue < 0) first_issue = cyc;
      end
      if (r_vld && r_rdy) begin
        if (qh == qt) `CHECK(0, "result with no outstanding issue")
        else begin
          exp_t e;
          e = ring[qh % QD]; qh++;
          `CHECK_EQ(tag_o, e.tag, "result tag (in order)")
          `CHECK_EQ(en_o, e.en, "result element enables")
          `CHECK_EQ(ovf_o, e.ovf, "per-element narrowing overflow flags")
          `CHECK_EQ(c_o, e.c, "C = A x B (narrowed)")
        end
        retired++; last_ret = cyc;
      end
    end
  end

  // ------------------------------------------------------------------ drivers
  int unsigned drain_mode = 0;     // 0 always ready, 1 random 50 %, 2 one cycle in four
  int unsigned phase4_cnt = 0;
  always @(negedge clk) begin
    phase4_cnt++;
    case (drain_mode)
      0: r_rdy = 1'b1;
      1: r_rdy = $urandom_range(0, 1);
      default: r_rdy = (phase4_cnt % 4) == 0;
    endcase
  end

  function automatic mat_t rnd_mat(int unsigned kind);
    mat_t m;
    for (int i = 0; i < int'(DIM); i++)
      for (int j = 0; j < int'(DIM); j++)
        case (kind)
          0: m[i][j] = OP_W'($urandom);
          1: m[i][j] = $urandom_range(0, 1) ? {1'b1, {(OP_W-1){1'b0}}} : {1'b0, {(OP_W-1){1'b1}}}; // extremes
          default: m[i][j] = OP_W'($urandom_range(0, 3)) - OP_W'(1);
        endcase
    return m;
  endfunction

  // issue one operation (called at negedge); whole-signal assignments only
  task automatic issue(mat_t A, mat_t B, msk_t E, logic [1:0] M);
    a = A; b = B; en = E; mode = M; tag = TAG_W'(issued + 1); i_vld = 1;
    #1; while (!i_rdy) begin @(negedge clk); #1; end
    @(negedge clk); i_vld = 0;
  endtask

  task automatic wait_idle(int max = 20000);
    int n; n = 0;
    while ((qh != qt || busy || r_vld) && n < max) begin @(negedge clk); n++; end
    `CHECK(n < max, "tensor unit drained")
  endtask

  longint c0, n0;
  initial begin
    int unsigned seed;
    if (!$value$plusargs("seed=%d", seed)) seed = 1;
    void'($urandom(seed));
    repeat (3) @(negedge clk);
    rst_n = 1;
    repeat (2) @(negedge clk);

    // ---------------------------------------------------------------- phase 1: latency
    issue(rnd_mat(0), rnd_mat(0), '1, 2'b00);
    wait_idle();
    tb_metric("sf25_tensor_latency_cycles", real'(last_ret - first_issue));

    // ---------------------------------------------------------------- phase 2: sustained, no backpressure
    c0 = cyc; n0 = retired;
    for (int k = 0; k < 2000; k++) issue(rnd_mat(0), rnd_mat(0), '1, 2'b00);
    wait_idle();
    tb_metric("sf25_tensor_products_per_cycle", real'(retired - n0) / real'(last_ret - c0));
    tb_metric("sf25_tensor_macs_per_cycle", real'((retired - n0) * DIM * DIM * DIM) / real'(last_ret - c0));
    tb_metric("sf25_tensor_operand_bytes_per_product", real'(2 * DIM * DIM * OP_W / 8));
    tb_metric("sf25_tensor_result_bytes_per_product", real'(DIM * DIM * OUT_W / 8));

    // ---------------------------------------------------------------- phase 3: 50 % backpressure
    drain_mode = 1;
    c0 = cyc; n0 = retired;
    for (int k = 0; k < 2000; k++) issue(rnd_mat(0), rnd_mat(0), '1, 2'b01);
    wait_idle();
    tb_metric("sf25_tensor_products_per_cycle_bp50", real'(retired - n0) / real'(last_ret - c0));

    // ---------------------------------------------------------------- phase 4: one 128-bit drain port
    drain_mode = 2;
    c0 = cyc; n0 = retired;
    for (int k = 0; k < 1000; k++) issue(rnd_mat(0), rnd_mat(0), '1, 2'b00);
    wait_idle();
    tb_metric("sf25_tensor_products_per_cycle_drain1of4", real'(retired - n0) / real'(last_ret - c0));
    drain_mode = 0;

    // ---------------------------------------------------------------- phase 5: random functional
    drain_mode = 1;
    for (int k = 0; k < 3000; k++) begin
      msk_t e;
      e = $urandom_range(0, 7) == 0 ? msk_t'($urandom) : '1;
      issue(rnd_mat($urandom_range(0, 2)), rnd_mat($urandom_range(0, 2)), e, 2'($urandom_range(0, 1)));
      if ($urandom_range(0, 7) == 0) @(negedge clk);
    end
    wait_idle();
    drain_mode = 0;

    // ---------------------------------------------------------------- phase 6: flush in flight
    for (int k = 0; k < 6; k++) issue(rnd_mat(0), rnd_mat(0), '1, 2'b00);
    flush = 1; @(negedge clk); flush = 0;
    `CHECK(qh == qt, "flush discarded every in-flight operation")
    repeat (40) @(negedge clk);
    `CHECK(!r_vld, "no result surfaces after a flush")
    issue(rnd_mat(0), rnd_mat(0), '1, 2'b01);
    wait_idle();
    tb_metric("sf25_tensor_flushed_ops", real'(flushed));
    tb_metric("sf25_tensor_results_checked", real'(retired));
    tb_finish();
  end

  initial begin #20_000_000; `CHECK(0, "global timeout"); tb_finish(); end
endmodule
