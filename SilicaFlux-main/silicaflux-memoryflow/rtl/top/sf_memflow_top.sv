// =============================================================================
// SilicaFlux MemoryFlow :: sf_memflow_top
// Memory subsystem + accelerator dataflow integration for SilicaFlux-V.
//
//            APB (CPU)                     host TCM port (CPU)
//               |                                  |
//     +---------+---------+                        |
//     | 0x0xxx  DMA regs  | 0x1xxx ctrl regs       |
//     v                   v                        v
//  +------+  rd  +--------+--------------+  +---------------------------+
//  | DMA  |----->| router | SPM 0x0      |->| SPM port0 (DMA read)      |
//  |      |      |        | EXT 0x8000_0 |  | SPM port1 (DMA write)     |
//  |      |  wr  +--------+--------------+  | SPM port2 (host / CPU)    |
//  |      |----->| router | SPM | EXT    |->|  NBANKS x sf_sram_bank    |
//  |      |      +--------+--------------+  |  ECC, MBIST, interleave   |
//  |      |  so0/so1 --> sf_vec_unit A/B    +---------------------------+
//  |      |  so2 ------> sf_tensor_array A
//  |      |  so3 -> sf_reuse_buffer -> sf_tensor_array B
//  |      |  si0 <---- vec result,  si1 <---- tensor result
//  +------+                ext_rd / ext_wr  --> DDR/LPDDR controller (external)
//
// Classification: SYNTHESIZABLE (integration)
// =============================================================================
`default_nettype none

module sf_memflow_top #(
  parameter int DW             = 64,
  parameter int AW             = 32,
  parameter int SPM_NBANKS     = 4,
  parameter int SPM_BANK_DEPTH = 1024,
  parameter int SPM_ECC        = 2,
  parameter int SPM_INTERLEAVE = 0,
  parameter int SPM_RSP_DEPTH  = 4,
  parameter int SPM_IMPL       = 0,
  parameter int DMA_NCH        = 4,
  parameter int DMA_DFIFO      = 16,
  parameter int DMA_MAXBURST   = 4,
  parameter int VEC_EW         = 16,
  parameter int VEC_IN_FIFO    = 16,
  parameter int TEN_TR         = 8,
  parameter int TEN_TC         = 8,
  parameter bit TEN_ACC_DBUF   = 1'b1,
  parameter int TEN_IN_FIFO    = 16,
  parameter int REUSE_DEPTH    = 64,
  parameter logic [31:0] EXT_BASE = 32'h8000_0000,
  parameter logic [31:0] EXT_SIZE = 32'h8000_0000,
  // test-only SPM stuck-at fault
  parameter bit SA_EN   = 1'b0,
  parameter int SA_BANK = 0,
  parameter int SA_ADDR = 0,
  parameter int SA_BIT  = 0,
  parameter bit SA_VAL  = 1'b0,
  localparam int NB     = DW / 8,
  localparam int SPM_BYTES = SPM_NBANKS * SPM_BANK_DEPTH * NB,
  localparam int R      = $clog2(DW + 1 + $clog2(DW + 1)),
  localparam int SW     = (SPM_ECC == 2) ? (DW + R + 1) : (SPM_ECC == 1) ? (NB * 9) : DW,
  localparam int IDXW   = $clog2(SPM_BANK_DEPTH)
) (
  input  logic          clk,
  input  logic          rst_n,
  // APB3
  input  logic          psel,
  input  logic          penable,
  input  logic          pwrite,
  input  logic [12:0]   paddr,
  input  logic [31:0]   pwdata,
  output logic [31:0]   prdata,
  output logic          pready,
  output logic          pslverr,
  output logic          irq,
  // host (CPU) tightly-coupled SPM port
  input  logic          h_req_valid,
  output logic          h_req_ready,
  input  logic          h_req_we,
  input  logic [AW-1:0] h_req_addr,
  input  logic [DW-1:0] h_req_wdata,
  input  logic [NB-1:0] h_req_wstrb,
  output logic          h_rsp_valid,
  input  logic          h_rsp_ready,
  output logic [DW-1:0] h_rsp_rdata,
  output logic          h_rsp_err,
  // external memory (to DDR/LPDDR controller) -- read path
  output logic          xr_req_valid,
  input  logic          xr_req_ready,
  output logic [AW-1:0] xr_req_addr,
  input  logic          xr_rsp_valid,
  output logic          xr_rsp_ready,
  input  logic [DW-1:0] xr_rsp_rdata,
  input  logic          xr_rsp_err,
  // external memory -- write path
  output logic          xw_req_valid,
  input  logic          xw_req_ready,
  output logic [AW-1:0] xw_req_addr,
  output logic [DW-1:0] xw_req_wdata,
  output logic [NB-1:0] xw_req_wstrb,
  input  logic          xw_rsp_valid,
  output logic          xw_rsp_ready,
  input  logic          xw_rsp_err
);
  // ================================================================ APB split
  wire sel_dma  = psel && !paddr[12];
  wire sel_ctrl = psel &&  paddr[12];
  logic [31:0] dma_prdata, ctl_prdata;
  logic        dma_pready, ctl_pready, dma_pslverr, ctl_pslverr;

  assign prdata  = paddr[12] ? ctl_prdata  : dma_prdata;
  assign pready  = paddr[12] ? ctl_pready  : dma_pready;
  assign pslverr = paddr[12] ? ctl_pslverr : dma_pslverr;

  // ================================================================ DMA
  logic          d_rd_req_valid, d_rd_req_ready, d_rd_rsp_valid, d_rd_rsp_ready, d_rd_rsp_err;
  logic [AW-1:0] d_rd_req_addr;
  logic [DW-1:0] d_rd_rsp_rdata;
  logic          d_wr_req_valid, d_wr_req_ready, d_wr_rsp_valid, d_wr_rsp_ready, d_wr_rsp_err;
  logic [AW-1:0] d_wr_req_addr;
  logic [DW-1:0] d_wr_req_wdata;
  logic [NB-1:0] d_wr_req_wstrb;
  logic [DW-1:0] d_wr_rsp_rdata_unused;
  logic [3:0]    so_valid, so_ready;
  logic [DW-1:0] so_data;
  logic [NB-1:0] so_strb;
  logic          so_last;
  logic [1:0]    si_valid, si_ready;
  logic [2*DW-1:0] si_data;

  sf_dma #(.NCH(DMA_NCH), .DW(DW), .AW(AW), .NSO(4), .NSI(2),
           .DFIFO_DEPTH(DMA_DFIFO), .MAX_BURST_LOG2(DMA_MAXBURST)) u_dma (
    .clk, .rst_n,
    .psel(sel_dma), .penable, .pwrite, .paddr(paddr[11:0]), .pwdata,
    .prdata(dma_prdata), .pready(dma_pready), .pslverr(dma_pslverr), .irq,
    .rd_req_valid(d_rd_req_valid), .rd_req_ready(d_rd_req_ready), .rd_req_addr(d_rd_req_addr),
    .rd_rsp_valid(d_rd_rsp_valid), .rd_rsp_ready(d_rd_rsp_ready),
    .rd_rsp_rdata(d_rd_rsp_rdata), .rd_rsp_err(d_rd_rsp_err),
    .wr_req_valid(d_wr_req_valid), .wr_req_ready(d_wr_req_ready), .wr_req_addr(d_wr_req_addr),
    .wr_req_wdata(d_wr_req_wdata), .wr_req_wstrb(d_wr_req_wstrb),
    .wr_rsp_valid(d_wr_rsp_valid), .wr_rsp_ready(d_wr_rsp_ready), .wr_rsp_err(d_wr_rsp_err),
    .so_valid, .so_ready, .so_data, .so_strb, .so_last,
    .si_valid, .si_ready, .si_data
  );

  // ================================================================ routers
  localparam logic [2*AW-1:0] RBASES = {EXT_BASE, 32'h0};
  localparam logic [2*AW-1:0] RSIZES = {EXT_SIZE, 32'(SPM_BYTES)};

  // SPM port signals (3 ports: 0 DMA rd, 1 DMA wr, 2 host)
  logic [2:0]      sp_req_valid, sp_req_ready, sp_req_we, sp_rsp_valid, sp_rsp_ready,
                   sp_rsp_err, sp_rsp_corr;
  logic [3*AW-1:0] sp_req_addr;
  logic [3*DW-1:0] sp_req_wdata, sp_rsp_rdata;
  logic [3*NB-1:0] sp_req_wstrb;

  // read router
  logic [1:0]      rr_req_valid, rr_req_ready, rr_req_we, rr_rsp_valid, rr_rsp_ready, rr_rsp_err;
  logic [2*AW-1:0] rr_req_addr;
  logic [2*DW-1:0] rr_req_wdata, rr_rsp_rdata;
  logic [2*NB-1:0] rr_req_wstrb;

  sf_mem_router #(.NS(2), .AW(AW), .DW(DW), .MAXOUT(DMA_DFIFO), .BASES(RBASES), .SIZES(RSIZES)) u_rrt (
    .clk, .rst_n,
    .req_valid(d_rd_req_valid), .req_ready(d_rd_req_ready), .req_we(1'b0),
    .req_addr(d_rd_req_addr), .req_wdata('0), .req_wstrb('0),
    .rsp_valid(d_rd_rsp_valid), .rsp_ready(d_rd_rsp_ready),
    .rsp_rdata(d_rd_rsp_rdata), .rsp_err(d_rd_rsp_err),
    .s_req_valid(rr_req_valid), .s_req_ready(rr_req_ready), .s_req_we(rr_req_we),
    .s_req_addr(rr_req_addr), .s_req_wdata(rr_req_wdata), .s_req_wstrb(rr_req_wstrb),
    .s_rsp_valid(rr_rsp_valid), .s_rsp_ready(rr_rsp_ready),
    .s_rsp_rdata(rr_rsp_rdata), .s_rsp_err(rr_rsp_err)
  );

  // write router
  logic [1:0]      wr_req_valid, wr_req_ready, wr_req_we, wr_rsp_valid, wr_rsp_ready, wr_rsp_err;
  logic [2*AW-1:0] wr_req_addr;
  logic [2*DW-1:0] wr_req_wdata, wr_rsp_rdata;
  logic [2*NB-1:0] wr_req_wstrb;

  sf_mem_router #(.NS(2), .AW(AW), .DW(DW), .MAXOUT(8), .BASES(RBASES), .SIZES(RSIZES)) u_wrt (
    .clk, .rst_n,
    .req_valid(d_wr_req_valid), .req_ready(d_wr_req_ready), .req_we(1'b1),
    .req_addr(d_wr_req_addr), .req_wdata(d_wr_req_wdata), .req_wstrb(d_wr_req_wstrb),
    .rsp_valid(d_wr_rsp_valid), .rsp_ready(d_wr_rsp_ready),
    .rsp_rdata(d_wr_rsp_rdata_unused), .rsp_err(d_wr_rsp_err),
    .s_req_valid(wr_req_valid), .s_req_ready(wr_req_ready), .s_req_we(wr_req_we),
    .s_req_addr(wr_req_addr), .s_req_wdata(wr_req_wdata), .s_req_wstrb(wr_req_wstrb),
    .s_rsp_valid(wr_rsp_valid), .s_rsp_ready(wr_rsp_ready),
    .s_rsp_rdata(wr_rsp_rdata), .s_rsp_err(wr_rsp_err)
  );

  // SPM port wiring
  assign sp_req_valid = {h_req_valid, wr_req_valid[0], rr_req_valid[0]};
  assign sp_req_we    = {h_req_we,    1'b1,            1'b0};
  assign sp_req_addr  = {h_req_addr,  wr_req_addr[AW-1:0], rr_req_addr[AW-1:0]};
  assign sp_req_wdata = {h_req_wdata, wr_req_wdata[DW-1:0], {DW{1'b0}}};
  assign sp_req_wstrb = {h_req_wstrb, wr_req_wstrb[NB-1:0], {NB{1'b0}}};
  assign sp_rsp_ready = {h_rsp_ready, wr_rsp_ready[0], rr_rsp_ready[0]};
  assign h_req_ready  = sp_req_ready[2];
  assign h_rsp_valid  = sp_rsp_valid[2];
  assign h_rsp_rdata  = sp_rsp_rdata[2*DW +: DW];
  assign h_rsp_err    = sp_rsp_err[2];

  assign rr_req_ready[0]       = sp_req_ready[0];
  assign rr_rsp_valid[0]       = sp_rsp_valid[0];
  assign rr_rsp_rdata[DW-1:0]  = sp_rsp_rdata[DW-1:0];
  assign rr_rsp_err[0]         = sp_rsp_err[0];
  assign wr_req_ready[0]       = sp_req_ready[1];
  assign wr_rsp_valid[0]       = sp_rsp_valid[1];
  assign wr_rsp_rdata[DW-1:0]  = sp_rsp_rdata[DW +: DW];
  assign wr_rsp_err[0]         = sp_rsp_err[1];

  // external memory wiring (slave 1 of each router)
  assign xr_req_valid           = rr_req_valid[1];
  assign rr_req_ready[1]        = xr_req_ready;
  assign xr_req_addr            = rr_req_addr[AW +: AW] + EXT_BASE;   // restore absolute
  assign rr_rsp_valid[1]        = xr_rsp_valid;
  assign xr_rsp_ready           = rr_rsp_ready[1];
  assign rr_rsp_rdata[DW +: DW] = xr_rsp_rdata;
  assign rr_rsp_err[1]          = xr_rsp_err;

  assign xw_req_valid           = wr_req_valid[1];
  assign wr_req_ready[1]        = xw_req_ready;
  assign xw_req_addr            = wr_req_addr[AW +: AW] + EXT_BASE;
  assign xw_req_wdata           = wr_req_wdata[DW +: DW];
  assign xw_req_wstrb           = wr_req_wstrb[NB +: NB];
  assign wr_rsp_valid[1]        = xw_rsp_valid;
  assign xw_rsp_ready           = wr_rsp_ready[1];
  assign wr_rsp_rdata[DW +: DW] = '0;
  assign wr_rsp_err[1]          = xw_rsp_err;

  // ================================================================ SPM
  logic              inj_en, mbist_start, mbist_busy, mbist_done, mbist_fail, lp_sleep;
  logic [$clog2(SPM_NBANKS)-1:0] inj_bank;
  logic [SW-1:0]     inj_mask, mbist_bg;
  logic [SPM_NBANKS-1:0] mbist_fail_bank;
  logic [IDXW-1:0]   mbist_fail_addr;
  logic [15:0]       cnt_corr, cnt_uncorr;
  logic [31:0]       cnt_conflict, cnt_stall;

  sf_spm_banked #(
    .NPORTS(3), .NBANKS(SPM_NBANKS), .DW(DW), .BANK_DEPTH(SPM_BANK_DEPTH), .AW(AW),
    .ECC_MODE(SPM_ECC), .INTERLEAVE(SPM_INTERLEAVE), .RSP_DEPTH(SPM_RSP_DEPTH),
    .IMPL(SPM_IMPL), .SA_EN(SA_EN), .SA_BANK(SA_BANK), .SA_ADDR(SA_ADDR),
    .SA_BIT(SA_BIT), .SA_VAL(SA_VAL)
  ) u_spm (
    .clk, .rst_n,
    .req_valid(sp_req_valid), .req_ready(sp_req_ready), .req_we(sp_req_we),
    .req_addr(sp_req_addr), .req_wdata(sp_req_wdata), .req_wstrb(sp_req_wstrb),
    .rsp_valid(sp_rsp_valid), .rsp_ready(sp_rsp_ready), .rsp_rdata(sp_rsp_rdata),
    .rsp_err(sp_rsp_err), .rsp_corr(sp_rsp_corr),
    .inj_en, .inj_bank, .inj_mask, .cnt_corr, .cnt_uncorr,
    .mbist_start, .mbist_bg, .mbist_busy, .mbist_done, .mbist_fail,
    .mbist_fail_bank, .mbist_fail_addr,
    .cnt_conflict_cycles(cnt_conflict), .cnt_stall_cycles(cnt_stall),
    .lp_sleep
  );

  // ================================================================ accelerators
  logic [1:0]  vec_op;
  logic [15:0] vec_alpha, ten_k;
  logic [7:0]  reuse_replay;
  logic        perf_clear;
  logic [31:0] ten_mac, ten_stall_in, ten_stall_acc, ten_tiles, vec_active, vec_starve, vec_ostall;

  logic          vr_valid, vr_ready, vr_last;
  logic [DW-1:0] vr_data;
  sf_vec_unit #(.DW(DW), .EW(VEC_EW), .IN_FIFO(VEC_IN_FIFO)) u_vec (
    .clk, .rst_n, .cfg_op(vec_op), .cfg_alpha(vec_alpha), .perf_clear,
    .a_valid(so_valid[0]), .a_ready(so_ready[0]), .a_data(so_data), .a_last(so_last),
    .b_valid(so_valid[1]), .b_ready(so_ready[1]), .b_data(so_data),
    .r_valid(vr_valid), .r_ready(vr_ready), .r_data(vr_data), .r_last(vr_last),
    .cnt_active(vec_active), .cnt_starve(vec_starve), .cnt_ostall(vec_ostall)
  );

  logic          rb_valid, rb_ready, rb_last;
  logic [DW-1:0] rb_data;
  logic [1:0]    rb_full;
  logic [31:0]   rb_cnt;
  sf_reuse_buffer #(.DW(DW), .DEPTH(REUSE_DEPTH)) u_reuse (
    .clk, .rst_n, .cfg_replay(reuse_replay),
    .in_valid(so_valid[3]), .in_ready(so_ready[3]), .in_data(so_data), .in_last(so_last),
    .out_valid(rb_valid), .out_ready(rb_ready), .out_data(rb_data), .out_last(rb_last),
    .bank_full(rb_full), .cnt_replayed_beats(rb_cnt)
  );

  logic          tc_valid, tc_ready, tc_last;
  logic [DW-1:0] tc_data;
  sf_tensor_array #(.DW(DW), .TR(TEN_TR), .TC(TEN_TC), .ACC_DBUF(TEN_ACC_DBUF),
                    .IN_FIFO(TEN_IN_FIFO)) u_ten (
    .clk, .rst_n, .cfg_k(ten_k), .perf_clear,
    .a_valid(so_valid[2]), .a_ready(so_ready[2]), .a_data(so_data),
    .b_valid(rb_valid), .b_ready(rb_ready), .b_data(rb_data),
    .c_valid(tc_valid), .c_ready(tc_ready), .c_data(tc_data), .c_last(tc_last),
    .cnt_mac(ten_mac), .cnt_stall_in(ten_stall_in), .cnt_stall_acc(ten_stall_acc),
    .cnt_tiles(ten_tiles)
  );

  assign si_valid = {tc_valid, vr_valid};
  assign si_data  = {tc_data, vr_data};
  assign vr_ready = si_ready[0];
  assign tc_ready = si_ready[1];

  // ================================================================ control regs
  sf_ctrl_regs #(.SW(SW), .NBANKS(SPM_NBANKS), .IDXW(IDXW)) u_ctrl (
    .clk, .rst_n,
    .psel(sel_ctrl), .penable, .pwrite, .paddr(paddr[11:0]), .pwdata,
    .prdata(ctl_prdata), .pready(ctl_pready), .pslverr(ctl_pslverr),
    .vec_op, .vec_alpha, .ten_k, .reuse_replay, .perf_clear,
    .ten_mac, .ten_stall_in, .ten_stall_acc, .ten_tiles,
    .vec_active, .vec_starve, .vec_ostall,
    .inj_en, .inj_bank, .inj_mask,
    .spm_cnt_corr(cnt_corr), .spm_cnt_uncorr(cnt_uncorr),
    .spm_conflict(cnt_conflict), .spm_stall(cnt_stall),
    .mbist_start, .mbist_bg, .mbist_busy, .mbist_done, .mbist_fail,
    .mbist_fail_bank, .mbist_fail_addr, .lp_sleep
  );

  // unused
  /* verilator lint_off UNUSEDSIGNAL */
  wire unused_ok = ^{sp_rsp_corr, rr_req_we, wr_req_we, rr_req_wdata, rr_req_wstrb,
                     wr_rsp_rdata, rb_full, rb_cnt, so_strb, rb_last, vr_last,
                     tc_last, wr_req_valid, rr_req_valid, d_wr_rsp_rdata_unused};
  /* verilator lint_on UNUSEDSIGNAL */

endmodule

`default_nettype wire
