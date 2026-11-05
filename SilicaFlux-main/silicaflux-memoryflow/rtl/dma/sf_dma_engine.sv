// =============================================================================
// SilicaFlux MemoryFlow :: sf_dma_engine
// One DMA data-movement engine (burst scheduler + read side + data FIFO +
// write side).  sf_dma instantiates TWO of these:
//
//   engine 0  (SRC_STREAM = 0): memory-sourced channels  MEM->MEM, MEM->STREAM
//   engine 1  (SRC_STREAM = 1): stream-sourced channels  STREAM->MEM
//
// Why two engines: with a single shared engine, a stream-sourced burst
// (accelerator -> SRAM) occupies the read side while waiting for results that
// can only be produced once memory-sourced bursts (SRAM -> accelerator) have
// run -> the DMA deadlocks against its own accelerator.  This was found by
// tb_system and is the reason MM2S / S2MM paths are independent here (the
// same split used by production AXI DMA engines).
//
// The engine owns no channel registers: sf_dma supplies the eligibility
// vector and, combinationally, the burst parameters for the channel the
// engine's round-robin scheduler selects.
// Classification: SYNTHESIZABLE
// =============================================================================
`default_nettype none

module sf_dma_engine #(
  parameter bit SRC_STREAM     = 1'b0,
  parameter int NCH            = 4,
  parameter int DW             = 64,
  parameter int AW             = 32,
  parameter int NSO            = 4,
  parameter int NSI            = 2,
  parameter int DFIFO_DEPTH    = 16,
  parameter int DESC_DEPTH     = 4,
  parameter int MAX_BURST_LOG2 = 4,
  localparam int NB            = DW / 8,
  localparam int CHW           = (NCH > 1) ? $clog2(NCH) : 1,
  localparam int NBW           = MAX_BURST_LOG2 + 1,
  localparam int SOW           = (NSO > 1) ? $clog2(NSO) : 1,
  localparam int SIW           = (NSI > 1) ? $clog2(NSI) : 1
) (
  input  logic              clk,
  input  logic              rst_n,
  // ---- scheduling handshake with the channel table
  input  logic [NCH-1:0]    elig,           // channels this engine may schedule
  input  logic [NCH-1:0]    ch_err,         // channel has failed / been aborted
  output logic              sch_valid,      // a burst is scheduled this cycle
  output logic [CHW-1:0]    sch_idx,
  input  logic [AW-1:0]     b_src,          // burst params for sch_idx (comb)
  input  logic [AW-1:0]     b_dst,
  input  logic [NBW-1:0]    b_nb,
  input  logic              b_rowend,
  input  logic              b_last,
  input  logic              b_dst_str,
  input  logic [1:0]        b_dport,
  input  logic [1:0]        b_sport,
  input  logic [NB-1:0]     b_tail,
  output logic              idle_rd,        // read side idle (no burst open)
  // ---- memory read master (engine 0)
  output logic              rd_req_valid,
  input  logic              rd_req_ready,
  output logic [AW-1:0]     rd_req_addr,
  input  logic              rd_rsp_valid,
  input  logic [DW-1:0]     rd_rsp_rdata,
  input  logic              rd_rsp_err,
  // ---- stream inputs (engine 1)
  input  logic [NSI-1:0]    si_valid,
  output logic [NSI-1:0]    si_ready,
  input  logic [NSI*DW-1:0] si_data,
  // ---- memory write request (arbitrated in sf_dma)
  output logic              wr_req_valid,
  input  logic              wr_req_ready,
  output logic [AW-1:0]     wr_req_addr,
  output logic [DW-1:0]     wr_req_wdata,
  output logic [NB-1:0]     wr_req_wstrb,
  output logic [CHW-1:0]    wr_req_ch,
  input  logic              wack_space,     // ack-tracking FIFO has room
  // ---- stream outputs (engine 0)
  output logic [NSO-1:0]    so_valid,
  input  logic [NSO-1:0]    so_ready,
  output logic [DW-1:0]     so_data,
  output logic [NB-1:0]     so_strb,
  output logic              so_last,
  // ---- events to the channel table
  output logic              retire_w,       // beat retired by the write side
  output logic [CHW-1:0]    retire_w_ch,
  output logic              rd_err,         // read data error seen at write side
  output logic [CHW-1:0]    rd_err_ch
);
  localparam int DCW = $clog2(DFIFO_DEPTH + 1);

  // ================================================================ scheduler
  typedef enum logic {R_IDLE, R_BURST} rst_t;
  rst_t           rs;
  logic           ds_push_ready;
  logic [DCW-1:0] rd_out;

  logic [NCH-1:0] req;
  assign req = (rs == R_IDLE && ds_push_ready) ? elig : '0;

  /* verilator lint_off UNUSEDSIGNAL */
  logic [NCH-1:0] sch_grant;
  /* verilator lint_on UNUSEDSIGNAL */
  sf_rr_arbiter #(.N(NCH)) u_sched (
    .clk, .rst_n, .req, .accept(sch_valid),
    .grant(sch_grant), .grant_idx(sch_idx), .grant_valid(sch_valid));

  assign idle_rd = (rs == R_IDLE) && (rd_out == '0);

  // ================================================================ data FIFO
  logic           df_push, df_pop, df_valid;
  logic [DW+1:0]  df_din, df_dout;          // {kill, err, data}
  /* verilator lint_off UNUSEDSIGNAL */
  logic           df_ready_unused;
  logic [DCW-1:0] df_cnt_unused;
  /* verilator lint_on UNUSEDSIGNAL */
  sf_fifo #(.WIDTH(DW + 2), .DEPTH(DFIFO_DEPTH)) u_dfifo (
    .clk, .rst_n,
    .push_valid(df_push), .push_ready(df_ready_unused), .push_data(df_din),
    .pop_valid(df_valid), .pop_ready(df_pop), .pop_data(df_dout), .count(df_cnt_unused));

  logic [DCW-1:0] reserved;                 // in-flight reads + FIFO beats
  wire  credit = (reserved < DCW'(DFIFO_DEPTH));

  // ================================================================ descriptor FIFO
  localparam int DSW = CHW + AW + NBW + 1 + 1 + 1 + 2 + NB;
  logic           ds_valid, ds_pop;
  logic [DSW-1:0] ds_dout;
  /* verilator lint_off UNUSEDSIGNAL */
  logic [$clog2(DESC_DEPTH+1)-1:0] ds_cnt_unused;
  /* verilator lint_on UNUSEDSIGNAL */
  sf_fifo #(.WIDTH(DSW), .DEPTH(DESC_DEPTH)) u_desc (
    .clk, .rst_n,
    .push_valid(sch_valid), .push_ready(ds_push_ready),
    .push_data({sch_idx, b_dst, b_nb, b_rowend, b_last, b_dst_str, b_dport, b_tail}),
    .pop_valid(ds_valid), .pop_ready(ds_pop), .pop_data(ds_dout), .count(ds_cnt_unused));

  // ================================================================ read side
  logic [CHW-1:0] r_ch;
  logic [AW-1:0]  r_addr;
  logic [NBW-1:0] r_left;
  /* verilator lint_off UNUSEDSIGNAL */
  logic [1:0]     r_sport;
  /* verilator lint_on UNUSEDSIGNAL */

  wire r_act  = (rs == R_BURST);
  wire r_kill = r_act && ch_err[r_ch] && SRC_STREAM;     // aborted stream source
  wire r_str  = r_act && SRC_STREAM && !ch_err[r_ch];
  wire r_mem  = r_act && !SRC_STREAM;

  assign rd_req_valid = r_mem && credit;
  assign rd_req_addr  = r_addr;

  always_comb begin
    si_ready = '0;
    if (r_str && credit) si_ready[SIW'(r_sport)] = 1'b1;
  end
  wire si_fire    = r_str && credit && si_valid[SIW'(r_sport)];
  wire rd_fire    = rd_req_valid && rd_req_ready;
  wire kill_fire  = r_kill && credit;
  wire beat_issue = rd_fire || si_fire || kill_fire;

  always_comb begin
    df_push = 1'b0;
    df_din  = '0;
    if (!SRC_STREAM && rd_rsp_valid) begin
      df_push = 1'b1;
      df_din  = {1'b0, rd_rsp_err, rd_rsp_rdata};
    end else if (si_fire) begin
      df_push = 1'b1;
      df_din  = {1'b0, 1'b0, si_data[SIW'(r_sport)*DW +: DW]};
    end else if (kill_fire) begin
      df_push = 1'b1;
      df_din  = {1'b1, 1'b0, {DW{1'b0}}};
    end
  end

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      rs      <= R_IDLE;
      r_ch    <= '0;
      r_addr  <= '0;
      r_left  <= '0;
      r_sport <= '0;
    end else begin
      case (rs)
        R_IDLE: if (sch_valid) begin
          rs      <= R_BURST;
          r_ch    <= sch_idx;
          r_addr  <= b_src;
          r_left  <= b_nb;
          r_sport <= b_sport;
        end
        default: if (beat_issue) begin
          r_addr <= r_addr + AW'(NB);
          r_left <= r_left - NBW'(1);
          if (r_left == NBW'(1)) rs <= R_IDLE;
        end
      endcase
    end
  end

  // ================================================================ write side
  typedef enum logic {W_IDLE, W_BURST} wst_t;
  wst_t           ws;
  logic [CHW-1:0] w_ch;
  logic [AW-1:0]  w_addr;
  logic [NBW-1:0] w_left;
  logic           w_rowend, w_xlast, w_dstr;
  logic [1:0]     w_dport;
  logic [NB-1:0]  w_tail;

  wire h_kill = df_dout[DW+1];
  wire h_err  = df_dout[DW];
  wire w_act  = (ws == W_BURST) && df_valid;
  wire w_drop = w_act && (h_kill || h_err || ch_err[w_ch]);
  wire [NB-1:0] w_strb = (w_left == NBW'(1) && w_rowend) ? w_tail : {NB{1'b1}};

  assign wr_req_valid = w_act && !w_drop && !w_dstr && wack_space;
  assign wr_req_addr  = w_addr;
  assign wr_req_wdata = df_dout[DW-1:0];
  assign wr_req_wstrb = w_strb;
  assign wr_req_ch    = w_ch;

  always_comb begin
    so_valid = '0;
    if (!SRC_STREAM && w_act && !w_drop && w_dstr) so_valid[SOW'(w_dport)] = 1'b1;
  end
  assign so_data = df_dout[DW-1:0];
  assign so_strb = w_strb;
  assign so_last = w_xlast && (w_left == NBW'(1));

  wire wr_fire = wr_req_valid && wr_req_ready;
  wire so_fire = |(so_valid & so_ready);
  assign df_pop = w_drop || wr_fire || so_fire;
  assign ds_pop = (ws == W_IDLE) && ds_valid;

  assign retire_w    = w_drop || so_fire;
  assign retire_w_ch = w_ch;
  assign rd_err      = w_act && h_err && !h_kill;
  assign rd_err_ch   = w_ch;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      ws       <= W_IDLE;
      w_ch     <= '0;
      w_addr   <= '0;
      w_left   <= '0;
      w_rowend <= 1'b0;
      w_xlast  <= 1'b0;
      w_dstr   <= 1'b0;
      w_dport  <= '0;
      w_tail   <= '0;
    end else begin
      case (ws)
        W_IDLE: if (ds_valid) begin
          ws <= W_BURST;
          {w_ch, w_addr, w_left, w_rowend, w_xlast, w_dstr, w_dport, w_tail} <= ds_dout;
        end
        default: if (df_pop) begin
          w_addr <= w_addr + AW'(NB);
          w_left <= w_left - NBW'(1);
          if (w_left == NBW'(1)) ws <= W_IDLE;
        end
      endcase
    end
  end

  // ================================================================ credits
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      reserved <= '0;
      rd_out   <= '0;
    end else begin
      reserved <= reserved + DCW'(beat_issue) - DCW'(df_pop);
      rd_out   <= rd_out + DCW'(rd_fire) - DCW'(!SRC_STREAM && rd_rsp_valid);
    end
  end

`ifndef SYNTHESIS
  // pragma translate_off
  always_ff @(posedge clk) begin
    if (df_push && !df_ready_unused) $error("sf_dma_engine: data FIFO overflow (credit bug)");
  end
  // pragma translate_on
`endif

endmodule

`default_nettype wire
