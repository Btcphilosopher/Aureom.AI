// =============================================================================
// tb_router :: sf_mem_router ordering and decode verification
//   Two slaves with very different latency (2 vs 25 cycles) and bandwidth,
//   one write router + one read router sharing the slaves.  Random traffic
//   to both windows and to unmapped space with random response backpressure:
//   every response must arrive IN ORDER with correct data / decode errors.
// =============================================================================
`timescale 1ns/1ps
`default_nettype none
`include "tb_common.svh"

module tb_router;
  localparam int AW = 32, DW = 64, NB = 8, WIN = 4096;
  localparam logic [63:0] BASES = {32'h8000_0000, 32'h0000_0000};
  localparam logic [63:0] SIZES = {32'(WIN), 32'(WIN)};

  logic clk = 0, rst_n = 0;
  always #5 clk = ~clk;

  // master (read router)
  logic          m_req_valid, m_req_ready, m_rsp_valid, m_rsp_ready, m_rsp_err;
  logic [AW-1:0] m_req_addr;
  logic [DW-1:0] m_rsp_rdata;
  // master (write router)
  logic          w_req_valid, w_req_ready, w_rsp_valid, w_rsp_ready, w_rsp_err;
  logic [AW-1:0] w_req_addr;
  logic [DW-1:0] w_req_wdata, w_rsp_rdata_unused;
  logic [NB-1:0] w_req_wstrb;

  logic [1:0]      rs_req_valid, rs_req_ready, rs_req_we, rs_rsp_valid, rs_rsp_ready, rs_rsp_err;
  logic [2*AW-1:0] rs_req_addr;
  logic [2*DW-1:0] rs_req_wdata, rs_rsp_rdata;
  logic [2*NB-1:0] rs_req_wstrb;
  logic [1:0]      ws_req_valid, ws_req_ready, ws_req_we, ws_rsp_valid, ws_rsp_ready, ws_rsp_err;
  logic [2*AW-1:0] ws_req_addr;
  logic [2*DW-1:0] ws_req_wdata, ws_rsp_rdata;
  logic [2*NB-1:0] ws_req_wstrb;

  sf_mem_router #(.NS(2), .AW(AW), .DW(DW), .MAXOUT(8), .BASES(BASES), .SIZES(SIZES)) u_rd (
    .clk, .rst_n, .req_valid(m_req_valid), .req_ready(m_req_ready), .req_we(1'b0),
    .req_addr(m_req_addr), .req_wdata('0), .req_wstrb('0),
    .rsp_valid(m_rsp_valid), .rsp_ready(m_rsp_ready), .rsp_rdata(m_rsp_rdata), .rsp_err(m_rsp_err),
    .s_req_valid(rs_req_valid), .s_req_ready(rs_req_ready), .s_req_we(rs_req_we),
    .s_req_addr(rs_req_addr), .s_req_wdata(rs_req_wdata), .s_req_wstrb(rs_req_wstrb),
    .s_rsp_valid(rs_rsp_valid), .s_rsp_ready(rs_rsp_ready), .s_rsp_rdata(rs_rsp_rdata),
    .s_rsp_err(rs_rsp_err));

  sf_mem_router #(.NS(2), .AW(AW), .DW(DW), .MAXOUT(8), .BASES(BASES), .SIZES(SIZES)) u_wr (
    .clk, .rst_n, .req_valid(w_req_valid), .req_ready(w_req_ready), .req_we(1'b1),
    .req_addr(w_req_addr), .req_wdata(w_req_wdata), .req_wstrb(w_req_wstrb),
    .rsp_valid(w_rsp_valid), .rsp_ready(w_rsp_ready), .rsp_rdata(w_rsp_rdata_unused), .rsp_err(w_rsp_err),
    .s_req_valid(ws_req_valid), .s_req_ready(ws_req_ready), .s_req_we(ws_req_we),
    .s_req_addr(ws_req_addr), .s_req_wdata(ws_req_wdata), .s_req_wstrb(ws_req_wstrb),
    .s_rsp_valid(ws_rsp_valid), .s_rsp_ready(ws_rsp_ready), .s_rsp_rdata(ws_rsp_rdata),
    .s_rsp_err(ws_rsp_err));
  assign ws_rsp_rdata = '0;

  // slave 0: fast; slave 1: slow + throttled (both see window offsets)
  sf_extmem_model #(.BASE(32'h0), .SIZE(WIN), .LATENCY(2), .INTERVAL(1), .MAXOUT(4)) u_s0 (
    .clk, .rst_n,
    .rd_req_valid(rs_req_valid[0]), .rd_req_ready(rs_req_ready[0]), .rd_req_addr(rs_req_addr[0 +: AW]),
    .rd_rsp_valid(rs_rsp_valid[0]), .rd_rsp_ready(rs_rsp_ready[0]), .rd_rsp_rdata(rs_rsp_rdata[0 +: DW]),
    .rd_rsp_err(rs_rsp_err[0]),
    .wr_req_valid(ws_req_valid[0]), .wr_req_ready(ws_req_ready[0]), .wr_req_addr(ws_req_addr[0 +: AW]),
    .wr_req_wdata(ws_req_wdata[0 +: DW]), .wr_req_wstrb(ws_req_wstrb[0 +: NB]),
    .wr_rsp_valid(ws_rsp_valid[0]), .wr_rsp_ready(ws_rsp_ready[0]), .wr_rsp_err(ws_rsp_err[0]));
  sf_extmem_model #(.BASE(32'h0), .SIZE(WIN), .LATENCY(25), .INTERVAL(3), .MAXOUT(8)) u_s1 (
    .clk, .rst_n,
    .rd_req_valid(rs_req_valid[1]), .rd_req_ready(rs_req_ready[1]), .rd_req_addr(rs_req_addr[AW +: AW]),
    .rd_rsp_valid(rs_rsp_valid[1]), .rd_rsp_ready(rs_rsp_ready[1]), .rd_rsp_rdata(rs_rsp_rdata[DW +: DW]),
    .rd_rsp_err(rs_rsp_err[1]),
    .wr_req_valid(ws_req_valid[1]), .wr_req_ready(ws_req_ready[1]), .wr_req_addr(ws_req_addr[AW +: AW]),
    .wr_req_wdata(ws_req_wdata[DW +: DW]), .wr_req_wstrb(ws_req_wstrb[DW/8 +: NB]),
    .wr_rsp_valid(ws_rsp_valid[1]), .wr_rsp_ready(ws_rsp_ready[1]), .wr_rsp_err(ws_rsp_err[1]));

  // reference
  logic [7:0] refm [2][WIN];
  typedef struct packed { logic err; logic [DW-1:0] d; } e_t;
  e_t rq [8192];  int rh = 0, rt = 0;
  e_t wq [8192];  int wh = 0, wt = 0;

  function automatic int decode(logic [AW-1:0] a, output int off);
    off = 0;
    if (a < WIN) begin off = int'(a); return 0; end
    if (a >= 32'h8000_0000 && a < 32'h8000_0000 + WIN) begin off = int'(a - 32'h8000_0000); return 1; end
    return -1;
  endfunction

  function automatic logic [AW-1:0] rnd_addr();
    int k;
    k = $urandom_range(0, 9);
    if (k < 4) return AW'($urandom_range(0, WIN / 8 - 1) * 8);
    if (k < 8) return 32'h8000_0000 + AW'($urandom_range(0, WIN / 8 - 1) * 8);
    if (k == 8) return 32'h0000_2000 + AW'($urandom_range(0, 255) * 8);   // hole
    return 32'hFFFF_FFF8;                                               // top of space
  endfunction

  always @(negedge clk) begin
    m_rsp_ready = ($urandom_range(0, 2) != 0);
    w_rsp_ready = ($urandom_range(0, 3) != 0);
  end

  always @(posedge clk) begin
    if (rst_n && m_rsp_valid && m_rsp_ready) begin
      `CHECK(rh < rt, "read response expected")
      `CHECK_EQ(m_rsp_err, rq[rh % 8192].err, "read decode-error flag in order")
      if (!rq[rh % 8192].err) `CHECK_EQ(m_rsp_rdata, rq[rh % 8192].d, "read data in order")
      rh = rh + 1;
    end
    if (rst_n && w_rsp_valid && w_rsp_ready) begin
      `CHECK(wh < wt, "write ack expected")
      `CHECK_EQ(w_rsp_err, wq[wh % 8192].err, "write decode-error flag in order")
      wh = wh + 1;
    end
  end

  task automatic do_write(logic [AW-1:0] a, logic [DW-1:0] d, logic [NB-1:0] s);
    bit acc;
    w_req_valid = 1; w_req_addr = a; w_req_wdata = d; w_req_wstrb = s;
    acc = 0;
    while (!acc) begin
      #1 acc = w_req_ready;
      if (acc) begin
        int off, sl;
        sl = decode(a, off);
        wq[wt % 8192] = '{err: (sl < 0), d: '0};
        wt++;
        if (sl >= 0) for (int b = 0; b < NB; b++) if (s[b]) refm[sl][off + b] = d[b*8 +: 8];
      end
      @(negedge clk);
    end
    w_req_valid = 0;
  endtask

  task automatic do_read(logic [AW-1:0] a);
    bit acc;
    m_req_valid = 1; m_req_addr = a;
    acc = 0;
    while (!acc) begin
      #1 acc = m_req_ready;
      if (acc) begin
        int off, sl;
        logic [DW-1:0] d;
        sl = decode(a, off);
        d = '0;
        if (sl >= 0) for (int b = 0; b < NB; b++) d[b*8 +: 8] = refm[sl][off + b];
        rq[rt % 8192] = '{err: (sl < 0), d: d};
        rt++;
      end
      @(negedge clk);
    end
    m_req_valid = 0;
  endtask

  initial begin
    m_req_valid = 0; w_req_valid = 0; m_req_addr = '0; w_req_addr = '0; w_req_wdata = '0; w_req_wstrb = '0;
    for (int s = 0; s < 2; s++) for (int i = 0; i < WIN; i++) begin
      refm[s][i] = 8'($urandom());
      if (s == 0) u_s0.bd_write(i, refm[s][i]); else u_s1.bd_write(i, refm[s][i]);
    end
    repeat (3) @(negedge clk);
    rst_n = 1;
    @(negedge clk);
    // phase 1: writes (random strobes) to both windows and holes
    for (int n = 0; n < 1500; n++) do_write(rnd_addr(), {$urandom(), $urandom()}, NB'($urandom()));
    while (wh != wt) @(negedge clk);
    // phase 2: reads (data must reflect writes), in order across slaves
    for (int n = 0; n < 4000; n++) do_read(rnd_addr());
    while (rh != rt) @(negedge clk);
    tb_metric("router_reads", real'(rt));
    tb_metric("router_writes", real'(wt));
    tb_finish();
  end

  initial begin
    #20ms;
    $display("TIMEOUT");
    tb_finish();
  end
endmodule

`default_nettype wire
