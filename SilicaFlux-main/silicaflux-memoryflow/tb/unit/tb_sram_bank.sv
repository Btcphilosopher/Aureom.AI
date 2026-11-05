// =============================================================================
// tb_sram_bank :: protected SRAM bank verification (parameter ECC_MODE, IMPL)
//  * random reads / full writes / partial (byte-enable) writes vs reference
//  * exact 2-cycle response latency, tags returned in order
//  * read-after-RMW hazard (partial write then immediate read)
//  * ECC_MODE 2: 1-bit inject -> corrected; 2-bit -> uncorrectable;
//               partial write onto 1-bit error scrubs; onto 2-bit error is
//               suppressed (word stays detectably bad)
//  * ECC_MODE 1: parity detects single-bit flips, byte writes native
//  * MBIST raw port write/read of the full stored word
// =============================================================================
`timescale 1ns/1ps
`default_nettype none
`include "tb_common.svh"

module tb_sram_bank #(
  parameter int ECC_MODE = 2,
  parameter int IMPL     = 0
);
  localparam int DW = 64, NB = 8, DEPTH = 256, AW = 8, TAGW = 4;
  localparam int R  = 7;
  localparam int SW = (ECC_MODE == 2) ? (DW + R + 1) : (ECC_MODE == 1) ? (NB * 9) : DW;

  logic clk = 0, rst_n = 0;
  always #5 clk = ~clk;
  longint cyc = 0;
  always @(posedge clk) cyc <= cyc + 1;

  logic            req_valid, req_ready, req_we;
  logic [AW-1:0]   req_addr;
  logic [DW-1:0]   req_wdata;
  logic [NB-1:0]   req_wstrb;
  logic [TAGW-1:0] req_tag;
  logic            rsp_valid, rsp_we, rsp_corr, rsp_uncorr;
  logic [DW-1:0]   rsp_rdata;
  logic [TAGW-1:0] rsp_tag;
  logic            inj_en;
  logic [SW-1:0]   inj_mask;
  logic            bist_en, bist_ce, bist_we;
  logic [AW-1:0]   bist_addr;
  logic [SW-1:0]   bist_wdata, bist_rdata;

  sf_sram_bank #(.DW(DW), .DEPTH(DEPTH), .ECC_MODE(ECC_MODE), .TAGW(TAGW),
                 .IMPL(IMPL), .MACRO_W(72), .MACRO_D(128)) dut (
    .clk, .rst_n, .req_valid, .req_ready, .req_we, .req_addr, .req_wdata, .req_wstrb,
    .req_tag, .rsp_valid, .rsp_we, .rsp_rdata, .rsp_tag, .rsp_corr, .rsp_uncorr,
    .inj_en, .inj_mask, .bist_en, .bist_ce, .bist_we, .bist_addr, .bist_wdata, .bist_rdata,
    .lp_sleep(1'b0), .lp_shutdown(1'b0));

  // ---------------------------------------------------------------- reference
  logic [DW-1:0] refm [DEPTH];

  typedef struct {
    longint        due;
    logic          we;
    logic [TAGW-1:0] tag;
    logic [DW-1:0] data;
    logic          chk_data;
    logic          exp_corr;
    logic          exp_unc;
    logic          chk_flags;
  } exp_t;
  exp_t q[$];
  int   rsp_seen = 0;

  function automatic logic [DW-1:0] merge(logic [DW-1:0] o, logic [DW-1:0] n, logic [NB-1:0] m);
    for (int b = 0; b < NB; b++) if (m[b]) o[b*8 +: 8] = n[b*8 +: 8];
    return o;
  endfunction

  // monitor: exact latency + content
  always @(posedge clk) begin
    if (rst_n) begin
      if (q.size() > 0 && q[0].due == cyc) begin
        exp_t e;
        e = q.pop_front();
        `CHECK(rsp_valid, "response present at exact latency")
        `CHECK_EQ(rsp_tag, e.tag, "response tag order")
        `CHECK_EQ(rsp_we, e.we, "response type")
        if (e.chk_data) `CHECK_EQ(rsp_rdata, e.data, "read data")
        if (e.chk_flags) begin
          `CHECK_EQ(rsp_corr, e.exp_corr, "corrected flag")
          `CHECK_EQ(rsp_uncorr, e.exp_unc, "uncorrectable flag")
        end
        rsp_seen++;
      end else begin
        `CHECK(!rsp_valid, "no spurious response")
      end
    end
  end

  logic [TAGW-1:0] tagc = '0;

  // issue one request; blocks until accepted. flags expectations explicit.
  task automatic issue(input logic we, input logic [AW-1:0] a, input logic [DW-1:0] d,
                       input logic [NB-1:0] s, input logic chk_data = 1,
                       input logic ec = 0, input logic eu = 0, input logic chk_flags = 1);
    exp_t e;
    bit   acc;
    // called just after a negedge; inputs stable until the next negedge
    req_valid = 1; req_we = we; req_addr = a; req_wdata = d; req_wstrb = s; req_tag = tagc;
    acc = 0;
    while (!acc) begin
      #1;
      acc = req_ready;             // sampled before the accepting posedge
      if (acc) begin
        e.due = cyc + 2;
        e.we = we; e.tag = tagc; e.chk_flags = chk_flags; e.exp_corr = ec; e.exp_unc = eu;
        e.chk_data = !we && chk_data;
        e.data = refm[a];
        q.push_back(e);
        if (we && !(ECC_MODE == 2 && eu)) refm[a] = merge(refm[a], d, s);
        tagc++;
      end
      @(negedge clk);
    end
    req_valid = 0;
  endtask

  task automatic idle(int n);
    req_valid = 0;
    repeat (n) @(negedge clk);
  endtask

  task automatic drain();
    req_valid = 0;
    while (q.size() > 0) @(negedge clk);
  endtask

  int n_partial = 0;
  longint t0, t1;

  initial begin
    req_valid = 0; req_we = 0; req_addr = '0; req_wdata = '0; req_wstrb = '0; req_tag = '0;
    inj_en = 0; inj_mask = '0; bist_en = 0; bist_ce = 0; bist_we = 0; bist_addr = '0; bist_wdata = '0;
    repeat (3) @(negedge clk);
    rst_n = 1;
    @(negedge clk);

    // ---------------- init
    for (int i = 0; i < DEPTH; i++) issue(1, AW'(i), {$urandom(), $urandom()}, '1);
    drain();

    // ---------------- random traffic (back-to-back with gaps)
    t0 = cyc;
    for (int n = 0; n < 6000; n++) begin
      int kind;
      logic [NB-1:0] s;
      kind = $urandom_range(0, 2);
      s = (kind == 2) ? NB'($urandom()) : '1;
      if (kind == 2 && s == '1) s = 8'h0F;
      if (kind == 2) n_partial++;
      issue(kind != 0, AW'($urandom_range(0, DEPTH - 1)), {$urandom(), $urandom()}, s);
      if ($urandom_range(0, 7) == 0) idle($urandom_range(1, 3));
    end
    drain();
    t1 = cyc;
    tb_metric("bank_random_ops_cycles", real'(t1 - t0));
    tb_metric("bank_partial_writes", real'(n_partial));

    // ---------------- read-after-partial-write hazard, back to back
    for (int i = 0; i < 64; i++) begin
      logic [AW-1:0] a;
      a = AW'($urandom_range(0, DEPTH - 1));
      issue(1, a, {$urandom(), $urandom()}, 8'h3C);
      issue(0, a, '0, '0);
    end
    drain();

    // ---------------- error injection
    if (ECC_MODE == 2) begin
      // single-bit in data, check bits and overall parity
      for (int b = 0; b < SW; b += 7) begin
        logic [DW-1:0] d;
        d = {$urandom(), $urandom()};
        inj_en = 1; inj_mask = SW'(1) << b;
        issue(1, 8'd10, d, '1);
        inj_en = 0; inj_mask = '0;
        issue(0, 8'd10, '0, '0, 1, 1, 0);           // corrected, data intact
      end
      // double-bit -> uncorrectable
      inj_en = 1; inj_mask = (SW'(1) << 3) | (SW'(1) << 40);
      issue(1, 8'd20, 64'hDEAD_BEEF_0000_1111, '1);
      inj_en = 0; inj_mask = '0;
      issue(0, 8'd20, '0, '0, 0, 0, 1);              // data unchecked, flagged
      // partial write onto a double-error word: suppressed, still flagged
      issue(1, 8'd20, 64'hFFFF_FFFF_FFFF_FFFF, 8'h01, 1, 0, 1);
      issue(0, 8'd20, '0, '0, 0, 0, 1);
      // partial write onto a single-error word: merged + scrubbed
      inj_en = 1; inj_mask = SW'(1) << 17;
      issue(1, 8'd30, 64'h1111_2222_3333_4444, '1);
      inj_en = 0; inj_mask = '0;
      issue(1, 8'd30, 64'h0000_0000_0000_00AA, 8'h01, 1, 1, 0);   // RMW corrected
      issue(0, 8'd30, '0, '0, 1, 0, 0);                            // now clean
      `CHECK_EQ(refm[30], 64'h1111_2222_3333_44AA, "reference merged value")
      drain();
    end else if (ECC_MODE == 1) begin
      inj_en = 1; inj_mask = SW'(1) << (9 * 3 + 2);                 // byte 3, bit 2
      issue(1, 8'd40, 64'h0123_4567_89AB_CDEF, '1);
      inj_en = 0; inj_mask = '0;
      issue(0, 8'd40, '0, '0, 0, 0, 1);                             // detected
      issue(1, 8'd40, 64'h0000_0000_0000_0055, 8'h01);               // other byte
      issue(0, 8'd40, '0, '0, 0, 0, 1);                             // still detected
      issue(1, 8'd40, 64'h0000_0000_7700_0000, 8'h08);               // rewrite byte 3
      issue(0, 8'd40, '0, '0, 1, 0, 0);                             // clean again
      refm[40] = merge(refm[40], 64'h0000_0000_7700_0000, 8'h08);
      drain();
    end

    // ---------------- MBIST raw port
    idle(2);
    bist_en = 1;
    #1 `CHECK(!req_ready, "functional port blocked during MBIST")
    for (int i = 0; i < 16; i++) begin
      logic [SW-1:0] pat;
      pat = SW'({$urandom(), $urandom(), $urandom()});
      bist_ce = 1; bist_we = 1; bist_addr = AW'(i); bist_wdata = pat;
      @(negedge clk);
      bist_ce = 1; bist_we = 0; bist_addr = AW'(i);
      @(negedge clk);
      `CHECK_EQ(bist_rdata, pat, "MBIST raw write/read of full stored word")
    end
    bist_en = 0; bist_ce = 0;
    idle(2);

    `CHECK(rsp_seen > 6000, "responses observed")
    tb_finish();
  end

  initial begin
    #50ms;
    $display("TIMEOUT");
    tb_finish();
  end
endmodule

`default_nettype wire
