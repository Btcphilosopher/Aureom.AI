// =============================================================================
// SilicaFlux-V :: sfv_sysctrl -- system control / test & debug registers
//
//   0x00 CHIP_ID      RO  sfv_pkg::CHIP_ID
//   0x04 BOOT_MODE    RO  [1:0] straps sampled 3 cycles after reset release
//   0x08 SCRATCH0     RW  (JTAG boot mailbox: entry point)
//   0x0C SCRATCH1     RW  (JTAG boot mailbox: 0xB007_C0DE = go)
//   0x10 TEST_STATUS  RW  [1:0] 0 running / 1 pass / 2 fail  [15:8] code
//                         drives test_pass/test_fail outputs (status pins)
//   0x14 SOFT_RESET   WO  write 0x5AFE_0001 -> system reset (CPU, bus, periph)
//   0x18 RESET_CAUSE  RO  [0] external pin  [1] soft  [2] JTAG CPU hold
//   0x1C CLK_CTRL     RW  [0] TILE_CG_OFF: keep accelerator tile clock on
//   0x20 BUSERR_ADDR  RO  address of the first unacknowledged decode error
//   0x24 BUSERR_INFO  RW  [0] VALID (W1C) [2:1] master [3] write
//   0x28 MBIST_CTRL   RW  [0] START (self-clearing) [1] BG_CHK [4] GROUP
//                         (0 main SRAM banks, 1 tile scratchpad) [8] IRQ_EN
//   0x2C MBIST_STATUS RO  [0] BUSY [1] DONE [2] FAIL [11:8] fail bank mask
//                         (BUSY is also set, DONE masked, in the cycle after a
//                          START write: polling right after START is race-free)
//                         [14:12] fail element [31:16] fail address
//   0x30 DOORBELL     RW  [0] software/JTAG doorbell interrupt (IRQ_DBG)
// Reset domain: all registers use the system reset except RESET_CAUSE's soft
// bit and the soft-reset pulse generator, which use the pin-level reset.
// =============================================================================
`default_nettype none

module sfv_sysctrl (
  input  wire logic        clk,
  input  wire logic        rst_n,        // system reset
  input  wire logic        por_rst_n,    // pin reset (survives soft reset)
  input  wire logic        rb_sel,
  input  wire logic        rb_we,
  input  wire logic [11:0] rb_addr,
  input  wire logic [31:0] rb_wdata,
  output logic [31:0]      rb_rdata,
  output logic             rb_err,
  input  wire logic [1:0]  boot_straps,
  input  wire logic        jtag_cpu_hold,
  // bus error capture
  input  wire logic        berr_evt,
  input  wire logic [31:0] berr_addr,
  input  wire logic [1:0]  berr_master,
  input  wire logic        berr_we,
  // MBIST
  output logic             mbist_start,
  output logic             mbist_bg,
  output logic             mbist_group,
  input  wire logic        mbist_busy,
  input  wire logic        mbist_done,
  input  wire logic        mbist_fail,
  input  wire logic [3:0]  mbist_fail_bank,
  input  wire logic [2:0]  mbist_fail_elem,
  input  wire logic [15:0] mbist_fail_addr,
  // outputs
  output logic             soft_reset,   // to reset controller (pulse >= 4 clk)
  output logic             tile_cg_off,
  output logic             test_pass,
  output logic             test_fail,
  output logic [31:0]      test_status,
  output logic             irq_berr,
  output logic             irq_mbist,
  output logic             irq_dbg
);
  wire wr = rb_sel && rb_we;
  logic [1:0]  boot_q;
  logic [31:0] scr0_q, scr1_q, tst_q, beaddr_q;
  logic        bev_q, bewe_q, cgoff_q, mbg_q, mgrp_q, mien_q, db_q, mstart_q;
  logic [1:0]  bem_q, strap_cnt;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      boot_q <= 2'b00;
      strap_cnt <= 2'd0;
      scr0_q <= '0; scr1_q <= '0; tst_q <= '0; beaddr_q <= '0;
      bev_q  <= 1'b0; bewe_q <= 1'b0; bem_q <= '0; cgoff_q <= 1'b0;
      mbg_q  <= 1'b0; mgrp_q <= 1'b0; mien_q <= 1'b0; db_q <= 1'b0; mstart_q <= 1'b0;
    end else begin
      mstart_q <= wr && rb_addr == 12'h028 && rb_wdata[0];
      // straps (already synchronised at the SoC top) are sampled once, three
      // cycles after reset release, then held: no asynchronous data load.
      if (strap_cnt != 2'd3) begin
        strap_cnt <= strap_cnt + 2'd1;
        boot_q    <= boot_straps;
      end
      if (berr_evt && !bev_q) begin
        bev_q <= 1'b1; beaddr_q <= berr_addr; bem_q <= berr_master; bewe_q <= berr_we;
      end
      if (wr) begin
        case (rb_addr)
          12'h008: scr0_q  <= rb_wdata;
          12'h00C: scr1_q  <= rb_wdata;
          12'h010: tst_q   <= rb_wdata;
          12'h01C: cgoff_q <= rb_wdata[0];
          12'h024: if (rb_wdata[0]) bev_q <= 1'b0;
          12'h028: begin mbg_q <= rb_wdata[1]; mgrp_q <= rb_wdata[4]; mien_q <= rb_wdata[8]; end
          12'h030: db_q    <= rb_wdata[0];
          default: ;
        endcase
      end
    end
  end

  // soft reset: keyed write -> 8-cycle pulse, generator on the pin reset
  logic [3:0] srst_cnt;
  logic       cause_soft_q;
  wire        srst_req = wr && rb_addr == 12'h014 && rb_wdata == 32'h5AFE_0001;
  always_ff @(posedge clk or negedge por_rst_n) begin
    if (!por_rst_n) begin
      srst_cnt     <= '0;
      cause_soft_q <= 1'b0;
    end else begin
      if (srst_req) begin
        srst_cnt     <= 4'd8;
        cause_soft_q <= 1'b1;
      end else if (srst_cnt != 4'd0) begin
        srst_cnt <= srst_cnt - 4'd1;
      end
    end
  end
  assign soft_reset = (srst_cnt != 4'd0);

  assign mbist_start = mstart_q;
  assign mbist_bg    = mbg_q;
  assign mbist_group = mgrp_q;
  assign tile_cg_off = cgoff_q;
  assign test_status = tst_q;
  assign test_pass   = (tst_q[1:0] == 2'd1);
  assign test_fail   = (tst_q[1:0] == 2'd2);
  assign irq_berr    = bev_q;
  assign irq_mbist   = mien_q && mbist_done;
  assign irq_dbg     = db_q;

  always_comb begin
    rb_rdata = 32'd0;
    rb_err   = 1'b0;
    case (rb_addr)
      12'h000: rb_rdata = sfv_pkg::CHIP_ID;
      12'h004: rb_rdata = {30'd0, boot_q};
      12'h008: rb_rdata = scr0_q;
      12'h00C: rb_rdata = scr1_q;
      12'h010: rb_rdata = tst_q;
      12'h014: rb_rdata = 32'd0;
      12'h018: rb_rdata = {29'd0, jtag_cpu_hold, cause_soft_q, !cause_soft_q};
      12'h01C: rb_rdata = {31'd0, cgoff_q};
      12'h020: rb_rdata = beaddr_q;
      12'h024: rb_rdata = {28'd0, bewe_q, bem_q, bev_q};
      12'h028: rb_rdata = {23'd0, mien_q, 3'd0, mgrp_q, 2'd0, mbg_q, 1'b0};
      12'h02C: rb_rdata = {mbist_fail_addr, 1'b0, mbist_fail_elem, mbist_fail_bank,
                           5'd0, mbist_fail, mbist_done && !mstart_q, mbist_busy || mstart_q};
      12'h030: rb_rdata = {31'd0, db_q};
      default: rb_err = 1'b1;
    endcase
  end
endmodule

`default_nettype wire
