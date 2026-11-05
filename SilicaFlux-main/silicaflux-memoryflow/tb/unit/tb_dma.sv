// =============================================================================
// tb_dma :: DMA engine verification in a realistic harness
//   sf_dma (4 ch) -> read/write routers -> SPM (16 KiB, 3 ports) + EXT model
//   stream sinks on so[0..3] (random ready), stream sources on si[0..1]
// Tests
//   T1  ID / CAPS / reset values
//   T2  SPM->SPM 1-D, byte-granular lengths (1,7,8,9,64,1000,4096), tails
//   T3  EXT->SPM, SPM->EXT, EXT->EXT
//   T4  2-D tile extraction (strided rows)
//   T5  start-time validation errors: zero length, misaligned, overflow (1-D, 2-D)
//   T6  bus errors: read from hole, write to hole, read crossing SPM end
//   T7  abort of a long transfer
//   T8  MEM->STREAM (SRAM->accelerator) with backpressure, strobes, last
//   T9  STREAM->MEM (accelerator->SRAM) with bursty source
//   T10 four concurrent channels, mixed bursts
//   T11 burst-length sweep (RTL-measured efficiency)
//   T12 IRQ set/clear, busy register lock, start-while-busy ignored
// =============================================================================
`timescale 1ns/1ps
`default_nettype none
`include "tb_common.svh"

module tb_dma;
  localparam int DW = 64, NB = 8, AW = 32, NCH = 4;
  localparam int SPM_NBANKS = 4, SPM_BD = 512;
  localparam int SPM_BYTES = SPM_NBANKS * SPM_BD * NB;         // 16 KiB
  localparam logic [31:0] EXT_BASE = 32'h8000_0000;
  localparam int EXT_BYTES = 65536;
  localparam logic [63:0] BASES = {EXT_BASE, 32'h0};
  localparam logic [63:0] SIZES = {32'(EXT_BYTES), 32'(SPM_BYTES)};

  logic clk = 0, rst_n = 0;
  always #5 clk = ~clk;
  longint cyc = 0;
  always @(posedge clk) cyc <= cyc + 1;

  // ---------------------------------------------------------------- APB
  logic        psel, penable, pwrite, pready, pslverr, irq;
  logic [11:0] paddr;
  logic [31:0] pwdata, prdata;

  // ---------------------------------------------------------------- DMA ports
  logic          rd_req_valid, rd_req_ready, rd_rsp_valid, rd_rsp_ready, rd_rsp_err;
  logic [AW-1:0] rd_req_addr;
  logic [DW-1:0] rd_rsp_rdata;
  logic          wr_req_valid, wr_req_ready, wr_rsp_valid, wr_rsp_ready, wr_rsp_err;
  logic [AW-1:0] wr_req_addr;
  logic [DW-1:0] wr_req_wdata, wr_rsp_rdata_unused;
  logic [NB-1:0] wr_req_wstrb;
  logic [3:0]    so_valid, so_ready;
  logic [DW-1:0] so_data;
  logic [NB-1:0] so_strb;
  logic          so_last;
  logic [1:0]    si_valid, si_ready;
  logic [2*DW-1:0] si_data;

  sf_dma #(.NCH(NCH), .DW(DW), .AW(AW), .NSO(4), .NSI(2)) dut (
    .clk, .rst_n, .psel, .penable, .pwrite, .paddr, .pwdata, .prdata, .pready, .pslverr, .irq,
    .rd_req_valid, .rd_req_ready, .rd_req_addr, .rd_rsp_valid, .rd_rsp_ready, .rd_rsp_rdata, .rd_rsp_err,
    .wr_req_valid, .wr_req_ready, .wr_req_addr, .wr_req_wdata, .wr_req_wstrb,
    .wr_rsp_valid, .wr_rsp_ready, .wr_rsp_err,
    .so_valid, .so_ready, .so_data, .so_strb, .so_last, .si_valid, .si_ready, .si_data);

  // ---------------------------------------------------------------- routers
  logic [1:0]      r_sv, r_sr, r_swe, r_rv, r_rr, r_re;
  logic [2*AW-1:0] r_sa;
  logic [2*DW-1:0] r_swd, r_rd;
  logic [2*NB-1:0] r_sst;
  logic [1:0]      w_sv, w_sr, w_swe, w_rv, w_rr, w_re;
  logic [2*AW-1:0] w_sa;
  logic [2*DW-1:0] w_swd, w_rd;
  logic [2*NB-1:0] w_sst;

  sf_mem_router #(.NS(2), .AW(AW), .DW(DW), .MAXOUT(16), .BASES(BASES), .SIZES(SIZES)) u_rr (
    .clk, .rst_n, .req_valid(rd_req_valid), .req_ready(rd_req_ready), .req_we(1'b0),
    .req_addr(rd_req_addr), .req_wdata('0), .req_wstrb('0),
    .rsp_valid(rd_rsp_valid), .rsp_ready(rd_rsp_ready), .rsp_rdata(rd_rsp_rdata), .rsp_err(rd_rsp_err),
    .s_req_valid(r_sv), .s_req_ready(r_sr), .s_req_we(r_swe), .s_req_addr(r_sa),
    .s_req_wdata(r_swd), .s_req_wstrb(r_sst),
    .s_rsp_valid(r_rv), .s_rsp_ready(r_rr), .s_rsp_rdata(r_rd), .s_rsp_err(r_re));
  sf_mem_router #(.NS(2), .AW(AW), .DW(DW), .MAXOUT(8), .BASES(BASES), .SIZES(SIZES)) u_wr (
    .clk, .rst_n, .req_valid(wr_req_valid), .req_ready(wr_req_ready), .req_we(1'b1),
    .req_addr(wr_req_addr), .req_wdata(wr_req_wdata), .req_wstrb(wr_req_wstrb),
    .rsp_valid(wr_rsp_valid), .rsp_ready(wr_rsp_ready), .rsp_rdata(wr_rsp_rdata_unused), .rsp_err(wr_rsp_err),
    .s_req_valid(w_sv), .s_req_ready(w_sr), .s_req_we(w_swe), .s_req_addr(w_sa),
    .s_req_wdata(w_swd), .s_req_wstrb(w_sst),
    .s_rsp_valid(w_rv), .s_rsp_ready(w_rr), .s_rsp_rdata(w_rd), .s_rsp_err(w_re));

  // ---------------------------------------------------------------- SPM (port2 = TB host)
  logic          h_req_valid, h_req_ready, h_req_we, h_rsp_valid, h_rsp_err;
  logic [AW-1:0] h_req_addr;
  logic [DW-1:0] h_req_wdata, h_rsp_rdata;
  logic [NB-1:0] h_req_wstrb;
  logic [2:0]    sp_rv, sp_re, sp_rc, sp_qr;
  logic [3*DW-1:0] sp_rd;
  logic [15:0]   c_corr, c_unc;
  logic [31:0]   c_conf, c_stall;
  logic          mb1, mb2, mb3;
  logic [3:0]    mb4;
  logic [8:0]    mb5;

  sf_spm_banked #(.NPORTS(3), .NBANKS(SPM_NBANKS), .DW(DW), .BANK_DEPTH(SPM_BD), .AW(AW)) u_spm (
    .clk, .rst_n,
    .req_valid({h_req_valid, w_sv[0], r_sv[0]}), .req_ready(sp_qr),
    .req_we({h_req_we, 1'b1, 1'b0}),
    .req_addr({h_req_addr, w_sa[0 +: AW], r_sa[0 +: AW]}),
    .req_wdata({h_req_wdata, w_swd[0 +: DW], 64'h0}),
    .req_wstrb({h_req_wstrb, w_sst[0 +: NB], 8'h0}),
    .rsp_valid(sp_rv), .rsp_ready({1'b1, w_rr[0], r_rr[0]}), .rsp_rdata(sp_rd),
    .rsp_err(sp_re), .rsp_corr(sp_rc),
    .inj_en(1'b0), .inj_bank('0), .inj_mask('0), .cnt_corr(c_corr), .cnt_uncorr(c_unc),
    .mbist_start(1'b0), .mbist_bg('0), .mbist_busy(mb1), .mbist_done(mb2), .mbist_fail(mb3),
    .mbist_fail_bank(mb4), .mbist_fail_addr(mb5),
    .cnt_conflict_cycles(c_conf), .cnt_stall_cycles(c_stall), .lp_sleep(1'b0));
  assign r_sr[0] = sp_qr[0];  assign r_rv[0] = sp_rv[0];  assign r_rd[0 +: DW] = sp_rd[0 +: DW];
  assign r_re[0] = sp_re[0];
  assign w_sr[0] = sp_qr[1];  assign w_rv[0] = sp_rv[1];  assign w_re[0] = sp_re[1];
  assign w_rd = '0;
  assign h_req_ready = sp_qr[2]; assign h_rsp_valid = sp_rv[2];
  assign h_rsp_rdata = sp_rd[2*DW +: DW]; assign h_rsp_err = sp_re[2];

  // ---------------------------------------------------------------- EXT model
  int ext_interval = 1;
  sf_extmem_model #(.BASE(32'h0), .SIZE(EXT_BYTES), .LATENCY(20), .INTERVAL(1), .MAXOUT(16)) u_ext (
    .clk, .rst_n,
    .rd_req_valid(r_sv[1]), .rd_req_ready(r_sr[1]), .rd_req_addr(r_sa[AW +: AW]),
    .rd_rsp_valid(r_rv[1]), .rd_rsp_ready(r_rr[1]), .rd_rsp_rdata(r_rd[DW +: DW]), .rd_rsp_err(r_re[1]),
    .wr_req_valid(w_sv[1]), .wr_req_ready(w_sr[1]), .wr_req_addr(w_sa[AW +: AW]),
    .wr_req_wdata(w_swd[DW +: DW]), .wr_req_wstrb(w_sst[NB +: NB]),
    .wr_rsp_valid(w_rv[1]), .wr_rsp_ready(w_rr[1]), .wr_rsp_err(w_re[1]));

  // ---------------------------------------------------------------- reference memories
  logic [7:0] spm_ref [SPM_BYTES];
  logic [7:0] ext_ref [EXT_BYTES];

  // ---------------------------------------------------------------- stream sinks
  int so_ready_pct = 70;
  localparam int SQ = 4096;
  logic [DW+NB:0] sink [4][SQ];    // {last, strb, data}
  int sink_n [4];

  always @(negedge clk) for (int p = 0; p < 4; p++) so_ready[p] = ($urandom_range(0, 99) < so_ready_pct);
  always @(posedge clk) begin
    for (int p = 0; p < 4; p++) begin
      if (rst_n && so_valid[p] && so_ready[p]) begin
        sink[p][sink_n[p] % SQ] = {so_last, so_strb, so_data};
        sink_n[p] = sink_n[p] + 1;
      end
    end
    `CHECK($countones(so_valid) <= 1, "at most one stream output active")
  end

  // ---------------------------------------------------------------- stream sources
  logic [DW-1:0] src_mem [2][SQ];
  int src_n [2];
  int src_i [2];
  int si_valid_pct = 60;
  always @(negedge clk) begin
    for (int q = 0; q < 2; q++) begin
      si_valid[q] = (src_i[q] < src_n[q]) && ($urandom_range(0, 99) < si_valid_pct);
      si_data[q*DW +: DW] = src_mem[q][src_i[q] % SQ];
    end
  end
  always @(posedge clk) for (int q = 0; q < 2; q++) if (rst_n && si_valid[q] && si_ready[q]) src_i[q] = src_i[q] + 1;

  // ---------------------------------------------------------------- APB tasks
  task automatic apb_write(input logic [11:0] a, input logic [31:0] d);
    psel = 1; penable = 0; pwrite = 1; paddr = a; pwdata = d;
    @(negedge clk); penable = 1;
    @(negedge clk); psel = 0; penable = 0; pwrite = 0;
  endtask

  task automatic apb_read(input logic [11:0] a, output logic [31:0] d);
    psel = 1; penable = 0; pwrite = 0; paddr = a;
    @(negedge clk); penable = 1;
    #1 d = prdata;
    @(negedge clk); psel = 0; penable = 0;
  endtask

  function automatic logic [11:0] creg(int ch, int off);
    return 12'(12'h100 + ch * 12'h40 + off);
  endfunction

  // ---------------------------------------------------------------- host SPM access
  // Host accesses are issued one at a time and wait for their response.
  task automatic host_op(input bit we, input int a, input logic [DW-1:0] d, input logic [NB-1:0] s,
                         output logic [DW-1:0] q);
    bit acc;
    h_req_valid = 1; h_req_we = we; h_req_addr = AW'(a); h_req_wdata = d; h_req_wstrb = s;
    acc = 0;
    while (!acc) begin
      #1 acc = h_req_ready;
      @(negedge clk);
    end
    h_req_valid = 0;
    while (!h_rsp_valid) @(negedge clk);   // response consumed at next posedge (ready=1)
    q = h_rsp_rdata;
    @(negedge clk);
  endtask

  task automatic spm_fill_random();
    logic [DW-1:0] d, q;
    for (int w = 0; w < SPM_BYTES / NB; w++) begin
      d = {$urandom(), $urandom()};
      for (int b = 0; b < NB; b++) spm_ref[w * NB + b] = d[b*8 +: 8];
      host_op(1, w * NB, d, '1, q);
    end
  endtask

  task automatic spm_check(input int lo, input int hi, input string tag);
    logic [DW-1:0] q;
    int bad;
    bad = 0;
    for (int w = lo / NB; w < (hi + NB - 1) / NB; w++) begin
      host_op(0, w * NB, '0, '0, q);
      for (int b = 0; b < NB; b++) if (q[b*8 +: 8] !== spm_ref[w * NB + b]) bad++;
    end
    `CHECK(bad == 0, $sformatf("%s: SPM bytes [%0d,%0d) match reference (%0d bad)", tag, lo, hi, bad))
  endtask

  task automatic ext_fill_random();
    for (int i = 0; i < EXT_BYTES; i++) begin
      ext_ref[i] = 8'($urandom());
      u_ext.bd_write(i, ext_ref[i]);
    end
  endtask

  task automatic ext_check(input int lo, input int hi, input string tag);
    int bad;
    bad = 0;
    for (int i = lo; i < hi; i++) if (u_ext.bd_read(i) !== ext_ref[i]) bad++;
    `CHECK(bad == 0, $sformatf("%s: EXT bytes [%0d,%0d) match reference (%0d bad)", tag, lo, hi, bad))
  endtask

  // reference copy on byte arrays (golden: memoryflow.verify.golden.dma_copy)
  function automatic logic [7:0] rd_ref(longint a);
    if (a >= EXT_BASE) return ext_ref[a - EXT_BASE];
    return spm_ref[a];
  endfunction
  function automatic void wr_ref(longint a, logic [7:0] v);
    if (a >= EXT_BASE) ext_ref[a - EXT_BASE] = v; else spm_ref[a] = v;
  endfunction
  function automatic void ref_copy(longint src, longint dst, int len, int rows, int ss, int ds);
    logic [7:0] tmp [];
    tmp = new[len * rows];
    for (int r = 0; r < rows; r++) for (int i = 0; i < len; i++) tmp[r * len + i] = rd_ref(src + r * ss + i);
    for (int r = 0; r < rows; r++) for (int i = 0; i < len; i++) wr_ref(dst + r * ds + i, tmp[r * len + i]);
  endfunction

  // ---------------------------------------------------------------- DMA helpers
  localparam logic [31:0] C_START = 32'h1, C_IRQ = 32'h2, C_SSTR = 32'h4, C_DSTR = 32'h8, C_2D = 32'h100;
  function automatic logic [31:0] c_burst(int l2); return 32'(l2) << 4; endfunction
  function automatic logic [31:0] c_sport(int p);  return 32'(p) << 12; endfunction
  function automatic logic [31:0] c_dport(int p);  return 32'(p) << 16; endfunction

  task automatic dma_prog(int ch, logic [31:0] src, logic [31:0] dst, logic [31:0] len,
                         logic [31:0] rows = 1, logic [31:0] ss = 0, logic [31:0] ds = 0);
    apb_write(creg(ch, 8'h08), src);
    apb_write(creg(ch, 8'h0C), dst);
    apb_write(creg(ch, 8'h10), len);
    apb_write(creg(ch, 8'h14), rows);
    apb_write(creg(ch, 8'h18), ss);
    apb_write(creg(ch, 8'h1C), ds);
  endtask

  task automatic wait_idle(int ch, output logic [31:0] st, input int timeout = 200000);
    int n;
    n = 0;
    do begin
      apb_read(creg(ch, 8'h04), st);
      n++;
    end while (st[0] && n < timeout);
    `CHECK(!st[0], $sformatf("ch%0d completes (no hang)", ch))
  endtask

  task automatic run_copy(int ch, logic [31:0] src, logic [31:0] dst, int len, int bl2,
                          int rows = 1, int ss = 0, int ds = 0, input string tag = "copy");
    logic [31:0] st;
    dma_prog(ch, src, dst, len, rows, ss, ds);
    apb_write(creg(ch, 0), C_START | c_burst(bl2) | ((rows > 1) ? C_2D : 0));
    wait_idle(ch, st);
    `CHECK_EQ(st[2:0], 3'b010, $sformatf("%s: DONE, no ERR", tag))
    ref_copy(src, dst, len, rows, ss, ds);
  endtask

  task automatic expect_err(int ch, logic [31:0] ctrl, logic [3:0] code, input string tag);
    logic [31:0] st;
    apb_write(creg(ch, 0), ctrl);
    wait_idle(ch, st);
    `CHECK_EQ(st[7:4], code, $sformatf("%s: error code", tag))
    `CHECK_EQ(st[2:0], 3'b100, $sformatf("%s: ERR set, DONE clear, idle", tag))
    apb_write(creg(ch, 8'h04), 32'h6);   // W1C
  endtask

  // ---------------------------------------------------------------- main
  logic [31:0] rd32;
  longint t0;

  initial begin
    psel = 0; penable = 0; pwrite = 0; paddr = '0; pwdata = '0;
    h_req_valid = 0; h_req_we = 0; h_req_addr = '0; h_req_wdata = '0; h_req_wstrb = '0;
    for (int p = 0; p < 4; p++) sink_n[p] = 0;
    for (int q = 0; q < 2; q++) begin src_n[q] = 0; src_i[q] = 0; end
    ext_fill_random();
    repeat (3) @(negedge clk);
    rst_n = 1;
    @(negedge clk);

    // ---------------- T1
    apb_read(12'h000, rd32);  `CHECK_EQ(rd32, 32'h5346_444D, "T1 ID")
    apb_read(12'h004, rd32);  `CHECK_EQ(rd32, 32'h0204_0804, "T1 CAPS {NSI,NSO,8B,NCH}")
    apb_read(creg(1, 4), rd32); `CHECK_EQ(rd32, 32'h0, "T1 STATUS reset")
    apb_read(creg(3, 0), rd32); `CHECK_EQ(rd32, 32'h30, "T1 CTRL reset (burst log2 = 3)")

    spm_fill_random();

    // ---------------- T2: SPM->SPM 1-D, byte-granular
    begin
      int lens [7] = '{1, 7, 8, 9, 64, 1000, 4096};
      for (int i = 0; i < 7; i++) begin
        run_copy(i % NCH, 32'h0000 + 32'(i * 8), 32'h2000 + 32'(i * 16), lens[i], i % 5,
                 1, 0, 0, $sformatf("T2 len=%0d", lens[i]));
        spm_check(32'h2000 + i * 16 - 16, 32'h2000 + i * 16 + lens[i] + 24, $sformatf("T2 len=%0d", lens[i]));
      end
    end

    // ---------------- T3: EXT<->SPM, EXT->EXT
    run_copy(0, EXT_BASE + 32'h100, 32'h1000, 2048, 4, 1, 0, 0, "T3 EXT->SPM");
    spm_check(32'h0F00, 32'h1900, "T3 EXT->SPM");
    run_copy(1, 32'h0800, EXT_BASE + 32'h4000, 2048 + 5, 3, 1, 0, 0, "T3 SPM->EXT");
    ext_check(32'h3F00, 32'h4900, "T3 SPM->EXT");
    run_copy(2, EXT_BASE + 32'h0, EXT_BASE + 32'h8000, 1536, 2, 1, 0, 0, "T3 EXT->EXT");
    ext_check(32'h7F00, 32'h8700, "T3 EXT->EXT");

    // ---------------- T4: 2-D tile (8 rows x 24 B from a 256 B-pitch matrix)
    run_copy(3, 32'h0100, 32'h3000, 24, 4, 8, 256, 24, "T4 2-D tile SPM->SPM");
    spm_check(32'h2FF0, 32'h3100, "T4 2-D");
    run_copy(0, EXT_BASE + 32'h200, 32'h3200, 40, 1, 12, 512, 64, "T4 2-D tile EXT->SPM");
    spm_check(32'h3200, 32'h3200 + 12 * 64, "T4 2-D EXT");

    // ---------------- T5: validation errors (no data must move)
    dma_prog(0, 32'h0, 32'h3800, 0);
    expect_err(0, C_START, 4'd1, "T5 zero length");
    dma_prog(0, 32'h4, 32'h3800, 64);
    expect_err(0, C_START, 4'd2, "T5 misaligned src");
    dma_prog(0, 32'h0, 32'h3803, 64);
    expect_err(0, C_START, 4'd2, "T5 misaligned dst");
    dma_prog(0, 32'h0, 32'h3800, 64, 4, 12, 64);
    expect_err(0, C_START | C_2D, 4'd2, "T5 misaligned 2-D stride");
    dma_prog(0, 32'hFFFF_FF00, 32'h3800, 32'h200);
    expect_err(0, C_START, 4'd3, "T5 1-D 32-bit address overflow");
    // (rows-1)*stride = 0xFFFE * 0x10_0000 = 0xF_FFE0_0000 : needs > 32-bit product
    dma_prog(0, 32'h0, 32'h3800, 64, 32'hFFFF, 32'h0010_0000, 64);
    expect_err(0, C_START | C_2D, 4'd3, "T5 2-D footprint overflow (rows*stride > 2^32)");
    // just inside the 32-bit space: must NOT be flagged as overflow (it will
    // later fault on the unmapped hole instead -> RD_BUS, data from row 0 moves)
    dma_prog(0, 32'h0, 32'h3800, 64, 32'h8000, 32'h0001_0000, 64);
    expect_err(0, C_START | C_2D, 4'd4, "T5 large 2-D footprint inside 4 GiB is legal (faults later)");
    ref_copy(32'h0, 32'h3800, 64, 1, 0, 0);
    dma_prog(0, 32'h0, 32'hFFFF_FFF8, 16);
    expect_err(0, C_START, 4'd3, "T5 dst overflow at top of address space");
    // stream endpoints are exempt from alignment/overflow checks
    spm_check(32'h3800, 32'h3900, "T5 nothing written");

    // ---------------- T6: bus errors
    dma_prog(1, 32'h4000_0000, 32'h3800, 128);
    expect_err(1, C_START | c_burst(2), 4'd4, "T6 read from unmapped hole");
    spm_check(32'h3800, 32'h3900, "T6 read-error wrote nothing");
    dma_prog(1, 32'h0, 32'h5000_0000, 128);
    expect_err(1, C_START | c_burst(2), 4'd5, "T6 write to unmapped hole");
    // read crossing the SPM end: first beats valid, then decode errors
    dma_prog(2, 32'(SPM_BYTES - 32), 32'h3800, 128);
    expect_err(2, C_START | c_burst(0), 4'd4, "T6 read crossing SPM boundary");

    // ---------------- T7: abort a long EXT->SPM transfer
    dma_prog(3, EXT_BASE, 32'h0, 16384);
    apb_write(creg(3, 0), C_START | c_burst(4));
    repeat (40) @(negedge clk);
    apb_write(creg(3, 0), 32'h200);        // ABORT
    begin
      logic [31:0] st;
      wait_idle(3, st);
      `CHECK_EQ(st[7:4], 4'd6, "T7 abort error code")
      `CHECK(st[2] && !st[1], "T7 aborted channel: ERR, not DONE")
      apb_read(creg(3, 8'h20), rd32);
      `CHECK(rd32 < 32'd2048, $sformatf("T7 abort stopped early (%0d of 2048 beats)", rd32))
      apb_write(creg(3, 4), 32'h6);
      // SPM now partially overwritten: resync reference by reading back
      for (int w = 0; w < SPM_BYTES / NB; w++) begin
        logic [DW-1:0] q;
        host_op(0, w * NB, '0, '0, q);
        for (int b = 0; b < NB; b++) spm_ref[w * NB + b] = q[b*8 +: 8];
      end
    end

    // ---------------- T8: SPM -> stream port 2 (1000 B, tail strobe)
    begin
      logic [31:0] st;
      int n0, nbeats;
      so_ready_pct = 55;
      n0 = sink_n[2];
      dma_prog(0, 32'h0400, 32'h0, 1000);
      apb_write(creg(0, 0), C_START | C_DSTR | c_dport(2) | c_burst(3));
      wait_idle(0, st);
      `CHECK_EQ(st[2:0], 3'b010, "T8 mem->stream DONE")
      nbeats = sink_n[2] - n0;
      `CHECK_EQ(nbeats, 125, "T8 beat count")
      for (int i = 0; i < nbeats; i++) begin
        logic [DW+NB:0] e;
        logic [DW-1:0]  expd;
        e = sink[2][(n0 + i) % SQ];
        for (int b = 0; b < NB; b++) expd[b*8 +: 8] = spm_ref[32'h400 + i * 8 + b];
        `CHECK_EQ(e[DW-1:0], expd, "T8 stream data")
        `CHECK_EQ(e[DW+NB], (i == nbeats - 1), "T8 last only on final beat")
        `CHECK_EQ(e[DW +: NB], 8'hFF, "T8 strobe all ones (1000 = 125*8)")
      end
      // 13-byte transfer: tail strobe 0x1F on the second beat
      n0 = sink_n[1];
      dma_prog(1, 32'h0408, 32'h0, 13);
      apb_write(creg(1, 0), C_START | C_DSTR | c_dport(1));
      wait_idle(1, st);
      `CHECK_EQ(sink_n[1] - n0, 2, "T8 13 B -> 2 beats")
      `CHECK_EQ(sink[1][(n0 + 1) % SQ][DW +: NB], 8'h1F, "T8 tail strobe")
      `CHECK_EQ(sink[1][(n0 + 1) % SQ][DW + NB], 1'b1, "T8 tail beat carries last")
      so_ready_pct = 70;
    end

    // ---------------- T9: stream port 1 -> SPM (accelerator -> SRAM)
    begin
      logic [31:0] st;
      src_n[1] = 0; src_i[1] = 0;
      for (int i = 0; i < 64; i++) src_mem[1][i] = {$urandom(), $urandom()};
      src_n[1] = 64;
      dma_prog(2, 32'h0, 32'h3A00, 507);                   // 63.375 beats -> 64 beats, tail
      apb_write(creg(2, 0), C_START | C_SSTR | c_sport(1) | c_burst(4));
      wait_idle(2, st);
      `CHECK_EQ(st[2:0], 3'b010, "T9 stream->mem DONE")
      `CHECK_EQ(src_i[1], 64, "T9 consumed exactly 64 source beats")
      for (int i = 0; i < 507; i++) spm_ref[32'h3A00 + i] = src_mem[1][i / 8][(i % 8) * 8 +: 8];
      spm_check(32'h3A00, 32'h3A00 + 512 + 8, "T9 stream->mem incl. untouched tail bytes");
    end

    // ---------------- T10: four concurrent channels
    begin
      logic [31:0] st;
      src_n[0] = 0; src_i[0] = 0;
      for (int i = 0; i < 96; i++) src_mem[0][i] = {$urandom(), $urandom()};
      src_n[0] = 96;
      dma_prog(0, EXT_BASE + 32'h1000, 32'h0000, 1024);
      dma_prog(1, 32'h1000, EXT_BASE + 32'hC000, 1024);
      dma_prog(2, 32'h0, 32'h2000, 768);
      dma_prog(3, 32'h1800, 32'h0, 512);
      t0 = cyc;
      apb_write(creg(0, 0), C_START | c_burst(4));
      apb_write(creg(1, 0), C_START | c_burst(2));
      apb_write(creg(2, 0), C_START | C_SSTR | c_sport(0) | c_burst(3));
      apb_write(creg(3, 0), C_START | C_DSTR | c_dport(3) | c_burst(1));
      for (int ch = 0; ch < 4; ch++) begin
        wait_idle(ch, st);
        `CHECK_EQ(st[2:0], 3'b010, $sformatf("T10 ch%0d DONE", ch))
      end
      tb_metric("dma_4ch_concurrent_cycles", real'(cyc - t0));
      ref_copy(EXT_BASE + 32'h1000, 32'h0000, 1024, 1, 0, 0);
      ref_copy(32'h1000, EXT_BASE + 32'hC000, 1024, 1, 0, 0);
      for (int i = 0; i < 768; i++) spm_ref[32'h2000 + i] = src_mem[0][i / 8][(i % 8) * 8 +: 8];
      spm_check(32'h0000, 32'h0400, "T10 ch0 EXT->SPM");
      ext_check(32'hC000, 32'hC400, "T10 ch1 SPM->EXT");
      spm_check(32'h2000, 32'h2300, "T10 ch2 stream->SPM");
    end

    // ---------------- T11: burst-length sweep (RTL-measured)
    so_ready_pct = 100;
    for (int bl = 0; bl <= 4; bl++) begin
      logic [31:0] st;
      dma_prog(0, EXT_BASE, 32'h0, 4096);
      t0 = cyc;
      apb_write(creg(0, 0), C_START | c_burst(bl));
      wait_idle(0, st);
      tb_metric($sformatf("dma_ext2spm_4k_burst%0d_cycles", 1 << bl), real'(cyc - t0));
      ref_copy(EXT_BASE, 32'h0, 4096, 1, 0, 0);
      dma_prog(1, 32'h0, 32'h2000, 4096);
      t0 = cyc;
      apb_write(creg(1, 0), C_START | c_burst(bl));
      wait_idle(1, st);
      tb_metric($sformatf("dma_spm2spm_4k_burst%0d_cycles", 1 << bl), real'(cyc - t0));
      ref_copy(32'h0, 32'h2000, 4096, 1, 0, 0);
      // same copy with the destination skewed by one beat (bank-conflict probe)
      dma_prog(1, 32'h0, 32'h2008, 4096);
      t0 = cyc;
      apb_write(creg(1, 0), C_START | c_burst(bl));
      wait_idle(1, st);
      tb_metric($sformatf("dma_spm2spm_4k_burst%0d_skew1_cycles", 1 << bl), real'(cyc - t0));
      ref_copy(32'h0, 32'h2008, 4096, 1, 0, 0);
    end
    spm_check(32'h0, 32'h3000, "T11 final contents");

    // ---------------- T12: IRQ, register lock, start-while-busy
    begin
      logic [31:0] st;
      `CHECK(!irq, "T12 irq low before")
      dma_prog(2, 32'h0, 32'h2800, 64);
      apb_write(creg(2, 0), C_START | C_IRQ);
      wait_idle(2, st);
      repeat (2) @(negedge clk);
      `CHECK(irq, "T12 irq asserted on DONE")
      apb_read(12'h008, rd32);
      `CHECK_EQ(rd32, 32'h4, "T12 IRQ_STATUS bit 2")
      apb_write(creg(2, 4), 32'h2);
      @(negedge clk);
      `CHECK(!irq, "T12 irq cleared by W1C DONE")
      ref_copy(32'h0, 32'h2800, 64, 1, 0, 0);
      // error interrupt
      dma_prog(2, 32'h0, 32'h2800, 0);
      apb_write(creg(2, 0), C_START | C_IRQ);
      @(negedge clk);
      `CHECK(irq, "T12 irq on validation error")
      apb_write(creg(2, 4), 32'h4);
      @(negedge clk);
      `CHECK(!irq, "T12 irq cleared by W1C ERR")
      // lock while busy
      dma_prog(3, EXT_BASE, 32'h0, 8192);
      apb_write(creg(3, 0), C_START | c_burst(0));
      apb_write(creg(3, 8'h08), 32'h1234_5678);      // must be ignored
      apb_write(creg(3, 0), C_START);                // start-while-busy ignored
      apb_read(creg(3, 8'h08), rd32);
      `CHECK_EQ(rd32, EXT_BASE, "T12 SRC locked while busy")
      wait_idle(3, st);
      `CHECK_EQ(st[2:0], 3'b010, "T12 locked channel completes normally")
      apb_read(creg(3, 8'h20), rd32);
      `CHECK_EQ(rd32, 32'd1024, "T12 BEATS counter = 8192/8")
      ref_copy(EXT_BASE, 32'h0, 8192, 1, 0, 0);
      spm_check(32'h0, 32'h2000, "T12 data");
      apb_read(12'h300, rd32);   // unmapped -> pslverr (not checked by data)
    end
    tb_finish();
  end

  initial begin
    #400ms;
    $display("TIMEOUT");
    tb_finish();
  end
endmodule

`default_nettype wire
