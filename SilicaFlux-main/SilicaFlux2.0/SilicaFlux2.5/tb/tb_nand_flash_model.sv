// =============================================================================
// tb_nand_flash_model.sv -- SilicaFlux NANDLab reference testbench
// -----------------------------------------------------------------------------
// A controller-style testbench (via nand_ctrl_bfm) that exercises the model at
// pin level. Run in phases, each a separate simulator process sharing the
// on-disk store, so persistence across process restarts is tested for real:
//
//   +PHASE=fresh        new device: ID, parameter page, program/read/erase,
//                       OOB, NOP, 0->1 rejection, sequential rule, boundaries,
//                       WP#, multi-LUN interleave, features, reset-abort, timing
//   +PHASE=restart      new process on the same store: data, erased blocks,
//                       erase counts, bad blocks and interrupted pages persist
//   +PHASE=powercut     VCC loss during program and erase -> partial cells
//   +PHASE=faults       directed + seeded faults (stress profile store)
//   +PHASE=faults_bake  restart after an unpowered bake: retention errors,
//                       read-retry recovery
//
// Exact error/timing/data agreement with the Python golden model is checked
// afterwards by `nand_flash_twin.py sv-regress` replaying the model trace.
// Results: <NANDLAB_DIR>/tb_<phase>.result
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

