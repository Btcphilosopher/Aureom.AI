// =============================================================================
// SilicaFlux DataFabric :: sfb_perf_counters -- optional fabric/DMA counters
//
// Register-bus page (DFPERF, map generated in sfb_perf_defs.svh).  Counts the
// crossbar event outputs per master (reads, writes, request-stall cycles,
// arbitration-loss cycles, response-stall cycles, error responses) plus DMA
// bytes / busy / idle cycles, maximum DMA FIFO occupancy and a 64-bit cycle
// counter.
//   * event counters are CW bits and SATURATE at all-ones (no silent wrap);
//   * CTRL.SNAPSHOT copies every live counter into the read registers in the
//     same cycle: software reads a mutually consistent set, including both
//     halves of the 64-bit cycle counter (atomic wide-counter read);
//   * CTRL.CLEAR zeroes the live counters; CTRL.ENABLE gates counting;
//   * the whole block is optional: sfv_soc_df PERF = 0 removes it (page then
//     answers with a bus error).  Cost is reported in reports/datafabric.
// =============================================================================
`include "sfb_perf_defs.svh"
`default_nettype none

module sfb_perf_counters #(
  parameter int NM = 4,
  parameter int CW = 32
) (
  input  wire logic          clk,
  input  wire logic          rst_n,
  // register bus
  input  wire logic          rb_sel,
  input  wire logic          rb_we,
  input  wire logic [11:0]   rb_addr,
  /* verilator lint_off UNUSEDSIGNAL */
  input  wire logic [31:0]   rb_wdata,       // only CTRL[2:0] is writable
  /* verilator lint_on UNUSEDSIGNAL */
  output logic [31:0]        rb_rdata,
  output logic               rb_err,
  // events
  input  wire logic [NM-1:0] ev_accept,
  input  wire logic [NM-1:0] ev_write,       // with ev_accept: request is a write
  input  wire logic [NM-1:0] ev_req_stall,
  input  wire logic [NM-1:0] ev_arb_loss,
  input  wire logic [NM-1:0] ev_rsp_stall,
  input  wire logic [NM-1:0] ev_rsp_error,   // error response accepted
  input  wire logic          dma_busy,
  input  wire logic          dma_done,
  input  wire logic [31:0]   dma_bytes,      // bytes of the transfer completing with dma_done
  input  wire logic [7:0]    fifo_level
);
  localparam int NE  = 6;                      // per-master events
  localparam int IXW = $clog2(NM * NE);
  logic [CW-1:0] live [0:NM*NE-1];
  logic [CW-1:0] shad [0:NM*NE-1];
  logic [CW-1:0] dbytes, dbusy, didle, sdbytes, sdbusy, sdidle;
  logic [7:0]    fmax, sfmax;
  logic [63:0]   cyc, scyc;
  logic          en_q;

  wire wr   = rb_sel && rb_we;
  wire ctrl = wr && rb_addr == `DFP_REG_CTRL;
  wire clr  = ctrl && rb_wdata[`DFP_CTRL_CLEAR];
  wire snap = ctrl && rb_wdata[`DFP_CTRL_SNAPSHOT];

  function automatic logic [CW-1:0] sat_inc(input logic [CW-1:0] v, input logic e);
    sat_inc = (e && v != '1) ? v + 1'b1 : v;
  endfunction

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      en_q <= 1'b1;
      for (int i = 0; i < NM * NE; i++) live[i] <= '0;
      dbytes <= '0; dbusy <= '0; didle <= '0; fmax <= '0; cyc <= '0;
    end else begin
      if (ctrl) en_q <= rb_wdata[`DFP_CTRL_ENABLE];
      if (clr) begin
        for (int i = 0; i < NM * NE; i++) live[i] <= '0;
        dbytes <= '0; dbusy <= '0; didle <= '0; fmax <= '0; cyc <= '0;
      end else if (en_q) begin
        for (int m = 0; m < NM; m++) begin
          live[m*NE + 0] <= sat_inc(live[m*NE + 0], ev_accept[m] && !ev_write[m]);
          live[m*NE + 1] <= sat_inc(live[m*NE + 1], ev_accept[m] && ev_write[m]);
          live[m*NE + 2] <= sat_inc(live[m*NE + 2], ev_req_stall[m]);
          live[m*NE + 3] <= sat_inc(live[m*NE + 3], ev_arb_loss[m]);
          live[m*NE + 4] <= sat_inc(live[m*NE + 4], ev_rsp_stall[m]);
          live[m*NE + 5] <= sat_inc(live[m*NE + 5], ev_rsp_error[m]);
        end
        if (dma_done) dbytes <= ({1'b0, dbytes} + {1'b0, dma_bytes} > {1'b0, {CW{1'b1}}}) ? '1 : dbytes + dma_bytes;
        dbusy <= sat_inc(dbusy, dma_busy);
        didle <= sat_inc(didle, !dma_busy);
        if (fifo_level > fmax) fmax <= fifo_level;
        cyc <= cyc + 64'd1;
      end
    end
  end

  // snapshot registers: datapath copies, loaded atomically on SNAPSHOT
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      for (int i = 0; i < NM * NE; i++) shad[i] <= '0;
      sdbytes <= '0; sdbusy <= '0; sdidle <= '0; sfmax <= '0; scyc <= '0;
    end else if (snap) begin
      for (int i = 0; i < NM * NE; i++) shad[i] <= live[i];
      sdbytes <= dbytes; sdbusy <= dbusy; sdidle <= didle; sfmax <= fmax; scyc <= cyc;
    end
  end

  // read mux
  logic [11:0] pm_off;
  logic [7:0]  pm_m;
  logic [4:0]  pm_r;
  always_comb begin
    rb_rdata = 32'd0;
    rb_err   = 1'b0;
    pm_off   = rb_addr - `DFP_PM_BASE;
    pm_m     = 8'(pm_off >> $clog2(`DFP_PM_STRIDE));
    pm_r     = pm_off[4:0];
    if (rb_sel) begin
      case (rb_addr)
        `DFP_REG_CTRL:      rb_rdata = {31'd0, en_q};
        `DFP_REG_INFO:      begin rb_rdata = {16'd0, 8'(CW), 8'(NM)}; rb_err = rb_we; end
        `DFP_REG_CYCLES_LO: begin rb_rdata = scyc[31:0];  rb_err = rb_we; end
        `DFP_REG_CYCLES_HI: begin rb_rdata = scyc[63:32]; rb_err = rb_we; end
        `DFP_REG_DMA_BYTES: begin rb_rdata = 32'(sdbytes); rb_err = rb_we; end
        `DFP_REG_DMA_BUSY:  begin rb_rdata = 32'(sdbusy);  rb_err = rb_we; end
        `DFP_REG_DMA_IDLE:  begin rb_rdata = 32'(sdidle);  rb_err = rb_we; end
        `DFP_REG_FIFO_MAX:  begin rb_rdata = 32'(sfmax);   rb_err = rb_we; end
        default: begin
          rb_err = 1'b1;
          if (rb_addr >= `DFP_PM_BASE && pm_m < 8'(NM) && pm_r[1:0] == 2'b00 && pm_r < 5'(NE * 4)) begin
            rb_rdata = 32'(shad[IXW'(pm_m * 8'(NE) + 8'(pm_r[4:2]))]);
            rb_err   = rb_we;
          end
        end
      endcase
    end
  end
endmodule

`default_nettype wire
