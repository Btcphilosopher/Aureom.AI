// =============================================================================
// tb_accel :: accelerator dataflow blocks
//  A  sf_tensor_array vs Python golden tiles (K = 1, 8, 37) with random
//     valid gaps on A/B and random backpressure on C
//  B  accumulation double-buffering: 8 back-to-back tiles, K = 8 and K = 32,
//     ACC_DBUF = 1 vs 0 -> cycles + MAC utilisation (RTL-measured)
//  C  sf_vec_unit ADD / MUL / AXPY / DOT vs reference, joined streams
//  D  sf_reuse_buffer: 3 tiles x replay 3, backpressure, ping-pong overlap
//
// TB structure (Verilator-robust): every DUT input is driven by exactly ONE
// static always block (a stream "source" in g_src[s]); the main thread only
// loads jobs into memories and waits for completion.  No concurrent tasks
// write shared signals.
// =============================================================================
`timescale 1ns/1ps
`default_nettype none
`include "tb_common.svh"

module tb_accel;
  localparam int DW = 64;
  localparam int NS = 7;                  // stream sources
  localparam int S_T1A = 0, S_T1B = 1, S_T0A = 2, S_T0B = 3, S_VA = 4, S_VB = 5, S_RI = 6;
  localparam int MEMD = 4096;

  logic clk = 0, rst_n = 0;
  always #5 clk = ~clk;
  longint cyc = 0;
  always @(posedge clk) cyc <= cyc + 1;

  // ================================================================ stream sources
  logic [DW-1:0] smem [NS][MEMD];
  int  s_n    [NS];       // beats per pass
  int  s_rep  [NS];       // passes
  int  s_last [NS];       // last asserted every s_last beats (0 = never)
  int  s_pct  [NS];       // valid probability (%)
  int  s_done [NS];       // beats accepted
  bit  s_go   [NS];

  generate
    for (genvar s = 0; s < NS; s++) begin : g_src
      logic          v;
      logic [DW-1:0] d;
      logic          l;
      logic          r;             // connected to DUT ready
      int            k;
      always @(posedge clk) begin
        if (!rst_n) begin
          v <= 1'b0; d <= '0; l <= 1'b0; k = 0;
        end else begin
          if (v && r) k = k + 1;                    // handshake at this edge
          if (s_go[s] && k < s_n[s] * s_rep[s]) begin
            v <= ($urandom_range(0, 99) < s_pct[s]);
            d <= smem[s][k % s_n[s]];
            l <= (s_last[s] != 0) && ((k % s_last[s]) == s_last[s] - 1);
          end else begin
            v <= 1'b0;
          end
          s_done[s] = k;
        end
      end
    end
  endgenerate

  task automatic src_start(int s, int n, int rep, int lst, int pct);
    // caller has filled smem[s][0 .. n-1]
    s_go[s] = 0;
    @(negedge clk);
    s_n[s] = n; s_rep[s] = rep; s_last[s] = lst; s_pct[s] = pct;
    s_go[s] = 1;
  endtask

  // resets the beat counter of a source (between jobs)
  task automatic src_reset(int s);
    s_go[s] = 0;
    case (s)
      0: g_src[0].k = 0;  1: g_src[1].k = 0;  2: g_src[2].k = 0;  3: g_src[3].k = 0;
      4: g_src[4].k = 0;  5: g_src[5].k = 0;  default: g_src[6].k = 0;
    endcase
    s_done[s] = 0;
  endtask

  task automatic src_wait(int s);
    while (s_done[s] < s_n[s] * s_rep[s]) @(negedge clk);
  endtask

  // ================================================================ sinks
  int   rpct_t = 100, rpct_v = 70, rpct_r = 100;
  logic t1_cr, t0_cr, v_rr, rb_or;
  always @(negedge clk) t1_cr = ($urandom_range(0, 99) < rpct_t);
  always @(negedge clk) t0_cr = ($urandom_range(0, 99) < rpct_t);
  always @(negedge clk) v_rr  = ($urandom_range(0, 99) < rpct_v);
  always @(negedge clk) rb_or = ($urandom_range(0, 99) < rpct_r);

  // ================================================================ tensor DUTs
  logic [15:0] k_cfg;
  logic        t1_cv, t1_cl, t0_cv, t0_cl;
  logic [DW-1:0] t1_cd, t0_cd;
  logic [31:0] t1_mac, t1_si, t1_sa, t1_tl, t0_mac, t0_si, t0_sa, t0_tl;

  sf_tensor_array #(.ACC_DBUF(1'b1)) u_t1 (
    .clk, .rst_n, .cfg_k(k_cfg), .perf_clear(1'b0),
    .a_valid(g_src[S_T1A].v), .a_ready(g_src[S_T1A].r), .a_data(g_src[S_T1A].d),
    .b_valid(g_src[S_T1B].v), .b_ready(g_src[S_T1B].r), .b_data(g_src[S_T1B].d),
    .c_valid(t1_cv), .c_ready(t1_cr), .c_data(t1_cd), .c_last(t1_cl),
    .cnt_mac(t1_mac), .cnt_stall_in(t1_si), .cnt_stall_acc(t1_sa), .cnt_tiles(t1_tl));
  sf_tensor_array #(.ACC_DBUF(1'b0)) u_t0 (
    .clk, .rst_n, .cfg_k(k_cfg), .perf_clear(1'b0),
    .a_valid(g_src[S_T0A].v), .a_ready(g_src[S_T0A].r), .a_data(g_src[S_T0A].d),
    .b_valid(g_src[S_T0B].v), .b_ready(g_src[S_T0B].r), .b_data(g_src[S_T0B].d),
    .c_valid(t0_cv), .c_ready(t0_cr), .c_data(t0_cd), .c_last(t0_cl),
    .cnt_mac(t0_mac), .cnt_stall_in(t0_si), .cnt_stall_acc(t0_sa), .cnt_tiles(t0_tl));

  logic [DW-1:0] cbuf [2][MEMD];
  int            cn [2];
  always @(posedge clk) begin
    if (rst_n && t1_cv && t1_cr) begin
      cbuf[1][cn[1] % MEMD] = t1_cd;
      `CHECK_EQ(t1_cl, ((cn[1] % 32) == 31), "tensor(dbuf1) C last on 32nd beat")
      cn[1] = cn[1] + 1;
    end
    if (rst_n && t0_cv && t0_cr) begin
      cbuf[0][cn[0] % MEMD] = t0_cd;
      `CHECK_EQ(t0_cl, ((cn[0] % 32) == 31), "tensor(dbuf0) C last on 32nd beat")
      cn[0] = cn[0] + 1;
    end
  end

  logic [DW-1:0] ga [64], gb [64], gc [64];

  task automatic tensor_load(int k, int rep, int pct);
    for (int s = 0; s < 4; s++) src_reset(s);
    for (int i = 0; i < k; i++) begin
      smem[S_T1A][i] = ga[i]; smem[S_T0A][i] = ga[i];
      smem[S_T1B][i] = gb[i]; smem[S_T0B][i] = gb[i];
    end
    k_cfg = 16'(k);
    cn[0] = 0; cn[1] = 0;
    src_start(S_T1A, k, rep, 0, pct); src_start(S_T1B, k, rep, 0, pct);
    src_start(S_T0A, k, rep, 0, pct); src_start(S_T0B, k, rep, 0, pct);
  endtask

  task automatic tensor_golden(int k, input string tag);
    $readmemh($sformatf("ten_k%0d_a.hex", k), ga);
    $readmemh($sformatf("ten_k%0d_b.hex", k), gb);
    $readmemh($sformatf("ten_k%0d_c.hex", k), gc);
    rpct_t = 60;
    tensor_load(k, 2, 60);
    while (cn[0] < 64 || cn[1] < 64) @(negedge clk);
    for (int d = 0; d < 2; d++) for (int t = 0; t < 2; t++) for (int i = 0; i < 32; i++)
      `CHECK_EQ(cbuf[d][t * 32 + i], gc[i], $sformatf("%s dbuf=%0d tile %0d beat %0d vs Python golden", tag, d, t, i))
  endtask

  task automatic tensor_timing(int k, int tiles);
    longint t0, te1, te0;
    int     m1, m0;
    for (int i = 0; i < k; i++) begin ga[i] = {$urandom(), $urandom()}; gb[i] = {$urandom(), $urandom()}; end
    rpct_t = 100;
    m1 = t1_mac; m0 = t0_mac;
    tensor_load(k, tiles, 100);
    t0 = cyc;
    te1 = 0; te0 = 0;
    while (te1 == 0 || te0 == 0) begin
      @(negedge clk);
      if (te1 == 0 && cn[1] >= 32 * tiles) te1 = cyc;
      if (te0 == 0 && cn[0] >= 32 * tiles) te0 = cyc;
    end
    tb_metric($sformatf("tensor_dbuf1_k%0d_%0dtiles_cycles", k, tiles), real'(te1 - t0));
    tb_metric($sformatf("tensor_dbuf0_k%0d_%0dtiles_cycles", k, tiles), real'(te0 - t0));
    tb_metric($sformatf("tensor_dbuf1_k%0d_mac_util", k), real'(t1_mac - m1) / real'(te1 - t0));
    tb_metric($sformatf("tensor_dbuf0_k%0d_mac_util", k), real'(t0_mac - m0) / real'(te0 - t0));
    `CHECK(te1 < te0, $sformatf("double-buffered accumulators faster (K=%0d)", k))
  endtask

  // ================================================================ vector unit
  logic [1:0]  v_op;
  logic [15:0] v_alpha;
  logic        vr_v, vr_l;
  logic [DW-1:0] vr_d;
  logic [31:0] v_act, v_st, v_os;
  sf_vec_unit u_vec (
    .clk, .rst_n, .cfg_op(v_op), .cfg_alpha(v_alpha), .perf_clear(1'b0),
    .a_valid(g_src[S_VA].v), .a_ready(g_src[S_VA].r), .a_data(g_src[S_VA].d), .a_last(g_src[S_VA].l),
    .b_valid(g_src[S_VB].v), .b_ready(g_src[S_VB].r), .b_data(g_src[S_VB].d),
    .r_valid(vr_v), .r_ready(v_rr), .r_data(vr_d), .r_last(vr_l),
    .cnt_active(v_act), .cnt_starve(v_st), .cnt_ostall(v_os));

  logic [DW-1:0] vR [MEMD];
  int vrn;
  always @(posedge clk) if (rst_n && vr_v && v_rr) begin vR[vrn % MEMD] = vr_d; vrn = vrn + 1; end

  function automatic logic signed [15:0] lane(logic [DW-1:0] w, int l); return w[l*16 +: 16]; endfunction

  task automatic vec_run(logic [1:0] op, int n, logic [15:0] alpha);
    src_reset(S_VA); src_reset(S_VB);
    v_op = op; v_alpha = alpha; vrn = 0;
    for (int i = 0; i < n; i++) begin smem[S_VA][i] = {$urandom(), $urandom()}; smem[S_VB][i] = {$urandom(), $urandom()}; end
    src_start(S_VA, n, 1, n, 70);
    src_start(S_VB, n, 1, 0, 50);
    if (op == 2'd2) begin
      longint s;
      while (vrn < 1) @(negedge clk);
      s = 0;
      for (int i = 0; i < n; i++) for (int l = 0; l < 4; l++)
        s += longint'(lane(smem[S_VA][i], l)) * longint'(lane(smem[S_VB][i], l));
      `CHECK_EQ(vR[0], 64'(s), $sformatf("vec DOT n=%0d", n))
    end else begin
      while (vrn < n) @(negedge clk);
      for (int i = 0; i < n; i++) for (int l = 0; l < 4; l++) begin
        logic [15:0] e;
        logic signed [15:0] xa, xb;
        xa = lane(smem[S_VA][i], l); xb = lane(smem[S_VB][i], l);
        case (op)
          2'd0: e = 16'(xa + xb);
          2'd1: e = 16'(xa * xb);
          default: e = 16'($signed(alpha) * xa) + 16'(xb);
        endcase
        `CHECK_EQ(vR[i][l*16 +: 16], e, $sformatf("vec op %0d beat %0d lane %0d", op, i, l))
      end
    end
    src_wait(S_VA); src_wait(S_VB);
    repeat (4) @(negedge clk);
    `CHECK_EQ(vrn, (op == 2'd2) ? 1 : n, "vec result beat count")
  endtask

  // ================================================================ reuse buffer
  logic [7:0]  rb_rep;
  logic        ro_v, ro_l;
  logic [DW-1:0] ro_d;
  logic [1:0]  rb_full;
  logic [31:0] rb_cnt;
  sf_reuse_buffer #(.DEPTH(16)) u_rb (
    .clk, .rst_n, .cfg_replay(rb_rep),
    .in_valid(g_src[S_RI].v), .in_ready(g_src[S_RI].r), .in_data(g_src[S_RI].d), .in_last(g_src[S_RI].l),
    .out_valid(ro_v), .out_ready(rb_or), .out_data(ro_d), .out_last(ro_l),
    .bank_full(rb_full), .cnt_replayed_beats(rb_cnt));

  logic [DW-1:0] rbo [512];
  logic          rbl [512];
  int            rbn;
  always @(posedge clk) if (rst_n && ro_v && rb_or) begin rbo[rbn % 512] = ro_d; rbl[rbn % 512] = ro_l; rbn = rbn + 1; end

  // ================================================================ main
  initial begin
    for (int s = 0; s < NS; s++) begin s_n[s] = 0; s_rep[s] = 0; s_last[s] = 0; s_pct[s] = 100; s_done[s] = 0; s_go[s] = 0; end
    cn[0] = 0; cn[1] = 0; vrn = 0; rbn = 0; rb_rep = 8'd1; k_cfg = 16'd8; v_op = 0; v_alpha = 16'd1;
    repeat (3) @(negedge clk);
    rst_n = 1;
    @(negedge clk);

    // A
    tensor_golden(1, "K=1");
    tensor_golden(8, "K=8");
    tensor_golden(37, "K=37");
    // B
    tensor_timing(8, 8);
    tensor_timing(32, 8);
    // C
    vec_run(2'd0, 40, 16'd1);
    vec_run(2'd1, 40, 16'd1);
    vec_run(2'd3, 40, 16'hFFFD);   // alpha = -3
    vec_run(2'd2, 50, 16'd1);
    vec_run(2'd2, 1, 16'd1);
    `CHECK(v_act > 0 && v_st > 0, "vec perf counters count activity and starvation")

    // D: reuse buffer, 3 tiles of 16 beats, replay 3, output backpressure
    begin
      longint t_in_tile1_done, t_out_pass3_of_tile0;
      rb_rep = 8'd3; rbn = 0; rpct_r = 50;
      src_reset(S_RI);
      for (int i = 0; i < 48; i++) smem[S_RI][i] = {$urandom(), $urandom()};
      src_start(S_RI, 48, 1, 16, 100);
      t_in_tile1_done = 0; t_out_pass3_of_tile0 = 0;
      while (rbn < 144) begin
        @(negedge clk);
        if (t_in_tile1_done == 0 && s_done[S_RI] >= 32) t_in_tile1_done = cyc;
        if (t_out_pass3_of_tile0 == 0 && rbn >= 48) t_out_pass3_of_tile0 = cyc;
      end
      for (int t = 0; t < 3; t++) for (int r = 0; r < 3; r++) for (int i = 0; i < 16; i++) begin
        int k;
        k = (t * 3 + r) * 16 + i;
        `CHECK_EQ(rbo[k], smem[S_RI][t * 16 + i], $sformatf("reuse tile %0d pass %0d beat %0d", t, r, i))
        `CHECK_EQ(rbl[k], (i == 15), "reuse last at end of each pass")
      end
      `CHECK(t_in_tile1_done != 0 && t_in_tile1_done < t_out_pass3_of_tile0,
             "ping-pong: tile 1 filled while tile 0 still replaying")
      `CHECK_EQ(rb_cnt, 32'd144, "replayed beat counter")
    end
    tb_finish();
  end

  initial begin
    #100ms;
    $display("TIMEOUT");
    tb_finish();
  end
endmodule

`default_nettype wire