module tb_nand_flash_model;
  import nand_flash_pkg::*;

  localparam int PD   = `NANDLAB_PAGE_DATA_BYTES;
  localparam int PS   = `NANDLAB_PAGE_SPARE_BYTES;
  localparam int PB   = PD + PS;
  localparam int PPB  = `NANDLAB_PAGES_PER_BLOCK;
  localparam int BPL  = `NANDLAB_PLANES_PER_LUN * `NANDLAB_BLOCKS_PER_PLANE;
  localparam int LUNS = `NANDLAB_LUNS;
  localparam int RPB  = (PPB > 1) ? $clog2(PPB) : 0;
  localparam int RBB  = (BPL > 1) ? $clog2(BPL) : 0;

  wire  ce_n, cle, ale, we_n, re_n, wp_n, rb_n, dq_oe;   // wires: driven by the BFM, forceable
  wire  [7:0] dq_c2n, dq_n2c;
  logic vcc_ok;

  nand_flash_model #(
    .PAGE_DATA_BYTES(PD), .PAGE_SPARE_BYTES(PS), .PAGES_PER_BLOCK(PPB),
    .BLOCKS_PER_PLANE(`NANDLAB_BLOCKS_PER_PLANE), .PLANES_PER_LUN(`NANDLAB_PLANES_PER_LUN),
    .LUNS(LUNS), .TARGET_ID(0)
  ) u_nand (
    .ce_n(ce_n), .cle(cle), .ale(ale), .we_n(we_n), .re_n(re_n), .wp_n(wp_n),
    .dq_in(dq_c2n), .dq_out(dq_n2c), .dq_oe(dq_oe), .rb_n(rb_n), .vcc_ok(vcc_ok));

  nand_ctrl_bfm #(.PAGE_BYTES(PB), .RP_BITS(RPB), .RB_BITS(RBB)) bfm (
    .ce_n(ce_n), .cle(cle), .ale(ale), .we_n(we_n), .re_n(re_n), .wp_n(wp_n),
    .dq_out(dq_c2n), .dq_in(dq_n2c), .rb_n(rb_n));

  // ---------------------------------------------------------- bookkeeping
  string phase, dir;
  int    n_pass, n_fail, exp_proto, rfd;
  bit [7:0] st, b;
  bit [7:0] expv [0:16383];

  task automatic check(input bit cond, input string name);
    if (cond) begin n_pass++; $fdisplay(rfd, "CHECK PASS %s", name); end
    else begin n_fail++; $fdisplay(rfd, "CHECK FAIL %s", name); $display("[TB] FAIL: %s", name); end
  endtask

  task automatic check_busy(input real expect_ns, input string name);
    real d;
    d = bfm.last_busy_ns - expect_ns;
    if (d < 0) d = -d;
    check(d < 0.002, $sformatf("%s busy %.3f ns (expect %.3f)", name, bfm.last_busy_ns, expect_ns));
  endtask

  function automatic bit [7:0] pat(input int seed, input int i);
    bit [63:0] h;
    h = mix64(64'(seed) * 64'h100000001B3 + 64'(i));
    return h[7:0];
  endfunction

  task automatic fill(input int seed, input int n);
    for (int i = 0; i < n; i++) bfm.wbuf[i] = pat(seed, i);
  endtask

  function automatic bit rbuf_is_pat(input int seed, input int off, input int n);
    bit ok;
    ok = 1;
    for (int i = 0; i < n; i++) if (bfm.rbuf[i] !== pat(seed, off + i)) ok = 0;
    return ok;
  endfunction

  function automatic bit rbuf_all(input bit [7:0] v, input int n);
    bit ok;
    ok = 1;
    for (int i = 0; i < n; i++) if (bfm.rbuf[i] !== v) ok = 0;
    return ok;
  endfunction

  function automatic int popc(input bit [7:0] x);
    int c;
    c = 0;
    for (int k = 0; k < 8; k++) c += x[k];
    return c;
  endfunction

  function automatic bit st_ok(input bit [7:0] s);   return (s & 8'h61) == 8'h60; endfunction
  function automatic bit st_fail(input bit [7:0] s); return (s & 8'h61) == 8'h61; endfunction

  // ================================================================ phases
  task automatic phase_fresh();
    bit [15:0] crc;
    int fd, nbad, zeros_r, zeros_d, viol0, ok_sub;
    bit found5, found9, okp;
    real t_prog_done, t_erase_end;

    // -- power-on: commands before RESET are protocol errors
    bfm.cmd(8'h90); bfm.addr(8'h00); bfm.idle();
    exp_proto += 2;
    check(u_nand.n_proto_errors == exp_proto, "command before power-on RESET flagged");
    bfm.reset();
    check_busy(1000000.0, "power-on RESET");
    bfm.read_status(st);
    check(st == 8'hE0, $sformatf("status after reset = %02x (expect E0)", st));

    // -- identification
    bfm.read_id(8'h00, 5);
    check(bfm.rbuf[0] == 8'h00 && bfm.rbuf[1] == 8'h5A && bfm.rbuf[3] == 8'h15, "READ ID 00h bytes");
    bfm.read_id(8'h20, 4);
    check(bfm.rbuf[0] == "O" && bfm.rbuf[1] == "N" && bfm.rbuf[2] == "F" && bfm.rbuf[3] == "I", "READ ID 20h = 'ONFI'");
    bfm.read_param_page(768);
    check_busy(25000.0, "READ PARAMETER PAGE");
    crc = 16'h4F4E;
    for (int i = 0; i < 254; i++) crc = onfi_crc16_step(crc, bfm.rbuf[i]);
    check(bfm.rbuf[0] == "O" && bfm.rbuf[3] == "I", "parameter page signature");
    check({bfm.rbuf[255], bfm.rbuf[254]} == crc, "parameter page CRC-16 (copy 0)");
    check({bfm.rbuf[81], bfm.rbuf[80]} == 16'(PD) && {bfm.rbuf[85], bfm.rbuf[84]} == 16'(PS), "parameter page page/spare size");
    check(bfm.rbuf[92] == PPB && {bfm.rbuf[97], bfm.rbuf[96]} == 16'(BPL) && bfm.rbuf[100] == LUNS, "parameter page block/LUN geometry");
    check(bfm.rbuf[256 + 7] == bfm.rbuf[7] && bfm.rbuf[512 + 254] == bfm.rbuf[254], "redundant parameter page copies");
    fd = $fopen($sformatf("%s/param_page.hex", dir), "w");
    for (int i = 0; i < 768; i++) $fwrite(fd, "%02x\n", bfm.rbuf[i]);
    $fclose(fd);

    // -- fresh device reads erased
    bfm.read_page(0, 1, 0, 0, PB);
    check(rbuf_all(8'hFF, PB), "fresh page reads all 1s (lun0 blk1 pg0)");
    check_busy(25000.0, "page READ (tR)");
    bfm.read_page(LUNS - 1, BPL - 1, PPB - 1, 0, PB);
    check(rbuf_all(8'hFF, PB), "fresh last page of last block reads all 1s");

    // -- factory bad blocks: controller-style marker scan
    nbad = 0; found5 = 0; found9 = 0;
    for (int l = 0; l < LUNS; l++)
      for (int k = 0; k < BPL; k++) begin
        okp = 1;
        bfm.read_page(l, k, 0, PD, 1);   if (bfm.rbuf[0] != 8'hFF) okp = 0;
        bfm.read_page(l, k, PPB - 1, PD, 1); if (bfm.rbuf[0] != 8'hFF) okp = 0;
        if (!okp) begin
          nbad++;
          if (l == 0 && k == 5) found5 = 1;
          if (l == 1 && k == 9) found9 = 1;
        end
      end
    check(found5 && found9 && nbad == 2, $sformatf("factory bad-block scan finds exactly the configured blocks (%0d found)", nbad));
    check((u_nand.bd_block_flags(0, 5) & 1) == 1, "ground truth: lun0 blk5 factory bad");
    fill(1, PB);
    bfm.program_page(0, 5, 0, 0, PB, st);
    check(st_fail(st), "PROGRAM to factory-bad block fails");
    check_busy(600000.0, "failed PROGRAM runs to max time");
    bfm.erase_block(0, 5, st);
    exp_proto += 1;
    check(st_fail(st), "ERASE of factory-bad block fails");
    bfm.read_page(0, 5, 0, PD, 1);
    check(bfm.rbuf[0] == 8'h00, "factory bad-block marker survives erase attempt");

    // -- program / read round trip (data + spare)
    fill(1, PB);
    bfm.program_page(0, 2, 0, 0, PB, st);
    check(st_ok(st), $sformatf("PROGRAM status %02x", st));
    check_busy(200000.0, "PROGRAM (tPROG)");
    bfm.read_page(0, 2, 0, 0, PB);
    check(rbuf_is_pat(1, 0, PB), "read-after-program returns programmed data+spare");

    // -- partial-page programming: data then spare (NOP)
    fill(2, PD);
    bfm.program_page(0, 2, 1, 0, PD, st);
    check(st_ok(st), "partial program #1 (data area)");
    fill(3, PS);
    bfm.program_page(0, 2, 1, PD, PS, st);
    check(st_ok(st), "partial program #2 (spare area)");
    bfm.read_page(0, 2, 1, 0, PD);
    check(rbuf_is_pat(2, 0, PD), "data area intact after spare program");
    bfm.change_read_col(PD, PS);
    check(rbuf_is_pat(3, 0, PS), "CHANGE READ COLUMN (05h-E0h) returns spare");
    check(u_nand.bd_page_nop(0, 2, 1) == 2, "page program count = 2");

    // -- two loaded ranges via 85h; unloaded bytes stay erased
    for (int i = 0; i < 100; i++) bfm.wbuf[i] = pat(4, i);
    for (int i = 0; i < 50; i++) bfm.wbuf[100 + i] = pat(4, 400 + i);
    bfm.program_two_ranges(0, 2, 2, 0, 100, 400, 50, st);
    check(st_ok(st), "PROGRAM with CHANGE WRITE COLUMN (85h)");
    bfm.read_page(0, 2, 2, 0, PB);
    okp = 1;
    for (int i = 0; i < PB; i++) begin
      if (i < 100 || (i >= 400 && i < 450)) begin if (bfm.rbuf[i] != pat(4, i)) okp = 0; end
      else if (bfm.rbuf[i] != 8'hFF) okp = 0;
    end
    check(okp, "85h ranges programmed, unloaded bytes remain FFh");

    // -- invalid 0->1 transition is rejected; cells unchanged
    for (int i = 0; i < PB; i++) bfm.wbuf[i] = 8'hFF;
    bfm.program_page(0, 2, 0, 0, PB, st);
    check(st_fail(st), "PROGRAM requesting 0->1 is rejected (FAIL)");
    check_busy(2000.0, "rejected PROGRAM");
    bfm.read_page(0, 2, 0, 0, PB);
    check(rbuf_is_pat(1, 0, PB), "rejected PROGRAM leaves cells unchanged");

    // -- NOP limit (4): two more compatible programs succeed, the 5th is rejected
    fill(2, PD);
    bfm.program_page(0, 2, 1, 0, PD, st); check(st_ok(st), "compatible re-program #3");
    bfm.program_page(0, 2, 1, 0, PD, st); check(st_ok(st), "compatible re-program #4");
    bfm.program_page(0, 2, 1, 0, PD, st); check(st_fail(st), "5th program exceeds NOP=4 -> rejected");
    check(u_nand.bd_page_nop(0, 2, 1) == 4, "page program count capped at NOP");

    // -- sequential page programming rule
    fill(5, PB);
    bfm.program_page(0, 2, 5, 0, PB, st);
    check(st_fail(st), "out-of-order first program (pg5 before pg3) rejected");

    // -- block erase and isolation (other plane, other LUN)
    fill(5, PB); bfm.program_page(0, 3, 0, 0, PB, st); check(st_ok(st), "program lun0 blk3 (plane 1)");
    fill(6, PB); bfm.program_page(1, 2, 0, 0, PB, st); check(st_ok(st), "program lun1 blk2");
    bfm.erase_block(0, 2, st);
    check(st_ok(st), "ERASE status");
    check_busy(2000000.0, "ERASE (tBERS)");
    bfm.read_page(0, 2, 0, 0, PB); check(rbuf_all(8'hFF, PB), "erased page 0 reads all 1s");
    bfm.read_page(0, 2, 1, 0, PB); check(rbuf_all(8'hFF, PB), "erased page 1 reads all 1s");
    check(u_nand.bd_erase_count(0, 2) == 1, "erase count incremented");
    bfm.read_page(0, 3, 0, 0, PB); check(rbuf_is_pat(5, 0, PB), "neighbour block (other plane) untouched");
    bfm.read_page(1, 2, 0, 0, PB); check(rbuf_is_pat(6, 0, PB), "same block number on other LUN untouched");
    fill(7, PB); bfm.program_page(0, 2, 0, 0, PB, st);
    check(st_ok(st), "program after erase");
    check_busy(200000.0 * (1.0 - 0.2 * (1.0 / 100000.0)), "tPROG after 1 P/E cycle (wear-scaled)");

    // -- page / block boundaries
    for (int p = 0; p < PPB; p++) begin
      fill(100 + p, PB);
      bfm.program_page(0, 4, p, 0, PB, st);
    end
    check(st_ok(st), "sequential program of all pages in a block");
    bfm.read_page(0, 4, PPB - 1, PB - 1, 1);
    check(bfm.rbuf[0] == pat(100 + PPB - 1, PB - 1), "last byte of last page");
    bfm.read_page(0, 4, PPB - 1, PB - 1, 2);
    exp_proto += 1;
    check(bfm.rbuf[0] == pat(100 + PPB - 1, PB - 1) && bfm.rbuf[1] == 8'hFF, "read past end of page returns FFh");
    fill(8, PB + 1);
    bfm.program_page(1, 4, 0, 0, PB + 1, st);
    exp_proto += 1;
    check(st_ok(st), "program with one byte beyond page+spare (byte ignored)");
    bfm.read_page(1, 4, 0, 0, PB);
    check(rbuf_is_pat(8, 0, PB), "page holds exactly page+spare bytes");
    fill(9, PB); bfm.program_page(LUNS - 1, BPL - 1, 0, 0, PB, st);
    bfm.read_page(LUNS - 1, BPL - 1, 0, 0, PB);
    check(st_ok(st) && rbuf_is_pat(9, 0, PB), "last block of last LUN programmable");

    // -- write protect
    bfm.wp_n = 0;
    fill(10, PB); bfm.program_page(1, 5, 0, 0, PB, st);
    check(st_fail(st) && st[7] == 1'b0, $sformatf("PROGRAM with WP# low: FAIL, WP#=0 in status (%02x)", st));
    bfm.erase_block(1, 2, st);
    check(st_fail(st), "ERASE with WP# low fails");
    bfm.wp_n = 1;
    bfm.read_page(1, 5, 0, 0, PB); check(rbuf_all(8'hFF, PB), "write-protected program changed nothing");
    bfm.read_page(1, 2, 0, 0, PB); check(rbuf_is_pat(6, 0, PB), "write-protected erase changed nothing");

    // -- status while busy
    fill(11, PB);
    bfm.program_start(1, 6, 0, 0, PB);
    #1000;
    bfm.read_status(st);
    check(st[6] == 1'b0 && st[5] == 1'b0, $sformatf("status during tPROG shows busy (%02x)", st));
    bfm.wait_ready(); bfm.read_status(st);
    check(st_ok(st), "status ready after tPROG");

    // -- multi-LUN interleaving: program LUN1 while LUN0 erases
    bfm.erase_start(0, 6);
    #1000;
    fill(12, PB);
    bfm.program_start(1, 7, 0, 0, PB);
    st = 0;
    while (st[6] == 0) begin #10000; bfm.read_status_enh(1, st); end
    t_prog_done = $realtime;
    bfm.read_status_enh(0, st);
    check(st[6] == 1'b0, "LUN0 still erasing while LUN1 program completed");
    check(rb_n == 1'b0, "R/B# low while any LUN busy");
    @(posedge rb_n);
    t_erase_end = $realtime;
    #100;
    bfm.read_status_enh(0, st);
    check(st_ok(st) && t_prog_done < t_erase_end, "interleaved operations overlap and both succeed");
    bfm.read_page(1, 7, 0, 0, PB); check(rbuf_is_pat(12, 0, PB), "interleaved program data correct");

    // -- features: timing mode and (model-specific) read retry
    bfm.get_feature(8'h01, b); check(b == 8'h00, "GET FEATURES timing mode = 0 after power-on");
    bfm.set_feature(8'h01, 8'h01); bfm.set_mode(1);
    check_busy(1000.0, "SET FEATURES (tFEAT)");
    bfm.get_feature(8'h01, b); check(b == 8'h01, "timing mode 1 selected");
    bfm.read_page(0, 3, 0, 0, PB); check(rbuf_is_pat(5, 0, PB), "read in timing mode 1");
    bfm.set_feature(8'h01, 8'h00); bfm.set_mode(0);
    bfm.set_feature(8'hA0, 8'h02); bfm.get_feature(8'hA0, b); check(b == 8'h02, "read-retry level +2");
    bfm.set_feature(8'hA0, 8'hFE); bfm.get_feature(8'hA0, b); check(b == 8'hFE, "read-retry level -2");
    bfm.set_feature(8'hA0, 8'h00);

    // -- RESET during program aborts it: cells are left partially programmed
    fill(13, PB);
    bfm.program_start(0, 7, 0, 0, PB);
    #100000;
    bfm.reset();
    check_busy(10000.0, "RESET aborting PROGRAM (tRST)");
    check((u_nand.bd_page_flags(0, 7, 0) & 8'h04) != 0, "aborted page flagged PROG_INTERRUPTED");
    bfm.read_page(0, 7, 0, 0, PB);
    zeros_r = 0; zeros_d = 0; ok_sub = 1;
    for (int i = 0; i < PB; i++) begin
      zeros_r += 8 - popc(bfm.rbuf[i]); zeros_d += 8 - popc(pat(13, i));
      if ((~bfm.rbuf[i] & pat(13, i)) != 0) ok_sub = 0;
    end
    check(ok_sub && zeros_r > 0 && zeros_r < zeros_d,
          $sformatf("aborted program: %0d of %0d intended 0s written, no stray 0s", zeros_r, zeros_d));

    // -- state for the restart phase
    for (int p = 0; p < 4; p++) begin fill(200 + p, PB); bfm.program_page(0, 10, p, 0, PB, st); end
    fill(14, PB); bfm.program_page(0, 11, 0, 0, PB, st);
    bfm.erase_block(0, 11, st);
    check(st_ok(st), "erase block 11 before restart");

    // -- AC timing checker: compliant so far, then one deliberate violation
    viol0 = u_nand.n_timing_violations;
    check(viol0 == 0, "no AC timing violations from the compliant BFM");
    ce_n_force();
    check(u_nand.n_timing_violations > viol0, "short WE# pulse detected by timing checker");
  endtask

  task automatic ce_n_force();
    // drive a 10 ns WE# pulse with CLE (violates tWP/tCLS/tDS in mode 0)
    force ce_n = 1'b0; force cle = 1'b1; force dq_c2n = 8'h70; force we_n = 1'b0;
    #10; force we_n = 1'b1; #100;
    release we_n; release cle; release dq_c2n; release ce_n;
    bfm.idle();
  endtask

  task automatic phase_restart();
    bfm.reset();
    check_busy(1000000.0, "power-on RESET after process restart");
    for (int p = 0; p < 4; p++) begin
      bfm.read_page(0, 10, p, 0, PB);
      check(rbuf_is_pat(200 + p, 0, PB), $sformatf("data persists across restart (lun0 blk10 pg%0d)", p));
    end
    bfm.read_page(0, 11, 0, 0, PB);
    check(rbuf_all(8'hFF, PB), "erased block stays erased after restart (no magic restore)");
    check(u_nand.bd_erase_count(0, 11) == 1 && u_nand.bd_erase_count(0, 2) == 1, "erase counts persist");
    bfm.read_page(0, 5, 0, PD, 1);
    check(bfm.rbuf[0] == 8'h00, "factory bad-block marker persists");
    check((u_nand.bd_block_flags(1, 9) & 1) == 1, "factory bad-block state persists");
    check((u_nand.bd_page_flags(0, 7, 0) & 8'h04) != 0, "interrupted-page flag persists");
    check(u_nand.bd_block_reads(0, 10) >= 4, "read-disturb counters persist");
    fill(204, PB); bfm.program_page(0, 10, 4, 0, PB, st);
    bfm.read_page(0, 10, 4, 0, PB);
    check(st_ok(st) && rbuf_is_pat(204, 0, PB), "device usable after restart");
    bfm.read_page(0, 2, 0, 0, PB);
    check(rbuf_is_pat(7, 0, PB), "page written after an erase persists");
  endtask

  task automatic phase_powercut();
    int z_r, z_d, ok_sub, ones_r, ones_d;
    bfm.reset();
    // -- loss of VCC during PROGRAM
    fill(10, PB);
    bfm.program_start(1, 20, 0, 0, PB);
    #250; #80000;                        // 40 % into tPROG
    vcc_ok = 0;
    #1;
    check(rb_n == 1'b0, "R/B# low while unpowered");
    #10000;
    vcc_ok = 1;
    #1000;
    bfm.cmd(8'h90); bfm.addr(8'h00); bfm.idle();
    exp_proto += 2;
    check(u_nand.n_proto_errors == exp_proto, "RESET required after power-up");
    bfm.reset();
    check_busy(1000000.0, "power-on RESET after VCC loss");
    check((u_nand.bd_page_flags(1, 20, 0) & 8'h04) != 0, "page flagged PROG_INTERRUPTED");
    bfm.read_page(1, 20, 0, 0, PB);
    z_r = 0; z_d = 0; ok_sub = 1;
    for (int i = 0; i < PB; i++) begin
      z_r += 8 - popc(bfm.rbuf[i]); z_d += 8 - popc(pat(10, i));
      if ((~bfm.rbuf[i] & pat(10, i)) != 0) ok_sub = 0;
    end
    check(ok_sub && z_r > 0 && z_r < z_d, $sformatf("power-cut program: %0d of %0d intended 0s written", z_r, z_d));
    bfm.program_page(1, 20, 0, 0, PB, st);
    bfm.read_page(1, 20, 0, 0, PB);
    check(st_ok(st) && rbuf_is_pat(10, 0, PB), "re-program completes the interrupted page");

    // -- loss of VCC during ERASE
    for (int p = 0; p < 3; p++) begin fill(20 + p, PB); bfm.program_page(1, 21, p, 0, PB, st); end
    bfm.erase_start(1, 21);
    #250; #1000000;                      // 50 % into tBERS
    vcc_ok = 0; #10000; vcc_ok = 1; #1000;
    bfm.reset();
    check((u_nand.bd_block_flags(1, 21) & 8'h30) == 8'h30, "block flagged MARGINAL + ERASE_INTERRUPTED");
    check(u_nand.bd_erase_count(1, 21) == 1, "interrupted erase counts as a P/E cycle");
    bfm.read_page(1, 21, 0, 0, PB);
    ones_r = 0; ones_d = 0; ok_sub = 1;
    for (int i = 0; i < PB; i++) begin
      ones_r += popc(bfm.rbuf[i]); ones_d += popc(pat(20, i));
      if ((pat(20, i) & ~bfm.rbuf[i]) != 0) ok_sub = 0;
    end
    check(ok_sub && ones_r > ones_d && ones_r < PB * 8,
          $sformatf("power-cut erase: partially erased (%0d of %0d bits are 1)", ones_r, PB * 8));
    bfm.erase_block(1, 21, st);
    check(st_ok(st), "re-erase after interrupted erase");
    bfm.read_page(1, 21, 0, 0, PB);
    check(rbuf_all(8'hFF, PB) && (u_nand.bd_block_flags(1, 21) & 8'h30) == 0, "re-erase clears the block and marginal flags");

    // -- power cycle while idle changes nothing
    vcc_ok = 0; #5000; vcc_ok = 1; #1000;
    bfm.reset();
    bfm.read_page(1, 20, 0, 0, PB);
    check(rbuf_is_pat(10, 0, PB), "idle power cycle preserves data");
  endtask

  // blocks used by the fault phases (chosen to avoid any factory-bad block)
  int good_blk [0:3];

  task automatic pick_good_blocks();
    int n, k;
    bit okp;
    n = 0; k = 16;
    while (n < 4 && k < BPL) begin
      okp = 1;
      bfm.read_page(1, k, 0, PD, 1);       if (bfm.rbuf[0] != 8'hFF) okp = 0;
      bfm.read_page(1, k, PPB - 1, PD, 1); if (bfm.rbuf[0] != 8'hFF) okp = 0;
      if (okp) begin good_blk[n] = k; n++; end
      k++;
    end
  endtask

  task automatic count_errors(input int lun, input int blk, input int pg, output int e01, output int e10);
    bit [7:0] raw;
    e01 = 0; e10 = 0;
    for (int i = 0; i < PB; i++) begin
      raw = u_nand.bd_peek(lun, blk, pg, i);
      e01 += popc(~raw & bfm.rbuf[i]);     // stored 0, read 1 (charge loss)
      e10 += popc(raw & ~bfm.rbuf[i]);     // stored 1, read 0 (charge gain)
    end
  endtask

  task automatic phase_faults();
    int e01, e10, t01, t10, nb;
    bfm.reset();
    // directed faults (configured in nandlab.svcfg)
    fill(30, PB);
    bfm.program_page(0, 24, 0, 0, PB, st);
    check(st_fail(st), "directed program failure reported in status");
    check((u_nand.bd_page_flags(0, 24, 0) & 8'h02) != 0 && (u_nand.bd_block_flags(0, 24) & 8'h04) != 0,
          "failed program flags page and block");
    bfm.erase_block(0, 25, st);
    check(st_fail(st), "directed erase failure reported in status");
    bfm.erase_block(0, 25, st);
    check(st_fail(st) && (u_nand.bd_block_flags(0, 25) & 8'h02) != 0, "erase failure is sticky (worn block)");
    for (int i = 0; i < PB; i++) bfm.wbuf[i] = 8'hFF;
    bfm.wbuf[1] = 8'h00;
    bfm.program_page(0, 26, 0, 0, PB, st);
    bfm.read_page(0, 26, 0, 0, 2);
    check(bfm.rbuf[0][3] == 1'b0, "stuck-at-0 cell (byte 0 bit 3) reads 0");
    // seeded statistical faults: program 4 good blocks, read every page twice
    pick_good_blocks();
    t01 = 0; t10 = 0; nb = 0;
    for (int k = 0; k < 4; k++)
      for (int p = 0; p < PPB; p++) begin
        fill(1000 + k * 100 + p, PB);
        bfm.program_page(1, good_blk[k], p, 0, PB, st);
        if (st_fail(st)) nb++;
      end
    for (int r = 0; r < 2; r++)
      for (int k = 0; k < 4; k++)
        for (int p = 0; p < PPB; p++) begin
          bfm.read_page(1, good_blk[k], p, 0, PB);
          count_errors(1, good_blk[k], p, e01, e10);
          t01 += e01; t10 += e10;
        end
    $fdisplay(rfd, "INFO fresh-stress raw bit errors: 0->1 %0d, 1->0 %0d over 128 page reads; %0d program fails", t01, t10, nb);
    check(1, "statistical fault reads completed (exact values verified by Python co-simulation)");
  endtask

  task automatic phase_faults_bake();
    int e01, e10, t01, t10, r01, r10, page_errs0, page_errs3;
    bfm.reset();
    pick_good_blocks();
    t01 = 0; t10 = 0;
    for (int k = 0; k < 4; k++)
      for (int p = 0; p < PPB; p++) begin
        bfm.read_page(1, good_blk[k], p, 0, PB);
        count_errors(1, good_blk[k], p, e01, e10);
        t01 += e01; t10 += e10;
      end
    $fdisplay(rfd, "INFO after bake: 0->1 %0d, 1->0 %0d", t01, t10);
    check(t01 > 1000 && t01 > 10 * t10, $sformatf("retention bake causes mostly 0->1 errors (%0d vs %0d)", t01, t10));
    bfm.read_page(1, good_blk[0], 3, 0, PB);
    count_errors(1, good_blk[0], 3, e01, e10); page_errs0 = e01 + e10;
    bfm.set_feature(8'hA0, 8'h03);
    bfm.read_page(1, good_blk[0], 3, 0, PB);
    count_errors(1, good_blk[0], 3, r01, r10); page_errs3 = r01 + r10;
    bfm.set_feature(8'hA0, 8'h00);
    $fdisplay(rfd, "INFO read retry: level0 %0d errors, level+3 %0d errors", page_errs0, page_errs3);
    check(page_errs3 * 4 < page_errs0, "read retry (+3) recovers most retention errors");
  endtask

  // ================================================================== main
  initial begin
    vcc_ok = 1;
    n_pass = 0; n_fail = 0; exp_proto = 0;
    if (!$value$plusargs("PHASE=%s", phase)) phase = "fresh";
    if (!$value$plusargs("NANDLAB_DIR=%s", dir)) dir = ".";
    rfd = $fopen($sformatf("%s/tb_%s.result", dir, phase), "w");
    #1000;                                   // host waits after power-on before the first command
    if (phase == "fresh") phase_fresh();
    else if (phase == "restart") phase_restart();
    else if (phase == "powercut") phase_powercut();
    else if (phase == "faults") phase_faults();
    else if (phase == "faults_bake") phase_faults_bake();
    else $display("[TB] unknown phase %s", phase);
    check(u_nand.n_proto_errors == exp_proto,
          $sformatf("protocol errors = %0d (expected %0d deliberate)", u_nand.n_proto_errors, exp_proto));
    $fdisplay(rfd, "SUMMARY phase %s pass %0d fail %0d proto %0d timing %0d simtime_ns %0.0f",
              phase, n_pass, n_fail, u_nand.n_proto_errors, u_nand.n_timing_violations, $realtime);
    $fclose(rfd);
    $display("[TB] phase %s: %0d passed, %0d failed", phase, n_pass, n_fail);
    #100;
    $finish;
  end

  initial begin
    #2000000000;  // 2 s watchdog
    $display("[TB] WATCHDOG timeout");
    $finish;
  end
endmodule
