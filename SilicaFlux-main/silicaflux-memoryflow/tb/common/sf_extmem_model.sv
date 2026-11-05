// =============================================================================
// SilicaFlux MemoryFlow :: sf_extmem_model  (BEHAVIOURAL - simulation only)
// External DRAM stand-in behind the SF-MEM read and write channels.
//   * LATENCY       cycles from request acceptance to response
//   * INTERVAL      accept at most one request every INTERVAL cycles per
//                   channel (bandwidth throttle: beats/cycle = 1/INTERVAL)
//   * MAXOUT        outstanding requests per channel
//   * responses in order, byte strobes honoured, out-of-range -> err
// This is NOT a DDR/LPDDR controller model: bank/row timing is modelled
// analytically in memoryflow.models.extmem.  It exists so DMA and system
// testbenches exercise long, variable-latency memory paths.
// =============================================================================
`timescale 1ns/1ps
`default_nettype none

module sf_extmem_model #(
  parameter int DW       = 64,
  parameter int AW       = 32,
  parameter logic [31:0] BASE = 32'h8000_0000,
  parameter int SIZE     = 65536,
  parameter int LATENCY  = 20,
  parameter int INTERVAL = 1,
  parameter int MAXOUT   = 16,
  localparam int NB      = DW / 8
) (
  input  logic          clk,
  input  logic          rst_n,
  input  logic          rd_req_valid,
  output logic          rd_req_ready,
  input  logic [AW-1:0] rd_req_addr,
  output logic          rd_rsp_valid,
  input  logic          rd_rsp_ready,
  output logic [DW-1:0] rd_rsp_rdata,
  output logic          rd_rsp_err,
  input  logic          wr_req_valid,
  output logic          wr_req_ready,
  input  logic [AW-1:0] wr_req_addr,
  input  logic [DW-1:0] wr_req_wdata,
  input  logic [NB-1:0] wr_req_wstrb,
  output logic          wr_rsp_valid,
  input  logic          wr_rsp_ready,
  output logic          wr_rsp_err
);
  logic [7:0] mem [SIZE];

  // pipelines as ring buffers {due, err, data}
  longint cyc = 0;
  always @(posedge clk) cyc <= cyc + 1;

  localparam int QD = 64;
  longint rq_due [QD];  logic rq_err [QD];  logic [DW-1:0] rq_dat [QD];
  int rq_h = 0, rq_t = 0;
  longint wq_due [QD];  logic wq_err [QD];
  int wq_h = 0, wq_t = 0;
  longint rd_last_acc = -1000, wr_last_acc = -1000;

  function automatic bit in_rng(logic [AW-1:0] a);
    return (a >= BASE) && ((a - BASE) <= AW'(SIZE - NB));
  endfunction

  assign rd_req_ready = rst_n && ((rq_t - rq_h) < MAXOUT) && (cyc - rd_last_acc >= INTERVAL);
  assign wr_req_ready = rst_n && ((wq_t - wq_h) < MAXOUT) && (cyc - wr_last_acc >= INTERVAL);
  assign rd_rsp_valid = (rq_t != rq_h) && (rq_due[rq_h % QD] <= cyc);
  assign rd_rsp_rdata = rd_rsp_valid ? rq_dat[rq_h % QD] : '0;
  assign rd_rsp_err   = rd_rsp_valid ? rq_err[rq_h % QD] : 1'b0;
  assign wr_rsp_valid = (wq_t != wq_h) && (wq_due[wq_h % QD] <= cyc);
  assign wr_rsp_err   = wr_rsp_valid ? wq_err[wq_h % QD] : 1'b0;

  // Queue state uses non-blocking updates so the DUT, sampling the same
  // clock edge, always sees pre-edge values (no TB/DUT race).  The byte
  // array is private to this block and the backdoor, so it is updated
  // immediately (read-before-write order within a cycle).
  always @(posedge clk) begin
    if (rst_n) begin
      if (rd_req_valid && rd_req_ready) begin
        logic [DW-1:0] d;
        logic          e;
        e = !in_rng(rd_req_addr);
        d = '0;
        if (!e) for (int b = 0; b < NB; b++) d[b*8 +: 8] = mem[rd_req_addr - BASE + b];
        rq_due[rq_t % QD] <= cyc + LATENCY;
        rq_err[rq_t % QD] <= e;
        rq_dat[rq_t % QD] <= d;
        rq_t        <= rq_t + 1;
        rd_last_acc <= cyc;
      end
      if (rd_rsp_valid && rd_rsp_ready) rq_h <= rq_h + 1;
      if (wr_req_valid && wr_req_ready) begin
        logic e;
        e = !in_rng(wr_req_addr);
        if (!e) for (int b = 0; b < NB; b++)
          if (wr_req_wstrb[b]) mem[wr_req_addr - BASE + b] = wr_req_wdata[b*8 +: 8];
        wq_due[wq_t % QD] <= cyc + LATENCY;
        wq_err[wq_t % QD] <= e;
        wq_t        <= wq_t + 1;
        wr_last_acc <= cyc;
      end
      if (wr_rsp_valid && wr_rsp_ready) wq_h <= wq_h + 1;
    end
  end

  // backdoor access for testbenches
  function automatic void bd_write(int off, logic [7:0] v);
    mem[off] = v;
  endfunction
  function automatic logic [7:0] bd_read(int off);
    return mem[off];
  endfunction

endmodule

`default_nettype wire
