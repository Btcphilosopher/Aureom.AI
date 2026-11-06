// =============================================================================
// SilicaFlux DataFabric :: dma_control_regs -- DMA register file
//
// Slave of the SilicaFlux-V register bus (silicaflux-v rtl/bus/
// sfv_periph_bridge.sv): rb_sel one-cycle strobe, rb_we, rb_addr[11:0],
// rb_wdata; rb_rdata/rb_err answered combinationally in the strobe cycle;
// side effects at the end of the strobe cycle.  32-bit registers only (the
// bridge already rejects sub-word writes).  Map: docs/datafabric/DMA.md,
// generated from memmap/silicaflux_v_datafabric.yaml (dma_defs.svh).
//
// Busy-state protection: while the engine is busy, writes to SRC_ADDR,
// DST_ADDR and LENGTH and CONTROL.START are refused with rb_err = 1 and have
// no effect (the active transfer is never modified).  CONTROL.ABORT is
// accepted at any time (no effect when idle).  Writes to read-only registers
// and accesses to unmapped offsets return rb_err = 1.  No read side effects.
// =============================================================================
`include "dma_defs.svh"
`default_nettype none

module dma_control_regs #(
  parameter int DW           = 32,
  parameter int ENGINE       = 0,
  parameter int FIFO_DEPTH   = 1,
  parameter int MAX_LEN_LOG2 = 24,
  parameter int PERF         = 1          // ACTIVE_CYCLES / STALL_CYCLES / TRANSFERS present
) (
  input  wire logic        clk,
  input  wire logic        rst_n,
  // register bus
  input  wire logic        rb_sel,
  input  wire logic        rb_we,
  input  wire logic [11:0] rb_addr,
  input  wire logic [31:0] rb_wdata,
  output logic [31:0]      rb_rdata,
  output logic             rb_err,
  // engine control / status
  output logic             start,
  output logic             abort,
  output logic [31:0]      cfg_src,
  output logic [31:0]      cfg_dst,
  output logic [31:0]      cfg_len,
  input  wire logic        busy,
  input  wire logic        done,
  input  wire logic        fail,
  input  wire logic [3:0]  err_code,
  input  wire logic [31:0] err_addr,
  input  wire logic [31:0] bytes_done,
  input  wire logic [2:0]  state,
  input  wire logic        ev_stall,
  output logic             irq
);
  logic        st_done_q, st_err_q, st_abt_q;
  logic [1:0]  ie_q;
  logic [1:0]  is_q;
  logic [31:0] act_q, stl_q, xfer_q;

  wire wr = rb_sel && rb_we;
  wire is_cfg = (rb_addr == `DMA_REG_SRC_ADDR) || (rb_addr == `DMA_REG_DST_ADDR) ||
                (rb_addr == `DMA_REG_LENGTH);
  wire start_req = wr && rb_addr == `DMA_REG_CONTROL && rb_wdata[`DMA_CONTROL_START];
  assign start = start_req && !busy;
  // a refused write (START while busy) has no effect at all, ABORT included
  assign abort = wr && rb_addr == `DMA_REG_CONTROL && rb_wdata[`DMA_CONTROL_ABORT] && !(start_req && busy);

  localparam logic [31:0] INFO = {8'h01, 8'(MAX_LEN_LOG2), 4'($clog2(FIFO_DEPTH)), 3'd0, 1'(ENGINE), 8'(DW / 8)};

  // ------------------------------------------------------------ read mux / errors
  // reads: error only for unmapped offsets (and absent perf registers);
  // writes: error for read-only registers, unmapped offsets, and for
  // SRC/DST/LENGTH or START while busy.
  always_comb begin
    rb_rdata = 32'd0;
    rb_err   = 1'b0;
    if (rb_sel) begin
      case (rb_addr)
        `DMA_REG_CONTROL:       rb_err = rb_we && start_req && busy;      // reads return 0
        `DMA_REG_STATUS:        begin rb_rdata = {21'd0, state, 4'd0, st_abt_q, st_err_q, st_done_q, busy};
                                      rb_err   = rb_we; end
        `DMA_REG_SRC_ADDR:      begin rb_rdata = cfg_src;    rb_err = rb_we && busy; end
        `DMA_REG_DST_ADDR:      begin rb_rdata = cfg_dst;    rb_err = rb_we && busy; end
        `DMA_REG_LENGTH:        begin rb_rdata = cfg_len;    rb_err = rb_we && busy; end
        `DMA_REG_BYTES_DONE:    begin rb_rdata = bytes_done; rb_err = rb_we; end
        `DMA_REG_INT_ENABLE:    rb_rdata = {30'd0, ie_q};
        `DMA_REG_INT_STATUS:    rb_rdata = {30'd0, is_q};
        `DMA_REG_ERROR_CODE:    begin rb_rdata = {28'd0, err_code}; rb_err = rb_we; end
        `DMA_REG_ERROR_ADDR:    begin rb_rdata = err_addr;   rb_err = rb_we; end
        `DMA_REG_INFO:          begin rb_rdata = INFO;       rb_err = rb_we; end
        `DMA_REG_ID:            begin rb_rdata = `DMA_ID_VALUE; rb_err = rb_we; end
        `DMA_REG_ACTIVE_CYCLES: begin rb_rdata = act_q;  rb_err = rb_we || (PERF == 0); end
        `DMA_REG_STALL_CYCLES:  begin rb_rdata = stl_q;  rb_err = rb_we || (PERF == 0); end
        `DMA_REG_TRANSFERS:     begin rb_rdata = xfer_q; rb_err = rb_we || (PERF == 0); end
        default:                rb_err = 1'b1;
      endcase
    end
  end

  // ------------------------------------------------------------ registers
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      cfg_src   <= '0;
      cfg_dst   <= '0;
      cfg_len   <= '0;
      ie_q      <= '0;
      st_done_q <= 1'b0;
      st_err_q  <= 1'b0;
      st_abt_q  <= 1'b0;
    end else begin
      if (wr && !busy && is_cfg) begin
        if (rb_addr == `DMA_REG_SRC_ADDR) cfg_src <= rb_wdata;
        if (rb_addr == `DMA_REG_DST_ADDR) cfg_dst <= rb_wdata;
        if (rb_addr == `DMA_REG_LENGTH)   cfg_len <= rb_wdata;
      end
      if (wr && rb_addr == `DMA_REG_INT_ENABLE) ie_q <= rb_wdata[1:0];
      if (start) begin
        st_done_q <= 1'b0;
        st_err_q  <= 1'b0;
        st_abt_q  <= 1'b0;
      end
      if (done) st_done_q <= 1'b1;
      if (fail) begin
        st_err_q <= 1'b1;
        st_abt_q <= (err_code == `DMA_ERR_ABORTED);
      end
    end
  end

  dma_irq u_irq (
    .clk, .rst_n,
    .set_done(done), .set_err(fail),
    .clr_wr(wr && rb_addr == `DMA_REG_INT_STATUS), .clr_mask(rb_wdata[1:0]),
    .enable(ie_q), .status(is_q), .irq
  );

  // ------------------------------------------------------------ performance counters
  if (PERF != 0) begin : g_perf
    always_ff @(posedge clk or negedge rst_n) begin
      if (!rst_n) begin
        act_q  <= '0;
        stl_q  <= '0;
        xfer_q <= '0;
      end else begin
        if (start) begin
          act_q <= '0;
          stl_q <= '0;
        end else begin
          if (busy)     act_q <= act_q + 32'd1;      // wraps at 2^32 (documented)
          if (ev_stall) stl_q <= stl_q + 32'd1;
        end
        if (done) xfer_q <= xfer_q + 32'd1;
      end
    end
  end else begin : g_noperf
    /* verilator lint_off UNUSEDSIGNAL */
    wire unused_stall = ev_stall;          // counters compiled out (area-minimised build)
    /* verilator lint_on UNUSEDSIGNAL */
    assign act_q  = '0;
    assign stl_q  = '0;
    assign xfer_q = '0;
  end
endmodule

`default_nettype wire
