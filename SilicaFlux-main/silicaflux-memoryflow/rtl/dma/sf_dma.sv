// =============================================================================
// SilicaFlux MemoryFlow :: sf_dma
// Multi-channel descriptor-register DMA engine.
//
// Endpoints per channel: memory (SF-MEM read / write master) or an
// accelerator stream port (valid/ready/data/strb/last).  This gives
//   MEM->MEM, MEM->ACCEL (SRAM-to-accelerator), ACCEL->MEM (ACCEL->ACCEL is
//   rejected with ERR_CODE 7: use the accelerators' direct stream links).
//
// Architecture: a shared channel table (registers + per-channel progress)
// feeds TWO independent sf_dma_engine instances -- engine 0 for memory-
// sourced channels (MM2S + MEM->MEM) and engine 1 for stream-sourced channels
// (S2MM).  Their memory writes share the write master through a round-robin
// arbiter.  A single shared engine deadlocks when an accelerator's result
// stream is being collected by the same engine that must feed its operands
// (found by tb_system; see docs/verification.md).
//
// Features
//   * APB3 control/status registers (map below), level interrupt.
//   * 1-D and 2-D (strided rows: tensor tiles) transfers.
//   * Bursts: a channel holds the engine for up to 2^BURST_LOG2 beats, then
//     the round-robin scheduler re-arbitrates between channels.
//   * Read/write decoupled through a data FIFO with credit-based flow
//     control; up to DFIFO_DEPTH reads in flight -> hides memory latency.
//   * Byte-granular lengths: the final beat of each row carries a tail
//     strobe (only valid bytes are written).
//   * Start-time validation: zero length, misalignment, 32-bit address
//     overflow of the whole (2-D) footprint are rejected BEFORE any data
//     moves.  Bus errors on read data / write acks, and software ABORT,
//     terminate the channel and drain its in-flight beats cleanly.
//
// Register map (byte offsets, 32-bit registers)
//   0x000 ID          RO  0x5346_444D ("SFDM")
//   0x004 CAPS        RO  {NSI[7:0], NSO[7:0], beat_bytes[7:0], NCH[7:0]}
//   0x008 IRQ_STATUS  RO  bit c = channel c interrupt pending
//   ch c base = 0x100 + 0x40*c
//   +0x00 CTRL   [0] START (W1, self-clearing)   [1] IRQ_EN
//                [2] SRC_STREAM  [3] DST_STREAM  [7:4] BURST_LOG2
//                [8] MODE_2D     [9] ABORT (W1)  [13:12] SRC_PORT
//                [17:16] DST_PORT
//   +0x04 STATUS [0] BUSY  [1] DONE (W1C)  [2] ERR (W1C)  [7:4] ERR_CODE
//   +0x08 SRC    +0x0C DST   +0x10 LEN (bytes/row)   +0x14 ROWS (2-D)
//   +0x18 SRC_STRIDE   +0x1C DST_STRIDE   +0x20 BEATS (RO, retired beats)
// ERR_CODE: 1 ZERO_LEN, 2 ALIGN, 3 OVERFLOW, 4 RD_BUS, 5 WR_BUS, 6 ABORT,
//           7 INVALID (stream->stream)
// Classification: SYNTHESIZABLE
// =============================================================================
`default_nettype none

module sf_dma #(
  parameter int NCH            = 2,
  parameter int DW             = 64,
  parameter int AW             = 32,
  parameter int NSO            = 4,     // stream outputs (to accelerators)
  parameter int NSI            = 2,     // stream inputs (from accelerators)
  parameter int DFIFO_DEPTH    = 16,
  parameter int DESC_DEPTH     = 4,
  parameter int WOUT           = 8,     // max outstanding write acks
  parameter int MAX_BURST_LOG2 = 4,
  localparam int NB            = DW / 8,
  localparam int OFF           = $clog2(NB),
  localparam int CHW           = (NCH > 1) ? $clog2(NCH) : 1,
  localparam int SIW           = (NSI > 1) ? $clog2(NSI) : 1
) (
  input  logic              clk,
  input  logic              rst_n,
  // APB3 slave
  input  logic              psel,
  input  logic              penable,
  input  logic              pwrite,
  input  logic [11:0]       paddr,
  input  logic [31:0]       pwdata,
  output logic [31:0]       prdata,
  output logic              pready,
  output logic              pslverr,
  output logic              irq,
  // memory read master
  output logic              rd_req_valid,
  input  logic              rd_req_ready,
  output logic [AW-1:0]     rd_req_addr,
  input  logic              rd_rsp_valid,
  output logic              rd_rsp_ready,
  input  logic [DW-1:0]     rd_rsp_rdata,
  input  logic              rd_rsp_err,
  // memory write master
  output logic              wr_req_valid,
  input  logic              wr_req_ready,
  output logic [AW-1:0]     wr_req_addr,
  output logic [DW-1:0]     wr_req_wdata,
  output logic [NB-1:0]     wr_req_wstrb,
  input  logic              wr_rsp_valid,
  output logic              wr_rsp_ready,
  input  logic              wr_rsp_err,
  // stream outputs (DMA -> accelerator); data/strb/last are shared buses
  output logic [NSO-1:0]    so_valid,
  input  logic [NSO-1:0]    so_ready,
  output logic [DW-1:0]     so_data,
  output logic [NB-1:0]     so_strb,
  output logic              so_last,
  // stream inputs (accelerator -> DMA)
  input  logic [NSI-1:0]    si_valid,
  output logic [NSI-1:0]    si_ready,
  input  logic [NSI*DW-1:0] si_data
);
  localparam int NBW = MAX_BURST_LOG2 + 1;         // burst beat count width
  localparam int IFW = 20;                         // per-channel in-flight beats

  localparam logic [3:0] E_ZERO = 4'd1, E_ALIGN = 4'd2, E_OVF = 4'd3,
                         E_RD   = 4'd4, E_WR    = 4'd5, E_ABORT = 4'd6, E_INV = 4'd7;

  // ================================================================ registers
  logic          c_irq_en  [NCH];
  logic          c_src_str [NCH];
  logic          c_dst_str [NCH];
  logic [3:0]    c_blog2   [NCH];
  logic          c_2d      [NCH];
  logic [1:0]    c_sport   [NCH];
  logic [1:0]    c_dport   [NCH];
  logic [31:0]   c_src     [NCH];
  logic [31:0]   c_dst     [NCH];
  logic [31:0]   c_len     [NCH];
  logic [15:0]   c_rows    [NCH];
  logic [31:0]   c_sstr    [NCH];
  logic [31:0]   c_dstr    [NCH];
  logic [31:0]   c_beats   [NCH];
  logic          c_busy    [NCH];
  logic          c_done    [NCH];
  logic          c_err     [NCH];
  logic [3:0]    c_ecode   [NCH];

  // working state
  logic [AW-1:0]  w_srow    [NCH];   // current source row start
  logic [AW-1:0]  w_drow    [NCH];   // current destination row start
  logic [AW-1:0]  w_bir     [NCH];   // beats issued in current row
  logic [15:0]    w_rows    [NCH];   // rows left (incl. current)
  logic           w_sdone   [NCH];   // scheduling complete
  logic [IFW-1:0] w_infl    [NCH];   // scheduled-but-not-retired beats

  // ---------------------------------------------------------------- APB decode
  wire        apb_wr = psel && penable && pwrite;
  wire        apb_rd = psel && !pwrite;
  localparam logic [11:0] CH_END = 12'(256 + 64 * NCH);
  wire        is_ch  = (paddr >= 12'h100) && (paddr < CH_END);
  wire [11:0] choff  = paddr - 12'h100;
  wire [CHW-1:0] wch = CHW'(choff >> 6);
  wire [5:0]  creg   = choff[5:0];
  wire        is_glb = (paddr == 12'h000) || (paddr == 12'h004) || (paddr == 12'h008);

  assign pready  = 1'b1;
  assign pslverr = psel && penable && !(is_ch || (is_glb && !pwrite));

  // beats per row and tail strobe per channel
  function automatic logic [AW-1:0] beats_per_row(input logic [31:0] len);
    logic [32:0] t;
    begin
      t = {1'b0, len} + 33'(NB - 1);
      beats_per_row = AW'(t >> OFF);
    end
  endfunction

  /* verilator lint_off UNUSEDSIGNAL */
  function automatic logic [NB-1:0] tail_strb(input logic [31:0] len);
    logic [OFF-1:0] r;
    begin
      r = len[OFF-1:0];
      tail_strb = (r == '0) ? {NB{1'b1}} : NB'((1 << r) - 1);
    end
  endfunction
  /* verilator lint_on UNUSEDSIGNAL */

  // start validation (combinational, for the channel being written)
  logic [3:0] v_code;
  logic [AW+16:0] v_send, v_dend;
  logic [15:0]    v_rows_m1;
  wire            v_2d   = pwdata[8];
  wire            v_sstr = pwdata[2];
  wire            v_dstr = pwdata[3];
  always_comb begin
    v_rows_m1 = (!v_2d || c_rows[wch] == 16'd0) ? 16'd0 : (c_rows[wch] - 16'd1);
    v_send = (AW+17)'(c_src[wch]) + (AW+17)'(v_rows_m1 * c_sstr[wch]) +
             (AW+17)'(c_len[wch]) - (AW+17)'(1);
    v_dend = (AW+17)'(c_dst[wch]) + (AW+17)'(v_rows_m1 * c_dstr[wch]) +
             (AW+17)'(c_len[wch]) - (AW+17)'(1);
    v_code = 4'd0;
    if (v_sstr && v_dstr)
      v_code = E_INV;
    else if (c_len[wch] == 32'd0)
      v_code = E_ZERO;
    else if ((!v_sstr && (c_src[wch][OFF-1:0] != '0 || (v_2d && c_sstr[wch][OFF-1:0] != '0))) ||
             (!v_dstr && (c_dst[wch][OFF-1:0] != '0 || (v_2d && c_dstr[wch][OFF-1:0] != '0))))
      v_code = E_ALIGN;
    else if ((!v_sstr && (v_send >> AW) != '0) || (!v_dstr && (v_dend >> AW) != '0))
      v_code = E_OVF;
  end

  // ================================================================ engines
  // per-engine scheduling / burst parameter signals
  logic [NCH-1:0] e_elig     [2];
  logic           e_sch      [2];
  logic [CHW-1:0] e_idx      [2];
  logic [AW-1:0]  e_bsrc     [2];
  logic [AW-1:0]  e_bdst     [2];
  logic [NBW-1:0] e_bnb      [2];
  logic           e_browend  [2];
  logic           e_blast    [2];
  logic           e_retire   [2];
  logic [CHW-1:0] e_retire_ch[2];
  logic           e_rderr    [2];
  logic [CHW-1:0] e_rderr_ch [2];
  logic           e_wvalid   [2];
  logic           e_wready   [2];
  logic [AW-1:0]  e_waddr    [2];
  logic [DW-1:0]  e_wdata    [2];
  logic [NB-1:0]  e_wstrb    [2];
  logic [CHW-1:0] e_wch      [2];
  logic [NCH-1:0] err_vec;
  logic           wa_push_ready;

  always_comb begin
    for (int c = 0; c < NCH; c++) begin
      err_vec[c]   = c_err[c];
      e_elig[0][c] = c_busy[c] && !w_sdone[c] && !c_err[c] && !c_src_str[c];
      // stream-sourced bursts start only once the producer has data
      e_elig[1][c] = c_busy[c] && !w_sdone[c] && !c_err[c] &&  c_src_str[c] &&
                     si_valid[SIW'(c_sport[c])];
    end
  end

  // burst sizing for each engine's selected channel
  genvar ge;
  generate
    for (ge = 0; ge < 2; ge++) begin : g_bsz
      logic [AW-1:0]  bpr, rem;
      logic [NBW-1:0] bmax;
      logic [3:0]     bl;
      always_comb begin
        bpr  = beats_per_row(c_len[e_idx[ge]]);
        rem  = bpr - w_bir[e_idx[ge]];
        bl   = (c_blog2[e_idx[ge]] > 4'(MAX_BURST_LOG2)) ? 4'(MAX_BURST_LOG2) : c_blog2[e_idx[ge]];
        bmax = NBW'(1) << bl;
        e_bnb[ge]     = (rem < AW'(bmax)) ? NBW'(rem) : bmax;
        e_browend[ge] = (AW'(e_bnb[ge]) == rem);
        e_blast[ge]   = e_browend[ge] && (w_rows[e_idx[ge]] == 16'd1);
        e_bsrc[ge]    = w_srow[e_idx[ge]] + (w_bir[e_idx[ge]] << OFF);
        e_bdst[ge]    = w_drow[e_idx[ge]] + (w_bir[e_idx[ge]] << OFF);
      end
    end
  endgenerate

  /* verilator lint_off UNUSEDSIGNAL */
  logic          e0_idle_unused, e1_idle_unused;
  logic [NSI-1:0] e0_si_ready_unused;
  logic [NSO-1:0] e1_so_valid_unused;
  logic [DW-1:0] e1_so_data_unused;
  logic [NB-1:0] e1_so_strb_unused;
  logic          e1_so_last_unused;
  logic          e1_rd_req_valid_unused;
  logic [AW-1:0] e1_rd_req_addr_unused;
  /* verilator lint_on UNUSEDSIGNAL */

  sf_dma_engine #(.SRC_STREAM(1'b0), .NCH(NCH), .DW(DW), .AW(AW), .NSO(NSO), .NSI(NSI),
                  .DFIFO_DEPTH(DFIFO_DEPTH), .DESC_DEPTH(DESC_DEPTH),
                  .MAX_BURST_LOG2(MAX_BURST_LOG2)) u_eng0 (
    .clk, .rst_n,
    .elig(e_elig[0]), .ch_err(err_vec), .sch_valid(e_sch[0]), .sch_idx(e_idx[0]),
    .b_src(e_bsrc[0]), .b_dst(e_bdst[0]), .b_nb(e_bnb[0]), .b_rowend(e_browend[0]),
    .b_last(e_blast[0]), .b_dst_str(c_dst_str[e_idx[0]]), .b_dport(c_dport[e_idx[0]]),
    .b_sport(c_sport[e_idx[0]]), .b_tail(tail_strb(c_len[e_idx[0]])), .idle_rd(e0_idle_unused),
    .rd_req_valid, .rd_req_ready, .rd_req_addr, .rd_rsp_valid, .rd_rsp_rdata, .rd_rsp_err,
    .si_valid('0), .si_ready(e0_si_ready_unused), .si_data('0),
    .wr_req_valid(e_wvalid[0]), .wr_req_ready(e_wready[0]), .wr_req_addr(e_waddr[0]),
    .wr_req_wdata(e_wdata[0]), .wr_req_wstrb(e_wstrb[0]), .wr_req_ch(e_wch[0]),
    .wack_space(wa_push_ready),
    .so_valid, .so_ready, .so_data, .so_strb, .so_last,
    .retire_w(e_retire[0]), .retire_w_ch(e_retire_ch[0]),
    .rd_err(e_rderr[0]), .rd_err_ch(e_rderr_ch[0]));

  sf_dma_engine #(.SRC_STREAM(1'b1), .NCH(NCH), .DW(DW), .AW(AW), .NSO(NSO), .NSI(NSI),
                  .DFIFO_DEPTH(DFIFO_DEPTH), .DESC_DEPTH(DESC_DEPTH),
                  .MAX_BURST_LOG2(MAX_BURST_LOG2)) u_eng1 (
    .clk, .rst_n,
    .elig(e_elig[1]), .ch_err(err_vec), .sch_valid(e_sch[1]), .sch_idx(e_idx[1]),
    .b_src(e_bsrc[1]), .b_dst(e_bdst[1]), .b_nb(e_bnb[1]), .b_rowend(e_browend[1]),
    .b_last(e_blast[1]), .b_dst_str(1'b0), .b_dport(2'd0),
    .b_sport(c_sport[e_idx[1]]), .b_tail(tail_strb(c_len[e_idx[1]])), .idle_rd(e1_idle_unused),
    .rd_req_valid(e1_rd_req_valid_unused), .rd_req_ready(1'b0), .rd_req_addr(e1_rd_req_addr_unused),
    .rd_rsp_valid(1'b0), .rd_rsp_rdata('0), .rd_rsp_err(1'b0),
    .si_valid, .si_ready, .si_data,
    .wr_req_valid(e_wvalid[1]), .wr_req_ready(e_wready[1]), .wr_req_addr(e_waddr[1]),
    .wr_req_wdata(e_wdata[1]), .wr_req_wstrb(e_wstrb[1]), .wr_req_ch(e_wch[1]),
    .wack_space(wa_push_ready),
    .so_valid(e1_so_valid_unused), .so_ready('0), .so_data(e1_so_data_unused),
    .so_strb(e1_so_strb_unused), .so_last(e1_so_last_unused),
    .retire_w(e_retire[1]), .retire_w_ch(e_retire_ch[1]),
    .rd_err(e_rderr[1]), .rd_err_ch(e_rderr_ch[1]));

  assign rd_rsp_ready = 1'b1;     // engine 0 reserves FIFO space per read (credit)

  // ---------------------------------------------------------------- write arbiter
  logic [1:0] wgrant;
  logic       wgidx, wgvalid;
  sf_rr_arbiter #(.N(2)) u_warb (
    .clk, .rst_n, .req({e_wvalid[1], e_wvalid[0]}), .accept(wr_req_ready),
    .grant(wgrant), .grant_idx(wgidx), .grant_valid(wgvalid));

  assign wr_req_valid = wgvalid;
  assign wr_req_addr  = e_waddr[wgidx];
  assign wr_req_wdata = e_wdata[wgidx];
  assign wr_req_wstrb = e_wstrb[wgidx];
  assign e_wready[0]  = wr_req_ready && wgrant[0];
  assign e_wready[1]  = wr_req_ready && wgrant[1];
  wire   wr_fire      = wr_req_valid && wr_req_ready;

  // write-ack tracking FIFO (channel of each outstanding memory write)
  logic           wa_valid;
  logic [CHW-1:0] wa_ch;
  /* verilator lint_off UNUSEDSIGNAL */
  logic [$clog2(WOUT+1)-1:0] wa_cnt_unused;
  /* verilator lint_on UNUSEDSIGNAL */
  sf_fifo #(.WIDTH(CHW), .DEPTH(WOUT)) u_wack (
    .clk, .rst_n,
    .push_valid(wr_fire), .push_ready(wa_push_ready), .push_data(e_wch[wgidx]),
    .pop_valid(wa_valid), .pop_ready(wr_rsp_valid), .pop_data(wa_ch),
    .count(wa_cnt_unused));
  assign wr_rsp_ready = 1'b1;

  wire retire_a    = wr_rsp_valid && wa_valid;
  wire so_fire_any = |(so_valid & so_ready);   // engine 0 stream beat delivered

  // ================================================================ channel state
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      for (int c = 0; c < NCH; c++) begin
        c_irq_en[c]  <= 1'b0;  c_src_str[c] <= 1'b0;  c_dst_str[c] <= 1'b0;
        c_blog2[c]   <= 4'd3;  c_2d[c]      <= 1'b0;  c_sport[c]   <= '0;
        c_dport[c]   <= '0;    c_src[c]     <= '0;    c_dst[c]     <= '0;
        c_len[c]     <= '0;    c_rows[c]    <= 16'd1; c_sstr[c]    <= '0;
        c_dstr[c]    <= '0;    c_beats[c]   <= '0;    c_busy[c]    <= 1'b0;
        c_done[c]    <= 1'b0;  c_err[c]     <= 1'b0;  c_ecode[c]   <= '0;
        w_srow[c]    <= '0;    w_drow[c]    <= '0;    w_bir[c]     <= '0;
        w_rows[c]    <= '0;    w_sdone[c]   <= 1'b1;  w_infl[c]    <= '0;
      end
    end else begin
      for (int c = 0; c < NCH; c++) begin
        logic [IFW-1:0] inc, dec;
        inc = '0;
        dec = '0;

        // -------- scheduling (engine e picked channel c; channels belong
        //          to exactly one engine so at most one fires per cycle)
        for (int e = 0; e < 2; e++) begin
          if (e_sch[e] && e_idx[e] == CHW'(c)) begin
            inc = IFW'(e_bnb[e]);
            if (e_browend[e]) begin
              w_bir[c]  <= '0;
              w_rows[c] <= w_rows[c] - 16'd1;
              w_srow[c] <= w_srow[c] + (c_2d[c] ? c_sstr[c] : '0);
              w_drow[c] <= w_drow[c] + (c_2d[c] ? c_dstr[c] : '0);
              if (e_blast[e]) w_sdone[c] <= 1'b1;
            end else begin
              w_bir[c] <= w_bir[c] + AW'(e_bnb[e]);
            end
          end
        end

        // -------- retirement
        for (int e = 0; e < 2; e++)
          if (e_retire[e] && e_retire_ch[e] == CHW'(c)) dec = dec + IFW'(1);
        if (retire_a && wa_ch == CHW'(c)) dec = dec + IFW'(1);
        w_infl[c] <= w_infl[c] + inc - dec;
        c_beats[c] <= c_beats[c]
                    + 32'(so_fire_any && e_retire_ch[0] == CHW'(c))
                    + 32'(retire_a && wa_ch == CHW'(c) && !wr_rsp_err);

        // -------- errors (first error wins)
        if (c_busy[c] && !c_err[c]) begin
          if ((e_rderr[0] && e_rderr_ch[0] == CHW'(c)) || (e_rderr[1] && e_rderr_ch[1] == CHW'(c))) begin
            c_err[c] <= 1'b1;  c_ecode[c] <= E_RD;  w_sdone[c] <= 1'b1;
          end else if (retire_a && wa_ch == CHW'(c) && wr_rsp_err) begin
            c_err[c] <= 1'b1;  c_ecode[c] <= E_WR;  w_sdone[c] <= 1'b1;
          end
        end

        // -------- completion
        if (c_busy[c] && w_sdone[c] && w_infl[c] == '0 && inc == '0) begin
          c_busy[c] <= 1'b0;
          if (!c_err[c]) c_done[c] <= 1'b1;
        end

        // -------- APB writes
        if (apb_wr && is_ch && wch == CHW'(c)) begin
          case (creg)
            6'h00: begin
              if (!c_busy[c]) begin
                c_irq_en[c]  <= pwdata[1];
                c_src_str[c] <= pwdata[2];
                c_dst_str[c] <= pwdata[3];
                c_blog2[c]   <= pwdata[7:4];
                c_2d[c]      <= pwdata[8];
                c_sport[c]   <= pwdata[13:12];
                c_dport[c]   <= pwdata[17:16];
                if (pwdata[0]) begin
                  c_done[c]  <= 1'b0;
                  c_beats[c] <= '0;
                  if (v_code != 4'd0) begin
                    c_err[c]   <= 1'b1;
                    c_ecode[c] <= v_code;
                  end else begin
                    c_err[c]   <= 1'b0;
                    c_ecode[c] <= '0;
                    c_busy[c]  <= 1'b1;
                    w_srow[c]  <= c_src[c];
                    w_drow[c]  <= c_dst[c];
                    w_bir[c]   <= '0;
                    w_rows[c]  <= (!pwdata[8] || c_rows[c] == 16'd0) ? 16'd1 : c_rows[c];
                    w_sdone[c] <= 1'b0;
                  end
                end
              end else if (pwdata[9] && !c_err[c]) begin
                c_err[c]   <= 1'b1;
                c_ecode[c] <= E_ABORT;
                w_sdone[c] <= 1'b1;
              end
            end
            6'h04: begin
              if (pwdata[1]) c_done[c] <= 1'b0;
              if (pwdata[2] && !c_busy[c]) c_err[c] <= 1'b0;
            end
            6'h08: if (!c_busy[c]) c_src[c]  <= pwdata;
            6'h0C: if (!c_busy[c]) c_dst[c]  <= pwdata;
            6'h10: if (!c_busy[c]) c_len[c]  <= pwdata;
            6'h14: if (!c_busy[c]) c_rows[c] <= pwdata[15:0];
            6'h18: if (!c_busy[c]) c_sstr[c] <= pwdata;
            6'h1C: if (!c_busy[c]) c_dstr[c] <= pwdata;
            default: ;
          endcase
        end
      end
    end
  end

  // ================================================================ readback / irq
  logic [NCH-1:0] irq_pend;
  always_comb begin
    for (int c = 0; c < NCH; c++)
      irq_pend[c] = c_irq_en[c] && (c_done[c] || (c_err[c] && !c_busy[c]));
  end
  assign irq = |irq_pend;

  always_comb begin
    prdata = 32'd0;
    if (apb_rd) begin
      if (paddr == 12'h000)      prdata = 32'h5346_444D;
      else if (paddr == 12'h004) prdata = {8'(NSI), 8'(NSO), 8'(NB), 8'(NCH)};
      else if (paddr == 12'h008) prdata = 32'(irq_pend);
      else if (is_ch) begin
        case (creg)
          6'h00: prdata = {14'd0, c_dport[wch], 2'd0, c_sport[wch], 3'd0, c_2d[wch],
                           c_blog2[wch], c_dst_str[wch], c_src_str[wch], c_irq_en[wch], 1'b0};
          6'h04: prdata = {24'd0, c_ecode[wch], 1'b0, c_err[wch], c_done[wch], c_busy[wch]};
          6'h08: prdata = c_src[wch];
          6'h0C: prdata = c_dst[wch];
          6'h10: prdata = c_len[wch];
          6'h14: prdata = {16'd0, c_rows[wch]};
          6'h18: prdata = c_sstr[wch];
          6'h1C: prdata = c_dstr[wch];
          6'h20: prdata = c_beats[wch];
          default: prdata = 32'd0;
        endcase
      end
    end
  end



endmodule

`default_nettype wire
