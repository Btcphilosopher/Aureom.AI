// =============================================================================
// SilicaFlux DataFabric :: dma_transfer_engine -- simple single-channel engine
//
// Default SilicaFlux-V production candidate: one SFB2 master port, exactly one
// bus transaction in flight, one data register (the write-data register).
//
//   IDLE --start--> VALIDATE --ok--> ISSUE_READ -> WAIT_READ -> ISSUE_WRITE
//        ^             |bad                ^                         |
//        |             v                   +------ WAIT_WRITE <------+
//        +-- ERROR <---+ (+ bus error / abort)        | last beat OK
//        +-- COMPLETE <-------------------------------+
//
// Guarantees (verified: tb/dma, formal/datafabric/fv_dma_engine.sv):
//   * no bus access before validation passes; never more than one request
//     outstanding; request payload registered and stable until accepted;
//   * every accepted request's response is consumed (rsp_ready = 1 in the
//     WAIT states, the only states in which a response can arrive);
//   * a write is issued only with data from an error-free read of the same
//     beat; writes target only [dst, dst+len) and bytes beyond len in the
//     final word are masked by req_wstrb (byte-accurate lengths);
//   * `done` is pulsed only after the LAST write response returned OK, so
//     completion implies that every write has completed;
//   * on a read error no further write is issued; on a write error no further
//     request is issued; bytes_done counts bytes whose writes completed OK,
//     always a contiguous prefix of the transfer;
//   * abort takes effect at the next beat boundary (after the outstanding
//     transaction's response): the engine never withdraws a request.
// Throughput: 4 cycles per beat with single-cycle slaves (2 handshakes x 2).
// =============================================================================
`include "dma_defs.svh"
`default_nettype none

