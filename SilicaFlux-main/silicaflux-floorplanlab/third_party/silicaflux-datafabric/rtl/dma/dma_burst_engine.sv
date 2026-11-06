// =============================================================================
// SilicaFlux DataFabric :: dma_burst_engine -- buffered / burst DMA engine
// (optional higher-throughput configuration; register-compatible with
// dma_transfer_engine, same validation, same error codes)
//
// Read issuer -> dma_fifo (FIFO_DEPTH beats) -> write issuer.
//   * credit: a read is issued only if a FIFO slot is reserved for its data
//     (reads issued - writes issued < FIFO_DEPTH): a read response can never
//     find the FIFO full, so rsp_ready is constantly 1 (no response stall).
//   * up to MAX_OUT requests outstanding per port; a request may be presented
//     while earlier responses are pending (the SFB2 crossbar accepts it in the
//     cycle the previous response is accepted -> one beat per cycle).
//   * DUAL_PORT = 0: one SFB2 port; READ and WRITE phases of up to BURST
//     requests alternate.  The phase changes only when the port is idle (no
//     request presented, nothing outstanding), so every response belongs to the
//     current phase.  SFB2 has no native bursts: a "burst" is BURST sequential
//     single-beat transactions issued back to back.
//   * DUAL_PORT = 1: port 0 reads, port 1 writes, concurrently (one beat per
//     cycle when source and destination are on different slaves).
// Errors / abort: issue stops (reads after a read error; everything after a
// write error or abort), every outstanding response is drained and consumed,
// then `fail` is pulsed with the first error.  After a read error the beats
// before it are still written (same final memory state as the simple engine).
// bytes_done counts the contiguous prefix of writes acknowledged OK; with
// MAX_OUT > 1 up to MAX_OUT-1 later beats may also have been written when a
// write error occurs (documented in DMA.md).  Never writes outside
// [dst, dst+len).  Completion implies every write response returned OK.
// =============================================================================
`include "dma_defs.svh"
`default_nettype none

