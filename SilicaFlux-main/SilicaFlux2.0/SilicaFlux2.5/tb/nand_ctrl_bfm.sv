// =============================================================================
// nand_ctrl_bfm.sv -- SilicaFlux NANDLab controller bus-functional model
// -----------------------------------------------------------------------------
// Stands in for the SilicaFlux storage controller's NAND PHY: drives the
// ONFI asynchronous pins with timing that meets the selected timing mode (with
// margin) and offers operation-level tasks. Replace with the real controller
// RTL to verify it against nand_flash_model.
// =============================================================================
`timescale 1ns/1ps

module nand_ctrl_bfm #(
  parameter int PAGE_BYTES = 528,
  parameter int RP_BITS    = 4,      // page bits in the row address
  parameter int RB_BITS    = 6       // block bits in the row address
) (
  output logic       ce_n,
  output logic       cle,
  output logic       ale,
  output logic       we_n,
  output logic       re_n,
  output logic       wp_n,
  output logic [7:0] dq_out,
  input  logic [7:0] dq_in,
  input  logic       rb_n
);
  // ---------------------------------------------------------------- timing
  real tWP, tWH, tRP, tREH, tWHR, tADL, tRR, tCCS, tWB_MAX;
  int  mode;
  bit [7:0] wbuf [0:16383];
  bit [7:0] rbuf [0:16383];
  real t_rb_fall, t_rb_rise, last_busy_ns;

  task automatic set_mode(input int m);
    mode = m;
    // per-mode controller timing with >= 20% margin over the ONFI-nominal minimums
    case (m)
      0: begin tWP = 60; tWH = 40; tRP = 60; tREH = 40; tWHR = 150; tADL = 250; tRR = 50; end
      1: begin tWP = 30; tWH = 20; tRP = 35; tREH = 20; tWHR = 100; tADL = 130; tRR = 30; end
      2: begin tWP = 21; tWH = 18; tRP = 30; tREH = 18; tWHR = 100; tADL = 130; tRR = 30; end
      3: begin tWP = 18; tWH = 13; tRP = 25; tREH = 13; tWHR = 100; tADL = 130; tRR = 30; end
      4: begin tWP = 15; tWH = 13; tRP = 25; tREH = 13; tWHR = 100; tADL = 100; tRR = 30; end
      default: begin tWP = 13; tWH = 10; tRP = 20; tREH = 10; tWHR = 100; tADL = 100; tRR = 30; end
    endcase
    tCCS = 600; tWB_MAX = 250;
  endtask

  initial begin
    ce_n = 1; cle = 0; ale = 0; we_n = 1; re_n = 1; wp_n = 1; dq_out = 8'h00;
    t_rb_fall = -1.0; t_rb_rise = -1.0; last_busy_ns = 0;
    set_mode(0);
  end

  // only this process writes t_rb_fall (a flag also written by wait_ready was
  // lost by Verilator's scheduling of multi-driven variables)
  always @(negedge rb_n) t_rb_fall = $realtime;
  always @(posedge rb_n) t_rb_rise = $realtime;

  // ------------------------------------------------------------ bus cycles
  task automatic cmd(input bit [7:0] c);
    ce_n = 0; cle = 1; ale = 0; dq_out = c; we_n = 0;
    #(tWP); we_n = 1; #(tWH); cle = 0;
  endtask

  task automatic addr(input bit [7:0] a);
    ce_n = 0; ale = 1; cle = 0; dq_out = a; we_n = 0;
    #(tWP); we_n = 1; #(tWH); ale = 0;
  endtask

  task automatic wr(input bit [7:0] d);
    ce_n = 0; cle = 0; ale = 0; dq_out = d; we_n = 0;
    #(tWP); we_n = 1; #(tWH);
  endtask

  task automatic rd(output bit [7:0] d);
    ce_n = 0; re_n = 0;
    #(tRP); d = dq_in; re_n = 1; #(tREH);
  endtask

  // (Icarus 12 crashes when an indexed array element is an automatic task's
  //  output argument, so reads go through a scalar temporary)
  task automatic rd_buf(input int i);
    bit [7:0] t;
    rd(t);
    rbuf[i] = t;
  endtask

  task automatic col_addr(input int c);
    addr(c[7:0]); addr(c[15:8]);
  endtask

  task automatic row_addr(input int lun, input int blk, input int pg);
    bit [23:0] row;
    row = 24'(pg) | (24'(blk) << RP_BITS) | (24'(lun) << (RP_BITS + RB_BITS));
    addr(row[7:0]); addr(row[15:8]); addr(row[23:16]);
  endtask

  // wait for an operation started by the last confirm command; measures the
  // R/B# low time (0 if R/B# did not fall after the wait started)
  task automatic wait_ready();
    real t0, t_rise;
    t0 = $realtime;
    #(tWB_MAX);
    if (!rb_n) @(posedge rb_n);
    t_rise = $realtime;            // sampled here: no race with the edge-recording process
    if (t_rb_fall >= t0) last_busy_ns = t_rise - t_rb_fall;
    else last_busy_ns = 0.0;
    #(tRR);
  endtask

  // ------------------------------------------------------- operation level
  task automatic reset();
    cmd(8'hFF); wait_ready();
  endtask

  task automatic read_status(output bit [7:0] st);
    cmd(8'h70); #(tWHR); rd(st);
  endtask

  task automatic read_status_enh(input int lun, output bit [7:0] st);
    cmd(8'h78); row_addr(lun, 0, 0); #(tWHR); rd(st);
  endtask

  task automatic read_id(input bit [7:0] a, input int n);
    cmd(8'h90); addr(a); #(tWHR);
    for (int i = 0; i < n; i++) rd_buf(i);
  endtask

  task automatic read_param_page(input int n);
    cmd(8'hEC); addr(8'h00); wait_ready();
    for (int i = 0; i < n; i++) rd_buf(i);
  endtask

  task automatic read_page(input int lun, input int blk, input int pg, input int c, input int n);
    cmd(8'h00); col_addr(c); row_addr(lun, blk, pg); cmd(8'h30); wait_ready();
    for (int i = 0; i < n; i++) rd_buf(i);
  endtask

  // read n bytes at a new column of the current page register (05h-E0h)
  task automatic change_read_col(input int c, input int n);
    cmd(8'h05); col_addr(c); cmd(8'hE0); #(tCCS);
    for (int i = 0; i < n; i++) rd_buf(i);
  endtask

  // issue a program but do not wait (for status-during-busy / abort tests)
  task automatic program_start(input int lun, input int blk, input int pg, input int c, input int n);
    cmd(8'h80); col_addr(c); row_addr(lun, blk, pg); #(tADL);
    for (int i = 0; i < n; i++) wr(wbuf[i]);
    cmd(8'h10);
  endtask

  task automatic program_page(input int lun, input int blk, input int pg, input int c, input int n,
                              output bit [7:0] st);
    program_start(lun, blk, pg, c, n); wait_ready(); read_status(st);
  endtask

  // program with two separate data ranges using CHANGE WRITE COLUMN (85h)
  task automatic program_two_ranges(input int lun, input int blk, input int pg, input int c0, input int n0,
                                    input int c1, input int n1, output bit [7:0] st);
    cmd(8'h80); col_addr(c0); row_addr(lun, blk, pg); #(tADL);
    for (int i = 0; i < n0; i++) wr(wbuf[i]);
    cmd(8'h85); col_addr(c1); #(tADL);
    for (int i = 0; i < n1; i++) wr(wbuf[n0 + i]);
    cmd(8'h10); wait_ready(); read_status(st);
  endtask

  task automatic erase_start(input int lun, input int blk);
    cmd(8'h60); row_addr(lun, blk, 0); cmd(8'hD0);
  endtask

  task automatic erase_block(input int lun, input int blk, output bit [7:0] st);
    erase_start(lun, blk); wait_ready(); read_status(st);
  endtask

  task automatic set_feature(input bit [7:0] fa, input bit [7:0] p1);
    cmd(8'hEF); addr(fa); #(tADL);
    wr(p1); wr(8'h00); wr(8'h00); wr(8'h00);
    wait_ready();
  endtask

  task automatic get_feature(input bit [7:0] fa, output bit [7:0] p1);
    bit [7:0] dummy;
    cmd(8'hEE); addr(fa); wait_ready();
    rd(p1); rd(dummy); rd(dummy); rd(dummy);
  endtask

  task automatic idle();
    ce_n = 1; cle = 0; ale = 0;
  endtask
endmodule
