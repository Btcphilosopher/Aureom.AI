// =============================================================================
// tb_sram_prims :: SRAM primitive / abstraction-layer verification
//  1. sf_sram_1rw IMPL=0 (inferred) and IMPL=1 (macro tiled 3 cols x 4 rows)
//     driven with identical random traffic -> identical read data, and both
//     match a behavioural reference (lane write enables, rdata hold).
//  2. sf_sram_1r1w_inferred: read-during-write same address returns OLD data.
//  3. sf_sram_2rw_inferred: concurrent dual-port traffic vs reference.
// =============================================================================
`timescale 1ns/1ps
`default_nettype none
`include "tb_common.svh"

module tb_sram_prims;
  localparam int LW = 9, LN = 8, W = LW * LN, D = 1024, AW = 10;
  logic clk = 0;
  always #5 clk = ~clk;

  // ------------------------------------------------ 1RW inferred vs macro
  logic          ce, we;
  logic [LN-1:0] lwe;
  logic [AW-1:0] addr;
  logic [W-1:0]  wd, rd_inf, rd_mac;

  sf_sram_1rw #(.LANE_W(LW), .LANES(LN), .DEPTH(D), .IMPL(0)) u_inf (
    .clk, .ce, .we, .lane_we(lwe), .addr, .wdata(wd), .rdata(rd_inf),
    .lp_sleep(1'b0), .lp_shutdown(1'b0));
  sf_sram_1rw #(.LANE_W(LW), .LANES(LN), .DEPTH(D), .IMPL(1), .MACRO_W(32), .MACRO_D(256)) u_mac (
    .clk, .ce, .we, .lane_we(lwe), .addr, .wdata(wd), .rdata(rd_mac),
    .lp_sleep(1'b0), .lp_shutdown(1'b0));

  logic [W-1:0] ref1 [D];
  logic [W-1:0] exp_q;
  logic         exp_valid;

  // ------------------------------------------------ 1R1W
  logic          p_we, p_re;
  logic [LN-1:0] p_lwe;
  logic [AW-1:0] p_wa, p_ra;
  logic [W-1:0]  p_wd, p_rd;
  sf_sram_1r1w_inferred #(.LANE_W(LW), .LANES(LN), .DEPTH(D)) u_2p (
    .clk, .we(p_we), .lane_we(p_lwe), .waddr(p_wa), .wdata(p_wd),
    .re(p_re), .raddr(p_ra), .rdata(p_rd));

  // ------------------------------------------------ 2RW
  logic          a_ce, a_we, b_ce, b_we;
  logic [LN-1:0] a_lwe, b_lwe;
  logic [AW-1:0] a_ad, b_ad;
  logic [W-1:0]  a_wd, b_wd, a_rd, b_rd;
  sf_sram_2rw_inferred #(.LANE_W(LW), .LANES(LN), .DEPTH(D)) u_dp (
    .clk, .a_ce, .a_we, .a_lane_we(a_lwe), .a_addr(a_ad), .a_wdata(a_wd), .a_rdata(a_rd),
    .b_ce, .b_we, .b_lane_we(b_lwe), .b_addr(b_ad), .b_wdata(b_wd), .b_rdata(b_rd));

  function automatic logic [W-1:0] merge(logic [W-1:0] old, logic [W-1:0] nw, logic [LN-1:0] m);
    logic [W-1:0] r;
    r = old;
    for (int l = 0; l < LN; l++) if (m[l]) r[l*LW +: LW] = nw[l*LW +: LW];
    return r;
  endfunction

  function automatic logic [W-1:0] rnd_word();
    return {$urandom(), $urandom(), $urandom()};
  endfunction

  int reads;

  initial begin
    // ---------- phase 1: initialise all words through both IMPLs
    ce = 0; we = 0; lwe = '0; addr = '0; wd = '0;
    @(negedge clk);
    for (int i = 0; i < D; i++) begin
      ce = 1; we = 1; lwe = '1; addr = AW'(i); wd = rnd_word(); ref1[i] = wd;
      @(negedge clk);
    end
    ce = 0;
    // ---------- phase 2: random traffic, compare every read
    exp_valid = 0;
    reads = 0;
    for (int n = 0; n < 20000; n++) begin
      ce  = ($urandom_range(0, 9) != 0);
      we  = $urandom_range(0, 1);
      lwe = LN'($urandom());
      addr = AW'($urandom_range(0, D - 1));
      wd  = rnd_word();
      @(posedge clk); #1;
      if (ce && !we) begin
        exp_q = ref1[addr];
        exp_valid = 1;
        reads++;
      end
      // rdata must equal the latest read and HOLD when no read was issued
      if (exp_valid) begin
        `CHECK_EQ(rd_inf, exp_q, "1RW inferred read data")
        `CHECK_EQ(rd_mac, exp_q, "1RW macro-tiled read data (abstraction equivalence)")
      end
      if (ce && we) ref1[addr] = merge(ref1[addr], wd, lwe);
      @(negedge clk);
    end
    ce = 0;
    tb_metric("sram_1rw_random_reads", real'(reads));

    // ---------- 1R1W read-first
    p_we = 0; p_re = 0; p_lwe = '1;
    @(negedge clk);
    p_we = 1; p_wa = 10'd5; p_wd = {W{1'b1}} ^ 72'h1; @(negedge clk);   // old value
    p_we = 1; p_wa = 10'd5; p_wd = 72'h0123_4567_89AB_CDEF_11;           // new value...
    p_re = 1; p_ra = 10'd5;                                              // ...read same cycle
    @(posedge clk); #1;
    `CHECK_EQ(p_rd, {W{1'b1}} ^ 72'h1, "1R1W read-during-write returns OLD data")
    @(negedge clk);
    p_we = 0; p_re = 1; p_ra = 10'd5;
    @(posedge clk); #1;
    `CHECK_EQ(p_rd, 72'h0123_4567_89AB_CDEF_11, "1R1W read after write returns NEW data")
    @(negedge clk);
    p_re = 0;

    // ---------- 2RW concurrent
    for (int i = 0; i < D; i++) ref1[i] = '0;
    a_ce = 0; b_ce = 0;
    @(negedge clk);
    for (int i = 0; i < D; i++) begin
      a_ce = 1; a_we = 1; a_lwe = '1; a_ad = AW'(i); a_wd = '0;
      b_ce = 0;
      @(negedge clk);
    end
    for (int n = 0; n < 5000; n++) begin
      logic [W-1:0] ea, eb;
      logic         va, vb;
      a_ce = 1; b_ce = 1;
      a_we = $urandom_range(0, 1); b_we = $urandom_range(0, 1);
      a_ad = AW'($urandom_range(0, 511)); b_ad = AW'($urandom_range(512, 1023)); // disjoint writes
      if (!b_we && $urandom_range(0, 3) == 0) b_ad = a_ad;                     // shared reads
      a_lwe = LN'($urandom()); b_lwe = LN'($urandom());
      a_wd = rnd_word(); b_wd = rnd_word();
      va = !a_we; vb = !b_we;
      ea = ref1[a_ad]; eb = ref1[b_ad];
      @(posedge clk); #1;
      if (va) `CHECK_EQ(a_rd, ea, "2RW port A read")
      if (vb) `CHECK_EQ(b_rd, eb, "2RW port B read (old data on same-addr write)")
      if (a_we) ref1[a_ad] = merge(ref1[a_ad], a_wd, a_lwe);
      if (b_we) ref1[b_ad] = merge(ref1[b_ad], b_wd, b_lwe);
      @(negedge clk);
    end
    tb_finish();
  end
endmodule

`default_nettype wire