module dma_burst_engine #(
  parameter int DW           = 32,
  parameter int MAX_LEN_LOG2 = 24,
  parameter int FIFO_DEPTH   = 8,           // power of two >= 2
  parameter int BURST        = 8,           // 1 .. FIFO_DEPTH (single-port phases)
  parameter int DUAL_PORT    = 0,
  parameter int MAX_OUT      = 2,
  localparam int SB          = DW / 8,
  localparam int OFF         = (DW > 8) ? $clog2(DW / 8) : 1,
  localparam int NP          = (DUAL_PORT != 0) ? 2 : 1,
  localparam int FW          = $clog2(FIFO_DEPTH)
) (
  input  wire logic             clk,
  input  wire logic             rst_n,
  input  wire logic             start,
  input  wire logic             abort,
  input  wire logic [31:0]      cfg_src,
  input  wire logic [31:0]      cfg_dst,
  input  wire logic [31:0]      cfg_len,
  output logic                  busy,
  output logic                  done,
  output logic                  fail,
  output logic [3:0]            err_code,
  output logic [31:0]           err_addr,
  output logic [31:0]           bytes_done,
  output logic [2:0]            state,
  output logic                  ev_stall,
  output logic [7:0]            fifo_level,     // data FIFO occupancy (perf / saturation coverage)
  // SFB2 master port(s): [0] read (or shared), [1] write (DUAL_PORT only)
  output logic [NP-1:0]         req_valid,
  input  wire logic [NP-1:0]    req_ready,
  output logic [NP-1:0]         req_write,
  output logic [NP*32-1:0]      req_addr,
  output logic [NP*DW-1:0]      req_wdata,
  output logic [NP*SB-1:0]      req_wstrb,
  input  wire logic [NP-1:0]    rsp_valid,
  output logic [NP-1:0]         rsp_ready,
  /* verilator lint_off UNUSEDSIGNAL */
  input  wire logic [NP*DW-1:0] rsp_rdata,      // write-port data unused (write responses)
  /* verilator lint_on UNUSEDSIGNAL */
  input  wire logic [NP-1:0]    rsp_error
);
  localparam logic [1:0] S_IDLE = 2'd0, S_VAL = 2'd1, S_RUN = 2'd2, S_END = 2'd3;
  localparam int WP = NP - 1;                       // index of the write port

  logic [1:0]  st_q;
  logic [31:0] src_q, dst_q, len_q, total_q;
  logic [31:0] rd_iss_q, rd_rsp_q, rd_ok_q, wr_iss_q, wr_rsp_q;
  logic [31:0] rd_addr_q, wr_addr_q;
  logic        rd_stop_q, wr_stop_q, abort_q, err_q, werr_q, ph_q;
  logic [31:0] bcnt_q;
  logic [3:0]  vcode;
  logic [FW:0] fcnt;
  logic [DW-1:0] fhead;

  dma_validate #(.DW(DW), .MAX_LEN_LOG2(MAX_LEN_LOG2)) u_val (
    .src(src_q), .dst(dst_q), .len(len_q), .code(vcode));

  // ------------------------------------------------------------ this cycle's events
  wire rd_acc = req_valid[0] && req_ready[0] && !req_write[0];
  wire wr_acc = req_valid[WP] && req_ready[WP] && req_write[WP];
  // responses: dual port -> by port; single port -> by phase (changes only when idle)
  wire rd_rsp = (DUAL_PORT != 0) ? rsp_valid[0] : (rsp_valid[0] && !ph_q);
  wire wr_rsp = (DUAL_PORT != 0) ? rsp_valid[WP] : (rsp_valid[0] && ph_q);
  wire rd_err = rd_rsp && rsp_error[0];
  wire wr_err = wr_rsp && rsp_error[WP];
  wire push   = rd_rsp && !rsp_error[0] && !rd_stop_q;     // data of a good read before any read error
  wire pop    = wr_acc;

  // ------------------------------------------------------------ next-state counters
  wire [31:0] rd_iss_n = rd_iss_q + 32'(rd_acc);
  wire [31:0] rd_rsp_n = rd_rsp_q + 32'(rd_rsp);
  wire [31:0] wr_iss_n = wr_iss_q + 32'(wr_acc);
  wire [31:0] wr_rsp_n = wr_rsp_q + 32'(wr_rsp);
  wire [31:0] rd_ok_n  = rd_ok_q + 32'(push);
  wire [FW:0] fcnt_n   = fcnt + (FW+1)'(push) - (FW+1)'(pop);
  wire        rd_stop_n = rd_stop_q || rd_err || wr_err || abort_q || abort;
  wire        wr_stop_n = wr_stop_q || wr_err || abort_q || abort;
  wire [31:0] wr_limit_n = rd_stop_n ? rd_ok_n : total_q;   // beats that will be written
  wire [31:0] rd_addr_n = rd_addr_q + (rd_acc ? 32'(SB) : 32'd0);
  wire [31:0] wr_addr_n = wr_addr_q + (wr_acc ? 32'(SB) : 32'd0);

  // can a new read / write be presented in the next cycle?
  wire can_rd = (st_q == S_RUN) && !rd_stop_n && (rd_iss_n < total_q) &&
                ((rd_iss_n - wr_iss_n) < 32'(FIFO_DEPTH)) && ((rd_iss_n - rd_rsp_n) < 32'(MAX_OUT));
  wire can_wr = (st_q == S_RUN) && !wr_stop_n && (wr_iss_n < wr_limit_n) && (fcnt_n != '0) &&
                ((wr_iss_n - wr_rsp_n) < 32'(MAX_OUT));
  wire outstanding_n = (rd_iss_n != rd_rsp_n) || (wr_iss_n != wr_rsp_n);
  // single-port phase control
  wire [31:0] bcnt_n = bcnt_q + 32'(rd_acc || wr_acc);
  wire hold0 = req_valid[0] && !req_ready[0];
  wire holdw = req_valid[WP] && !req_ready[WP];

  // tail strobe of the beat a write is presented for
  logic [SB-1:0] tail_strb;
  always_comb begin
    tail_strb = '1;
    if (len_q[OFF-1:0] != '0)
      for (int b = 0; b < SB; b++) tail_strb[b] = (32'(b) < {{(32-OFF){1'b0}}, len_q[OFF-1:0]});
  end
  wire [31:0] last_bytes = (len_q[OFF-1:0] == '0) ? 32'(SB) : {{(32-OFF){1'b0}}, len_q[OFF-1:0]};

  // finished: nothing presented or outstanding, and no further beat can be written
  wire finished = (st_q == S_RUN) && !req_valid[0] && !req_valid[WP] && !outstanding_n &&
                  (wr_stop_n || (wr_iss_n >= wr_limit_n)) && (rd_stop_n || rd_iss_n >= total_q || wr_stop_n);

  dma_fifo #(.WIDTH(DW), .DEPTH(FIFO_DEPTH)) u_fifo (
    .clk, .rst_n, .clr(st_q == S_IDLE), .push, .wdata(rsp_rdata[DW-1:0]), .pop,
    .rdata(fhead), .count(fcnt));

  assign busy      = (st_q != S_IDLE);
  assign fifo_level = 8'(fcnt);
  // terminal-state decode: DONE/ERROR are set on the edge on which BUSY falls
  assign done      = (st_q == S_END) && !err_q;
  assign fail      = (st_q == S_END) && err_q;
  assign rsp_ready = '1;
  assign ev_stall  = |(req_valid & ~req_ready);
  assign state     = (st_q == S_IDLE) ? `DMA_ST_IDLE :
                     (st_q == S_VAL)  ? `DMA_ST_VALIDATE :
                     (st_q == S_END)  ? (err_q ? `DMA_ST_ERROR : `DMA_ST_COMPLETE) :
                     ((DUAL_PORT == 0 && ph_q) ? `DMA_ST_ISSUE_WRITE : `DMA_ST_ISSUE_READ);

  // write data comes straight from the FIFO head (stable until popped)
  always_comb begin
    req_wdata = '0;
    req_wdata[WP*DW +: DW] = fhead;
  end

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      st_q <= S_IDLE;
      src_q <= '0; dst_q <= '0; len_q <= '0; total_q <= '0;
      rd_iss_q <= '0; rd_rsp_q <= '0; rd_ok_q <= '0; wr_iss_q <= '0; wr_rsp_q <= '0;
      rd_addr_q <= '0; wr_addr_q <= '0;
      rd_stop_q <= 1'b0; wr_stop_q <= 1'b0; abort_q <= 1'b0; err_q <= 1'b0; werr_q <= 1'b0; ph_q <= 1'b0;
      bcnt_q <= '0;
      req_valid <= '0; req_write <= '0; req_addr <= '0; req_wstrb <= '0;
      err_code <= `DMA_ERR_NONE; err_addr <= '0; bytes_done <= '0;
    end else begin
      case (st_q)
        S_IDLE: if (start) begin
          src_q <= cfg_src; dst_q <= cfg_dst; len_q <= cfg_len;
          total_q <= 32'(({1'b0, cfg_len} + 33'(SB - 1)) >> OFF);
          rd_iss_q <= '0; rd_rsp_q <= '0; rd_ok_q <= '0; wr_iss_q <= '0; wr_rsp_q <= '0;
          rd_addr_q <= cfg_src; wr_addr_q <= cfg_dst;
          rd_stop_q <= 1'b0; wr_stop_q <= 1'b0; abort_q <= 1'b0; err_q <= 1'b0; werr_q <= 1'b0; ph_q <= 1'b0;
          bcnt_q <= '0; bytes_done <= '0; err_code <= `DMA_ERR_NONE; err_addr <= '0;
          st_q <= S_VAL;
        end
        S_VAL: begin
          if (vcode != `DMA_ERR_NONE) begin
            err_code <= vcode; err_q <= 1'b1; st_q <= S_END;
          end else if (abort) begin
            err_code <= `DMA_ERR_ABORTED; err_q <= 1'b1; st_q <= S_END;
          end else begin
            st_q <= S_RUN;
            // first read is presented in the first RUN cycle
            req_valid[0] <= 1'b1; req_write[0] <= 1'b0; req_addr[31:0] <= src_q; req_wstrb[SB-1:0] <= '1;
          end
        end
        S_RUN: begin
          rd_iss_q <= rd_iss_n; rd_rsp_q <= rd_rsp_n; rd_ok_q <= rd_ok_n;
          wr_iss_q <= wr_iss_n; wr_rsp_q <= wr_rsp_n;
          rd_addr_q <= rd_addr_n; wr_addr_q <= wr_addr_n;
          if (abort) abort_q <= 1'b1;
          // ---- bus-error capture (first error wins)
          if (!err_q) begin
            if (rd_err) begin
              err_q <= 1'b1; err_code <= `DMA_ERR_READ_BUS;
              err_addr <= src_q + (rd_rsp_q << OFF);
            end else if (wr_err) begin
              err_q <= 1'b1; err_code <= `DMA_ERR_WRITE_BUS;
              err_addr <= dst_q + (wr_rsp_q << OFF);
            end
          end
          if (wr_err) werr_q <= 1'b1;
          rd_stop_q <= rd_stop_n;
          wr_stop_q <= wr_stop_n;
          // ---- completed bytes: contiguous prefix of writes acknowledged OK
          // (writes accepted before an abort still count; a write error ends it)
          if (wr_rsp && !rsp_error[WP] && !werr_q)
            bytes_done <= bytes_done + ((wr_rsp_q == total_q - 32'd1) ? last_bytes : 32'(SB));
          // ---- request presentation
          if (DUAL_PORT != 0) begin
            if (!hold0) begin
              req_valid[0] <= can_rd;
              req_write[0] <= 1'b0;
              req_addr[31:0] <= rd_addr_n;
              req_wstrb[SB-1:0] <= '1;
            end
            if (!holdw) begin
              req_valid[WP] <= can_wr;
              req_write[WP] <= 1'b1;
              req_addr[WP*32 +: 32] <= wr_addr_n;
              req_wstrb[WP*SB +: SB] <= (wr_iss_n == total_q - 32'd1) ? tail_strb : '1;
            end
          end else if (!hold0) begin
            bcnt_q <= bcnt_n;
            if (!ph_q && can_rd && bcnt_n < 32'(BURST)) begin
              req_valid[0] <= 1'b1; req_write[0] <= 1'b0;
              req_addr[31:0] <= rd_addr_n; req_wstrb[SB-1:0] <= '1;
            end else if (ph_q && can_wr && bcnt_n < 32'(BURST)) begin
              req_valid[0] <= 1'b1; req_write[0] <= 1'b1;
              req_addr[31:0] <= wr_addr_n;
              req_wstrb[SB-1:0] <= (wr_iss_n == total_q - 32'd1) ? tail_strb : '1;
            end else begin
              req_valid[0] <= 1'b0;
              // switch phase only when the port is idle (all responses back)
              if (!outstanding_n) begin
                ph_q   <= !ph_q;
                bcnt_q <= '0;
              end
            end
          end
          // ---- finish: all writes OK -> DONE (even if an abort raced the last
          // beat, same as dma_transfer_engine); stopped early without a bus
          // error -> ABORTED
          if (finished) begin
            st_q <= S_END;
            if (!err_q && !rd_err && !wr_err && wr_rsp_n != total_q) begin
              err_q <= 1'b1; err_code <= `DMA_ERR_ABORTED;
            end
          end
        end
        default: begin                      // S_END: report (done/fail decoded)
          req_valid <= '0;
          st_q <= S_IDLE;
        end
      endcase
    end
  end
endmodule

`default_nettype wire
