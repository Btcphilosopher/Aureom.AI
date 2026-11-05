// =============================================================================
// Shared harness for sf_memflow_top system testbenches (simulation only).
// Instantiates the DUT, the external-memory model, and APB / host tasks.
// Every DUT input is driven from exactly one process (the main thread for
// APB + host port; the ext model for its own outputs).
// Requires: localparam VEC_IN_FIFO_P defined by the including module.
// =============================================================================
  localparam int DW = 64, NB = 8, AW = 32;
  localparam int SPM_NBANKS = 4, SPM_BD = 1024;
  localparam int SPM_BYTES = SPM_NBANKS * SPM_BD * NB;          // 32 KiB
  localparam logic [31:0] EXT_BASE = 32'h8000_0000;
  localparam int EXT_BYTES = 65536;
  localparam logic [12:0] DMA = 13'h0000, CTL = 13'h1000;

  logic clk = 0, rst_n = 0;
  always #5 clk = ~clk;
  longint cyc = 0;
  always @(posedge clk) cyc <= cyc + 1;

  logic        psel, penable, pwrite, pready, pslverr, irq;
  logic [12:0] paddr;
  logic [31:0] pwdata, prdata;
  logic          h_req_valid, h_req_ready, h_req_we, h_rsp_valid, h_rsp_err;
  logic [AW-1:0] h_req_addr;
  logic [DW-1:0] h_req_wdata, h_rsp_rdata;
  logic [NB-1:0] h_req_wstrb;
  logic          xr_req_valid, xr_req_ready, xr_rsp_valid, xr_rsp_ready, xr_rsp_err;
  logic [AW-1:0] xr_req_addr;
  logic [DW-1:0] xr_rsp_rdata;
  logic          xw_req_valid, xw_req_ready, xw_rsp_valid, xw_rsp_ready, xw_rsp_err;
  logic [AW-1:0] xw_req_addr;
  logic [DW-1:0] xw_req_wdata;
  logic [NB-1:0] xw_req_wstrb;

  sf_memflow_top #(.SPM_NBANKS(SPM_NBANKS), .SPM_BANK_DEPTH(SPM_BD),
                   .VEC_IN_FIFO(VEC_IN_FIFO_P)) u_top (
    .clk, .rst_n, .psel, .penable, .pwrite, .paddr, .pwdata, .prdata, .pready, .pslverr, .irq,
    .h_req_valid, .h_req_ready, .h_req_we, .h_req_addr, .h_req_wdata, .h_req_wstrb,
    .h_rsp_valid, .h_rsp_ready(1'b1), .h_rsp_rdata, .h_rsp_err,
    .xr_req_valid, .xr_req_ready, .xr_req_addr, .xr_rsp_valid, .xr_rsp_ready, .xr_rsp_rdata, .xr_rsp_err,
    .xw_req_valid, .xw_req_ready, .xw_req_addr, .xw_req_wdata, .xw_req_wstrb,
    .xw_rsp_valid, .xw_rsp_ready, .xw_rsp_err);

  sf_extmem_model #(.BASE(EXT_BASE), .SIZE(EXT_BYTES), .LATENCY(24), .INTERVAL(1), .MAXOUT(16)) u_ext (
    .clk, .rst_n,
    .rd_req_valid(xr_req_valid), .rd_req_ready(xr_req_ready), .rd_req_addr(xr_req_addr),
    .rd_rsp_valid(xr_rsp_valid), .rd_rsp_ready(xr_rsp_ready), .rd_rsp_rdata(xr_rsp_rdata), .rd_rsp_err(xr_rsp_err),
    .wr_req_valid(xw_req_valid), .wr_req_ready(xw_req_ready), .wr_req_addr(xw_req_addr),
    .wr_req_wdata(xw_req_wdata), .wr_req_wstrb(xw_req_wstrb),
    .wr_rsp_valid(xw_rsp_valid), .wr_rsp_ready(xw_rsp_ready), .wr_rsp_err(xw_rsp_err));

  task automatic apb_write(input logic [12:0] a, input logic [31:0] d);
    psel = 1; penable = 0; pwrite = 1; paddr = a; pwdata = d;
    @(negedge clk); penable = 1;
    @(negedge clk); psel = 0; penable = 0; pwrite = 0;
  endtask

  task automatic apb_read(input logic [12:0] a, output logic [31:0] d);
    psel = 1; penable = 0; pwrite = 0; paddr = a;
    @(negedge clk); penable = 1;
    #1 d = prdata;
    @(negedge clk); psel = 0; penable = 0;
  endtask

  function automatic logic [12:0] creg(int ch, int off);
    return DMA + 13'(12'h100 + ch * 12'h40 + off);
  endfunction

  task automatic host_op(input bit we, input int a, input logic [DW-1:0] d, input logic [NB-1:0] s,
                         output logic [DW-1:0] q, output logic err);
    bit acc;
    h_req_valid = 1; h_req_we = we; h_req_addr = AW'(a); h_req_wdata = d; h_req_wstrb = s;
    acc = 0;
    while (!acc) begin
      #1 acc = h_req_ready;
      @(negedge clk);
    end
    h_req_valid = 0;
    while (!h_rsp_valid) @(negedge clk);
    q = h_rsp_rdata;
    err = h_rsp_err;
    @(negedge clk);
  endtask

  task automatic host_write64(input int a, input logic [DW-1:0] d);
    logic [DW-1:0] q; logic e;
    host_op(1, a, d, '1, q, e);
  endtask

  task automatic host_read64(input int a, output logic [DW-1:0] q);
    logic e;
    host_op(0, a, '0, '0, q, e);
  endtask

  localparam logic [31:0] C_START = 32'h1, C_IRQ = 32'h2, C_SSTR = 32'h4, C_DSTR = 32'h8;
  function automatic logic [31:0] c_burst(int l2); return 32'(l2) << 4; endfunction
  function automatic logic [31:0] c_sport(int p);  return 32'(p) << 12; endfunction
  function automatic logic [31:0] c_dport(int p);  return 32'(p) << 16; endfunction

  task automatic dma_setup(int ch, logic [31:0] src, logic [31:0] dst, logic [31:0] len);
    apb_write(creg(ch, 8'h08), src);
    apb_write(creg(ch, 8'h0C), dst);
    apb_write(creg(ch, 8'h10), len);
    apb_write(creg(ch, 8'h14), 32'd1);
  endtask

  task automatic dma_wait(int ch, output logic [31:0] st, input int max_polls = 100000);
    int n;
    n = 0;
    do begin apb_read(creg(ch, 8'h04), st); n++; end while (st[0] && n < max_polls);
  endtask
