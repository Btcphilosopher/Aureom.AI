// =============================================================================
// tb_nand_channel.sv -- two NAND targets sharing one channel (DQ bus, CLE, ALE,
// WE#, RE#, WP#, wired-AND R/B#) with separate CE#s, through the bidirectional
// nand_flash_device wrapper. Checks target isolation and bus turn-around.
// =============================================================================
`timescale 1ns/1ps
`ifdef NANDLAB_GEOM_FILE
  `include "nandlab_geom.svh"
`endif
`ifndef NANDLAB_PAGE_DATA_BYTES
  `define NANDLAB_PAGE_DATA_BYTES 512
  `define NANDLAB_PAGE_SPARE_BYTES 16
  `define NANDLAB_PAGES_PER_BLOCK 16
  `define NANDLAB_BLOCKS_PER_PLANE 32
  `define NANDLAB_PLANES_PER_LUN 2
  `define NANDLAB_LUNS 2
`endif

module tb_nand_channel;
  import nand_flash_pkg::*;
  localparam int PD = `NANDLAB_PAGE_DATA_BYTES, PS = `NANDLAB_PAGE_SPARE_BYTES, PB = PD + PS;
  localparam int PPB = `NANDLAB_PAGES_PER_BLOCK, BPL = `NANDLAB_PLANES_PER_LUN * `NANDLAB_BLOCKS_PER_PLANE;
  localparam int RPB = (PPB > 1) ? $clog2(PPB) : 0, RBB = (BPL > 1) ? $clog2(BPL) : 0;

  wire ce_n_bfm, cle, ale, we_n, re_n, wp_n, rb0, rb1, re_hold_n;
  wire [7:0] dq_c2n;
  tri  [7:0] dq;
  logic sel, vcc_ok;
  wire ce0 = ce_n_bfm | sel;
  wire ce1 = ce_n_bfm | ~sel;
  wire rb_bus = rb0 & rb1;                   // open-drain R/B# with pull-up
  assign #20 re_hold_n = re_n;
  assign dq = (re_n && re_hold_n) ? dq_c2n : 8'hzz;   // controller drives outside read cycles

  nand_flash_device #(.PAGE_DATA_BYTES(PD), .PAGE_SPARE_BYTES(PS), .PAGES_PER_BLOCK(PPB),
    .BLOCKS_PER_PLANE(`NANDLAB_BLOCKS_PER_PLANE), .PLANES_PER_LUN(`NANDLAB_PLANES_PER_LUN), .LUNS(`NANDLAB_LUNS),
    .TARGET_ID(0)) u_t0 (.ce_n(ce0), .cle(cle), .ale(ale), .we_n(we_n), .re_n(re_n), .wp_n(wp_n), .vcc_ok(vcc_ok),
    .dq(dq), .rb_n(rb0));
  nand_flash_device #(.PAGE_DATA_BYTES(PD), .PAGE_SPARE_BYTES(PS), .PAGES_PER_BLOCK(PPB),
    .BLOCKS_PER_PLANE(`NANDLAB_BLOCKS_PER_PLANE), .PLANES_PER_LUN(`NANDLAB_PLANES_PER_LUN), .LUNS(`NANDLAB_LUNS),
    .TARGET_ID(1)) u_t1 (.ce_n(ce1), .cle(cle), .ale(ale), .we_n(we_n), .re_n(re_n), .wp_n(wp_n), .vcc_ok(vcc_ok),
    .dq(dq), .rb_n(rb1));
  nand_ctrl_bfm #(.PAGE_BYTES(PB), .RP_BITS(RPB), .RB_BITS(RBB)) bfm (
    .ce_n(ce_n_bfm), .cle(cle), .ale(ale), .we_n(we_n), .re_n(re_n), .wp_n(wp_n),
    .dq_out(dq_c2n), .dq_in(dq), .rb_n(rb_bus));

  string dir;
  int n_pass, n_fail, rfd;
  bit [7:0] st;

  task automatic check(input bit cond, input string name);
    if (cond) begin n_pass++; $fdisplay(rfd, "CHECK PASS %s", name); end
    else begin n_fail++; $fdisplay(rfd, "CHECK FAIL %s", name); $display("[TB] FAIL: %s", name); end
  endtask

  function automatic bit [7:0] pat(input int seed, input int i);
    bit [63:0] h;
    h = mix64(64'(seed) * 64'h100000001B3 + 64'(i));
    return h[7:0];
  endfunction

  initial begin
    bit ok;
    vcc_ok = 1; sel = 0; n_pass = 0; n_fail = 0;
    if (!$value$plusargs("NANDLAB_DIR=%s", dir)) dir = ".";
    rfd = $fopen($sformatf("%s/tb_channel.result", dir), "w");
    #1000;
    sel = 0; bfm.reset();
    check(bfm.last_busy_ns > 999999.998 && bfm.last_busy_ns < 1000000.002, $sformatf("target 0 power-on RESET (%.3f ns)", bfm.last_busy_ns));
    sel = 1; bfm.reset();
    check(bfm.last_busy_ns > 999999.998 && bfm.last_busy_ns < 1000000.002, $sformatf("target 1 power-on RESET (%.3f ns)", bfm.last_busy_ns));
    sel = 0; bfm.read_status(st); check(st == 8'hE0, "target 0 status via shared bus");
    sel = 1; bfm.read_id(8'h20, 4); check(bfm.rbuf[0] == "O" && bfm.rbuf[3] == "I", "target 1 READ ID over shared DQ");
    for (int i = 0; i < PB; i++) bfm.wbuf[i] = pat(77, i);
    sel = 1; bfm.program_page(0, 3, 0, 0, PB, st); check((st & 8'h61) == 8'h60, "program on target 1");
    sel = 0; bfm.read_page(0, 3, 0, 0, PB);
    ok = 1; for (int i = 0; i < PB; i++) if (bfm.rbuf[i] !== 8'hFF) ok = 0;
    check(ok, "same address on target 0 still erased (CE# isolation)");
    sel = 1; bfm.read_page(0, 3, 0, 0, PB);
    ok = 1; for (int i = 0; i < PB; i++) if (bfm.rbuf[i] !== pat(77, i)) ok = 0;
    check(ok, "target 1 read-back over shared bus (no contention, no X)");
    // overlap: erase on target 0 while target 1 reads. R/B# is shared (wired-AND),
    // so per-target readiness must come from READ STATUS polling.
    sel = 0; bfm.erase_start(1, 4);
    #1000;
    check(rb_bus == 1'b0, "shared R/B# low while target 0 erases");
    sel = 1;
    bfm.cmd(8'h00); bfm.col_addr(0); bfm.row_addr(0, 3, 0); bfm.cmd(8'h30);
    #300; st = 0;
    while (st[6] == 1'b0) begin #2000; bfm.read_status(st); end
    check(rb_bus == 1'b0, "target 1 ready while shared R/B# still low (target 0 erasing)");
    bfm.cmd(8'h00); #(bfm.tWHR);                      // 00h: back to data output after 70h
    for (int i = 0; i < 16; i++) bfm.rd_buf(i);
    ok = 1; for (int i = 0; i < 16; i++) if (bfm.rbuf[i] !== pat(77, i)) ok = 0;
    check(ok, "target 1 serves a read while target 0 is busy");
    if (!rb_bus) @(posedge rb_bus);
    sel = 0; #100; bfm.read_status(st); check((st & 8'h61) == 8'h60, "target 0 erase completes");
    check(u_t0.u_model.n_proto_errors == 0 && u_t1.u_model.n_proto_errors == 0, "no protocol errors on either target");
    check(u_t0.u_model.n_timing_violations == 0 && u_t1.u_model.n_timing_violations == 0, "no AC timing violations");
    $fdisplay(rfd, "SUMMARY phase channel pass %0d fail %0d", n_pass, n_fail);
    $fclose(rfd);
    $display("[TB] channel: %0d passed, %0d failed", n_pass, n_fail);
    #100 $finish;
  end

  initial begin #50000000; $display("[TB] WATCHDOG"); $finish; end
endmodule