module dma_transfer_engine #(
  parameter int DW           = 32,
  parameter int MAX_LEN_LOG2 = 24,
  localparam int SB          = DW / 8,
  localparam int OFF         = (DW > 8) ? $clog2(DW / 8) : 1
) (
  input  wire logic          clk,
  input  wire logic          rst_n,
  // control
  input  wire logic          start,
  input  wire logic          abort,
  input  wire logic [31:0]   cfg_src,
  input  wire logic [31:0]   cfg_dst,
  input  wire logic [31:0]   cfg_len,
  output logic               busy,
  output logic               done,          // pulse: transfer completed (COMPLETE state)
  output logic               fail,          // pulse: transfer ended with error (ERROR state)
  output logic [3:0]         err_code,      // valid with fail (held until next start)
  output logic [31:0]        err_addr,
  output logic [31:0]        bytes_done,
  output logic [2:0]         state,
  output logic               ev_stall,      // request presented, not accepted
  // SFB2 master port
  output logic               req_valid,
  input  wire logic          req_ready,
  output logic               req_write,
  output logic [31:0]        req_addr,
  output logic [DW-1:0]      req_wdata,
  output logic [SB-1:0]      req_wstrb,
  input  wire logic          rsp_valid,
  output logic               rsp_ready,
  input  wire logic [DW-1:0] rsp_rdata,
  input  wire logic          rsp_error
);
  logic [2:0]  st_q;
  logic [31:0] src_q, dst_q, rem_q;       // current addresses, bytes remaining
  logic        abort_q;
  logic [3:0]  vcode;

  dma_validate #(.DW(DW), .MAX_LEN_LOG2(MAX_LEN_LOG2)) u_val (
    .src(src_q), .dst(dst_q), .len(rem_q), .code(vcode));

  // bytes moved by the current beat and its write strobe
  wire         last_beat = (rem_q <= 32'(SB));
  wire [31:0]  beat_bytes = last_beat ? rem_q : 32'(SB);
  logic [SB-1:0] tail_strb;
  always_comb begin
    tail_strb = '1;
    if (last_beat && rem_q[OFF-1:0] != '0)
      for (int b = 0; b < SB; b++) tail_strb[b] = (32'(b) < rem_q);
  end

  assign state     = st_q;
  assign busy      = (st_q != `DMA_ST_IDLE);
  assign rsp_ready = (st_q == `DMA_ST_WAIT_READ) || (st_q == `DMA_ST_WAIT_WRITE);
  assign ev_stall  = req_valid && !req_ready;
  // decoded from the terminal states: STATUS.DONE/ERROR are set on the same
  // edge on which BUSY falls (software never sees !BUSY && !DONE && !ERROR)
  assign done      = (st_q == `DMA_ST_COMPLETE);
  assign fail      = (st_q == `DMA_ST_ERROR);

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      st_q       <= `DMA_ST_IDLE;
      src_q      <= '0;
      dst_q      <= '0;
      rem_q      <= '0;
      abort_q    <= 1'b0;
      req_valid  <= 1'b0;
      req_write  <= 1'b0;
      req_addr   <= '0;
      req_wstrb  <= '0;
      err_code   <= `DMA_ERR_NONE;
      err_addr   <= '0;
      bytes_done <= '0;
    end else begin
      if (abort && busy) abort_q <= 1'b1;
      case (st_q)
        `DMA_ST_IDLE: begin
          abort_q <= 1'b0;
          if (start) begin
            src_q      <= cfg_src;
            dst_q      <= cfg_dst;
            rem_q      <= cfg_len;
            bytes_done <= '0;
            err_code   <= `DMA_ERR_NONE;
            err_addr   <= '0;
            st_q       <= `DMA_ST_VALIDATE;
          end
        end
        `DMA_ST_VALIDATE: begin
          if (vcode != `DMA_ERR_NONE) begin
            err_code <= vcode;
            st_q     <= `DMA_ST_ERROR;
          end else if (abort_q || abort) begin
            err_code <= `DMA_ERR_ABORTED;
            st_q     <= `DMA_ST_ERROR;
          end else begin
            req_valid <= 1'b1;
            req_write <= 1'b0;
            req_addr  <= src_q;
            req_wstrb <= '1;
            st_q      <= `DMA_ST_ISSUE_READ;
          end
        end
        `DMA_ST_ISSUE_READ: begin
          if (req_ready) begin
            req_valid <= 1'b0;
            st_q      <= `DMA_ST_WAIT_READ;
          end
        end
        `DMA_ST_WAIT_READ: begin
          if (rsp_valid) begin
            if (rsp_error) begin
              err_code <= `DMA_ERR_READ_BUS;
              err_addr <= src_q;
              st_q     <= `DMA_ST_ERROR;
            end else if (abort_q) begin
              err_code <= `DMA_ERR_ABORTED;
              st_q     <= `DMA_ST_ERROR;
            end else begin
              req_valid <= 1'b1;
              req_write <= 1'b1;
              req_addr  <= dst_q;
              req_wstrb <= tail_strb;
              st_q      <= `DMA_ST_ISSUE_WRITE;
            end
          end
        end
        `DMA_ST_ISSUE_WRITE: begin
          if (req_ready) begin
            req_valid <= 1'b0;
            st_q      <= `DMA_ST_WAIT_WRITE;
          end
        end
        `DMA_ST_WAIT_WRITE: begin
          if (rsp_valid) begin
            if (rsp_error) begin
              err_code <= `DMA_ERR_WRITE_BUS;
              err_addr <= dst_q;
              st_q     <= `DMA_ST_ERROR;
            end else begin
              bytes_done <= bytes_done + beat_bytes;
              rem_q      <= rem_q - beat_bytes;
              src_q      <= src_q + 32'(SB);
              dst_q      <= dst_q + 32'(SB);
              if (last_beat) begin
                st_q <= `DMA_ST_COMPLETE;
              end else if (abort_q) begin
                err_code <= `DMA_ERR_ABORTED;
                st_q     <= `DMA_ST_ERROR;
              end else begin
                req_valid <= 1'b1;
                req_write <= 1'b0;
                req_addr  <= src_q + 32'(SB);
                req_wstrb <= '1;
                st_q      <= `DMA_ST_ISSUE_READ;
              end
            end
          end
        end
        `DMA_ST_COMPLETE: st_q <= `DMA_ST_IDLE;
        default:          st_q <= `DMA_ST_IDLE;      // `DMA_ST_ERROR
      endcase
    end
  end

  // write data register: loaded from the read response (datapath, not reset)
  always_ff @(posedge clk) begin
    if (st_q == `DMA_ST_WAIT_READ && rsp_valid && !rsp_error) req_wdata <= rsp_rdata;
  end
endmodule

`default_nettype wire
