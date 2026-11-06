// =============================================================================
// SilicaFlux DataFabric :: sfv_soc_df -- SilicaFlux-V core SoC with DataFabric
//
// Derived from silicaflux-v rtl/top/sfv_soc.sv (release 1, vendored unmodified
// in third_party/).  Everything except the items below is identical:
//   * sfv_xbar (SFB, 3 masters)  ->  sfb_crossbar (SFB2, 4 masters,
//     round-robin by default, alignment check), addresses / access matrix /
//     pages / IRQs from generated/sfb_memmap_pkg.sv (memmap YAML);
//   * new master 3: silicaflux_dma (single channel; ENGINE 0 simple = default,
//     1 buffered); denied the peripheral window by the access matrix;
//   * new register pages: DMA (page 6, 0x4000_6000) and optional DataFabric
//     performance counters DFPERF (page 7, 0x4000_7000, PERF = 1);
//   * new interrupt source 8 = DMA (INTC N = 9);
//   * legacy SFB slaves (ROM, TSPM tile, peripheral bridge, and the SRAM banks
//     when SRAM_IMPL = 0) sit behind sfb_v1_slave_adapter; legacy masters
//     (CPU I/D, JTAG) always accept responses (rsp_ready = 1);
//   * SRAM_IMPL = 1 replaces the SRAM banks by SilicaFlux SRAM Wrapper Library
//     sram_sp instances (sfb_sram_slave, READ_LATENCY = SRAM_LATENCY); the
//     sfv_mbist collar drives the library test port (MBIST requires
//     SRAM_LATENCY = 1, the latency sfv_mbist was designed for).
// Clock / reset structure unchanged: one functional clock (+TCK), DMA and
// fabric in the sys_rst_n domain.
// =============================================================================
`default_nettype none

module sfv_soc_df #(
  parameter int          SRAM_BANKS      = 4,
  parameter int          SRAM_BANK_WORDS = 8192,      // 32 KiB per bank
  parameter int          TSPM_WORDS      = 4096,      // 16 KiB
  parameter int          ROM_WORDS       = 1024,      // 4 KiB
  parameter int          LANES           = 4,
  parameter int          MUL_W           = 32,
  parameter int          GPIO_N          = 8,
  parameter logic [15:0] UART_BAUD_RESET = 16'd217,
  // ---- DataFabric
  parameter int          ARB_MODE        = 1,         // 0 fixed priority (sfv_xbar), 1 round robin
  parameter int          DMA_ENGINE      = 0,         // 0 simple, 1 buffered
  parameter int          DMA_FIFO_DEPTH  = 8,
  parameter int          DMA_BURST       = 8,
  parameter int          PERF            = 1,         // DataFabric performance counters
  parameter int          SRAM_IMPL       = 0,         // 0 sfv_sram_slave, 1 sramlib sram_sp
  parameter int          SRAM_LATENCY    = 1
) (
  input  wire logic              clk,
  input  wire logic              rst_ni,
  input  wire logic              test_mode,
  // JTAG
  input  wire logic              tck,
  input  wire logic              tms,
  input  wire logic              tdi,
  output logic                   tdo,
  output logic                   tdo_oe,
  // UART
  output logic                   uart_tx,
  input  wire logic              uart_rx,
  // SPI
  output logic                   spi_sck,
  output logic                   spi_mosi,
  input  wire logic              spi_miso,
  output logic                   spi_cs0_n,
  // GPIO (gpio[1:0] are boot straps while reset is asserted)
  input  wire logic [GPIO_N-1:0] gpio_i,
  output logic [GPIO_N-1:0]      gpio_o,
  output logic [GPIO_N-1:0]      gpio_oe,
  // test / status
  output logic                   test_pass,
  output logic                   test_fail,
  output logic [31:0]            test_status,
  output logic                   cpu_sleep
);
  localparam int NM = sfb_memmap_pkg::NUM_MASTERS;            // DBG, CPUD, CPUI, DMA
  localparam int NS = sfb_memmap_pkg::NUM_SLAVES;             // ROM, SRAM0..3, TSPM, PERIPH
  localparam int S_ROM = sfb_memmap_pkg::S_ROM, S_TSPM = sfb_memmap_pkg::S_TSPM;
  localparam int S_PER = sfb_memmap_pkg::S_PERIPH, S_SRAM0 = sfb_memmap_pkg::S_SRAM0;
  localparam int BAW = $clog2(SRAM_BANK_WORDS);
  localparam int TAW = $clog2(TSPM_WORDS / LANES);

  // The address map is generated from memmap/silicaflux_v_datafabric.yaml for
  // the default memory sizes; any other size must be changed in the YAML.
  if (SRAM_BANKS != 4 || 32'(SRAM_BANK_WORDS * 4) != sfb_memmap_pkg::SRAM_BANK0_SIZE ||
      32'(TSPM_WORDS * 4) != sfb_memmap_pkg::TSPM_SIZE || 32'(ROM_WORDS * 4) != sfb_memmap_pkg::BOOT_ROM_SIZE ||
      NS != SRAM_BANKS + 3 || S_SRAM0 != 1) begin : g_err_memory_sizes_must_match_memmap_yaml
    sfv_soc_df_memory_sizes_must_match_memmap_yaml u_cfg_error ();
  end

  // ------------------------------------------------------------ resets (unchanged)
  logic por_rst_n, sys_rst_n, cpu_rst_n, soft_reset, jtag_hold, jtag_srst;
  sfv_rst_sync u_rs_por (.clk, .rst_ni(rst_ni), .test_mode, .test_rst_ni(rst_ni), .rst_no(por_rst_n));
  sfv_rst_sync u_rs_sys (.clk, .rst_ni(por_rst_n && !soft_reset && !jtag_srst), .test_mode,
                         .test_rst_ni(rst_ni), .rst_no(sys_rst_n));
  sfv_rst_sync u_rs_cpu (.clk, .rst_ni(sys_rst_n && !jtag_hold), .test_mode,
                         .test_rst_ni(rst_ni), .rst_no(cpu_rst_n));

  // ------------------------------------------------------------ crossbar (SFB2)
  // master side: legacy names; m_rsp_ready = 1 for the legacy masters
  logic [NM-1:0]    m_req, m_gnt, m_we, m_rvalid, m_err, m_rsp_ready;
  logic [NM*32-1:0] m_addr, m_wdata, m_rdata;
  logic [NM*4-1:0]  m_be;
  // slave side (SFB2)
  logic [NS-1:0]    x_req_valid, x_req_ready, x_req_write, x_rsp_valid, x_rsp_ready, x_rsp_error;
  logic [NS*32-1:0] x_req_addr, x_req_wdata, x_rsp_rdata;
  logic [NS*4-1:0]  x_req_wstrb;
  // legacy slave ports (behind sfb_v1_slave_adapter); with SRAM_IMPL = 1 the
  // SRAM-bank slots of these arrays are unused by design
  /* verilator lint_off UNUSEDSIGNAL */
  logic [NS-1:0]    s_req, s_gnt, s_we, s_rvalid, s_err;
  logic [NS*32-1:0] s_addr, s_wdata, s_rdata;
  logic [NS*4-1:0]  s_be;
  /* verilator lint_on UNUSEDSIGNAL */
  logic             berr_evt, berr_we;
  logic [31:0]      berr_addr;
  logic [1:0]       berr_m;
  logic [NM-1:0]    ev_acc, ev_stall, ev_loss, ev_rstall;

  sfb_crossbar #(
    .NM(NM), .NS(NS), .AW(32), .DW(32), .ARB_MODE(ARB_MODE), .CHECK_ALIGN(1),
    .SLV_BASE(sfb_memmap_pkg::SLV_BASE), .SLV_MASK(sfb_memmap_pkg::SLV_MASK),
    .MST_SLV_EN(sfb_memmap_pkg::MST_SLV_EN)
  ) u_xbar (
    .clk, .rst_n(sys_rst_n),
    .m_req_valid(m_req), .m_req_ready(m_gnt), .m_req_write(m_we), .m_req_addr(m_addr),
    .m_req_wdata(m_wdata), .m_req_wstrb(m_be),
    .m_rsp_valid(m_rvalid), .m_rsp_ready(m_rsp_ready), .m_rsp_rdata(m_rdata), .m_rsp_error(m_err),
    .s_req_valid(x_req_valid), .s_req_ready(x_req_ready), .s_req_write(x_req_write),
    .s_req_addr(x_req_addr), .s_req_wdata(x_req_wdata), .s_req_wstrb(x_req_wstrb),
    .s_rsp_valid(x_rsp_valid), .s_rsp_ready(x_rsp_ready), .s_rsp_rdata(x_rsp_rdata),
    .s_rsp_error(x_rsp_error),
    .err_evt(berr_evt), .err_addr(berr_addr), .err_master(berr_m), .err_write(berr_we),
    .ev_req_accept(ev_acc), .ev_req_stall(ev_stall), .ev_arb_loss(ev_loss), .ev_rsp_stall(ev_rstall)
  );

  // legacy slaves on SFB2: ROM, TSPM, PERIPH (+ SRAM banks when SRAM_IMPL = 0)
  genvar ga;
  for (ga = 0; ga < NS; ga++) begin : g_v1
    if (!(SRAM_IMPL != 0 && ga >= S_SRAM0 && ga < S_SRAM0 + SRAM_BANKS)) begin : g_ad
      sfb_v1_slave_adapter u_ad (
        .clk, .rst_n(sys_rst_n),
        .req_valid(x_req_valid[ga]), .req_ready(x_req_ready[ga]), .req_write(x_req_write[ga]),
        .req_addr(x_req_addr[ga*32 +: 32]), .req_wdata(x_req_wdata[ga*32 +: 32]),
        .req_wstrb(x_req_wstrb[ga*4 +: 4]),
        .rsp_valid(x_rsp_valid[ga]), .rsp_ready(x_rsp_ready[ga]), .rsp_rdata(x_rsp_rdata[ga*32 +: 32]),
        .rsp_error(x_rsp_error[ga]),
        .v1_req(s_req[ga]), .v1_gnt(s_gnt[ga]), .v1_addr(s_addr[ga*32 +: 32]), .v1_we(s_we[ga]),
        .v1_be(s_be[ga*4 +: 4]), .v1_wdata(s_wdata[ga*32 +: 32]),
        .v1_rvalid(s_rvalid[ga]), .v1_rdata(s_rdata[ga*32 +: 32]), .v1_err(s_err[ga])
      );
    end else begin : g_tie
      assign s_req[ga] = 1'b0;
      assign s_addr[ga*32 +: 32] = '0;
      assign s_we[ga] = 1'b0;
      assign s_be[ga*4 +: 4] = '0;
      assign s_wdata[ga*32 +: 32] = '0;
    end
  end

  // ------------------------------------------------------------ CPU (unchanged)
  logic irq_ext, irq_timer, irq_soft;
  localparam int MI = sfb_memmap_pkg::M_CPUI, MD = sfb_memmap_pkg::M_CPUD, MG = sfb_memmap_pkg::M_DBG;
  localparam int MDMA = sfb_memmap_pkg::M_DMA;
  logic [31:0] cpu_i_addr;
  /* verilator lint_off PINCONNECTEMPTY */
  sfv_cpu #(.BOOT_ADDR(sfb_memmap_pkg::BOOT_ROM_BASE)) u_cpu (
    .clk, .rst_n(cpu_rst_n),
    .i_req(m_req[MI]), .i_gnt(m_gnt[MI]), .i_addr(cpu_i_addr), .i_rvalid(m_rvalid[MI]),
    .i_rdata(m_rdata[MI*32 +: 32]), .i_err(m_err[MI]),
    .d_req(m_req[MD]), .d_gnt(m_gnt[MD]), .d_addr(m_addr[MD*32 +: 32]), .d_we(m_we[MD]),
    .d_be(m_be[MD*4 +: 4]), .d_wdata(m_wdata[MD*32 +: 32]), .d_rvalid(m_rvalid[MD]),
    .d_rdata(m_rdata[MD*32 +: 32]), .d_err(m_err[MD]),
    .irq_ext, .irq_timer, .irq_soft, .sleeping(cpu_sleep),
    .rt_valid(), .rt_pc(), .rt_insn(), .rt_trap(), .rt_cause(), .rt_rd(), .rt_rd_wdata(), .rt_rd_we()
  );
  /* verilator lint_on PINCONNECTEMPTY */
  assign m_addr[MI*32 +: 32]  = cpu_i_addr;
  assign m_we[MI]             = 1'b0;
  assign m_be[MI*4 +: 4]      = 4'b1111;
  assign m_wdata[MI*32 +: 32] = 32'd0;
  assign m_rsp_ready[MI]      = 1'b1;          // legacy SFB masters always accept responses
  assign m_rsp_ready[MD]      = 1'b1;
  assign m_rsp_ready[MG]      = 1'b1;

  // ------------------------------------------------------------ JTAG debug (unchanged)
  logic boot_ovr;
  logic [1:0] boot_ovr_mode;
  sfv_jtag_dbg u_dbg (
    .tck, .trst_n(rst_ni), .tms, .tdi, .tdo, .tdo_oe,
    .clk, .rst_n(por_rst_n),
    .m_req(m_req[MG]), .m_gnt(m_gnt[MG]), .m_addr(m_addr[MG*32 +: 32]), .m_we(m_we[MG]),
    .m_be(m_be[MG*4 +: 4]), .m_wdata(m_wdata[MG*32 +: 32]), .m_rvalid(m_rvalid[MG]),
    .m_rdata(m_rdata[MG*32 +: 32]), .m_err(m_err[MG]),
    .cpu_hold(jtag_hold), .sys_reset_req(jtag_srst), .boot_ovr, .boot_ovr_mode,
    .cpu_sleep, .test_pass, .test_fail
  );

  // ------------------------------------------------------------ boot ROM (unchanged)
  sfv_bootrom #(.WORDS(ROM_WORDS)) u_rom (
    .clk, .rst_n(sys_rst_n),
    .req(s_req[S_ROM]), .gnt(s_gnt[S_ROM]), .addr(s_addr[S_ROM*32 +: 32]), .we(s_we[S_ROM]),
    .be(s_be[S_ROM*4 +: 4]), .wdata(s_wdata[S_ROM*32 +: 32]), .rvalid(s_rvalid[S_ROM]),
    .rdata(s_rdata[S_ROM*32 +: 32]), .err(s_err[S_ROM])
  );

  // ------------------------------------------------------------ MBIST (unchanged)
  localparam int MAW = (BAW > TAW) ? BAW : TAW;
  logic mb_start, mb_bg, mb_grp, mb_busy, mb_done, mb_fail, mb_en, mb_ce, mb_we;
  logic [3:0]  mb_fbank;
  logic [2:0]  mb_felem;
  logic [MAW-1:0] mb_faddr, mb_addr;
  logic [31:0] mb_wdata;
  logic [SRAM_BANKS*32-1:0] mb_rd_sram;
  logic [LANES*32-1:0]      mb_rd_tspm;
  logic [4*32-1:0]          mb_rd;
  always_comb begin
    mb_rd = '0;
    if (mb_grp) mb_rd[LANES*32-1:0] = mb_rd_tspm;
    else        mb_rd[SRAM_BANKS*32-1:0] = mb_rd_sram;
  end
  sfv_mbist #(.AW(MAW), .NBANKS(4)) u_mbist (
    .clk, .rst_n(sys_rst_n), .start(mb_start), .bg_chk(mb_bg),
    .last(mb_grp ? MAW'(TSPM_WORDS / LANES - 1) : MAW'(SRAM_BANK_WORDS - 1)),
    .busy(mb_busy), .done(mb_done), .fail(mb_fail), .fail_bank(mb_fbank),
    .fail_addr(mb_faddr), .fail_elem(mb_felem),
    .bist_en(mb_en), .bist_ce(mb_ce), .bist_we(mb_we), .bist_addr(mb_addr),
    .bist_wdata(mb_wdata), .bist_rdata(mb_rd)
  );

  // ------------------------------------------------------------ SRAM banks
  genvar gb;
  for (gb = 0; gb < SRAM_BANKS; gb++) begin : g_sram
    if (SRAM_IMPL == 0) begin : g_sfv
      // SilicaFlux-V bank (sfv_sram_slave) behind its legacy adapter
      sfv_sram_slave #(.DEPTH(SRAM_BANK_WORDS)) u_bank (
        .clk, .rst_n(sys_rst_n),
        .req(s_req[gb+S_SRAM0]), .gnt(s_gnt[gb+S_SRAM0]), .addr(s_addr[(gb+S_SRAM0)*32 +: 32]),
        .we(s_we[gb+S_SRAM0]), .be(s_be[(gb+S_SRAM0)*4 +: 4]), .wdata(s_wdata[(gb+S_SRAM0)*32 +: 32]),
        .rvalid(s_rvalid[gb+S_SRAM0]), .rdata(s_rdata[(gb+S_SRAM0)*32 +: 32]), .err(s_err[gb+S_SRAM0]),
        .bist_en(mb_en && !mb_grp), .bist_ce(mb_ce), .bist_we(mb_we),
        .bist_addr(mb_addr[BAW-1:0]), .bist_wdata(mb_wdata),
        .bist_rdata(mb_rd_sram[gb*32 +: 32])
      );
    end else begin : g_lib
      // SilicaFlux SRAM Wrapper Library bank (Project 01) directly on SFB2
      sfb_sram_slave #(.DW(32), .DEPTH(SRAM_BANK_WORDS), .READ_LATENCY(SRAM_LATENCY)) u_bank (
        .clk, .rst_n(sys_rst_n),
        .req_valid(x_req_valid[gb+S_SRAM0]), .req_ready(x_req_ready[gb+S_SRAM0]),
        .req_write(x_req_write[gb+S_SRAM0]), .req_addr(x_req_addr[(gb+S_SRAM0)*32 +: 32]),
        .req_wdata(x_req_wdata[(gb+S_SRAM0)*32 +: 32]), .req_wstrb(x_req_wstrb[(gb+S_SRAM0)*4 +: 4]),
        .rsp_valid(x_rsp_valid[gb+S_SRAM0]), .rsp_ready(x_rsp_ready[gb+S_SRAM0]),
        .rsp_rdata(x_rsp_rdata[(gb+S_SRAM0)*32 +: 32]), .rsp_error(x_rsp_error[gb+S_SRAM0]),
        .tst_active(mb_en && !mb_grp), .tst_ce(mb_ce), .tst_we(mb_we), .tst_addr(mb_addr[BAW-1:0]),
        .tst_wdata(mb_wdata), .tst_rdata(mb_rd_sram[gb*32 +: 32])
      );
      assign s_gnt[gb+S_SRAM0]               = 1'b0;
      assign s_rvalid[gb+S_SRAM0]            = 1'b0;
      assign s_rdata[(gb+S_SRAM0)*32 +: 32]  = '0;
      assign s_err[gb+S_SRAM0]               = 1'b0;
    end
  end

  // ------------------------------------------------------------ peripherals
  localparam int NP = sfv_pkg::NUM_PAGES;
  logic [NP-1:0]    rb_sel;
  wire  [NP-1:0]    rb_err;
  logic             rb_we;
  logic [11:0]      rb_addr;
  logic [31:0]      rb_wdata;
  wire  [NP*32-1:0] rb_rdata;
  localparam logic [31:0] PAGE_EN = (PERF != 0) ? sfb_memmap_pkg::PAGE_EN :
                                    (sfb_memmap_pkg::PAGE_EN & ~(32'd1 << sfb_memmap_pkg::PG_DFPERF));
  sfv_periph_bridge #(.NP(NP), .PAGE_EN(PAGE_EN)) u_pbr (
    .clk, .rst_n(sys_rst_n),
    .req(s_req[S_PER]), .gnt(s_gnt[S_PER]), .addr(s_addr[S_PER*32 +: 32]), .we(s_we[S_PER]),
    .be(s_be[S_PER*4 +: 4]), .wdata(s_wdata[S_PER*32 +: 32]), .rvalid(s_rvalid[S_PER]),
    .rdata(s_rdata[S_PER*32 +: 32]), .err(s_err[S_PER]),
    .rb_sel, .rb_we, .rb_addr, .rb_wdata, .rb_rdata, .rb_err
  );
  genvar gp;
  for (gp = 0; gp < NP; gp++) begin : g_page
    if (!PAGE_EN[gp]) begin : g_unused
      assign rb_rdata[gp*32 +: 32] = 32'd0;
      assign rb_err[gp]            = 1'b1;
    end
  end

  localparam int NIRQ = sfb_memmap_pkg::NUM_IRQ;
  logic [NIRQ-1:0] irq_src;
  logic irq_uart, irq_spi, irq_gpio, irq_ve, irq_te, irq_mbist, irq_berr, irq_dbg, irq_dma, tile_cg_off;

  logic [1:0] straps_s;
  sfv_sync u_st0 (.clk, .rst_n(por_rst_n), .d(gpio_i[0]), .q(straps_s[0]));
  sfv_sync u_st1 (.clk, .rst_n(por_rst_n), .d(gpio_i[1]), .q(straps_s[1]));

  localparam int P_SC = sfb_memmap_pkg::PG_SYSCTRL, P_IC = sfb_memmap_pkg::PG_INTC;
  localparam int P_TM = sfb_memmap_pkg::PG_TIMER,   P_UA = sfb_memmap_pkg::PG_UART;
  localparam int P_SP = sfb_memmap_pkg::PG_SPI,     P_GP = sfb_memmap_pkg::PG_GPIO;
  localparam int P_VE = sfb_memmap_pkg::PG_VE,      P_TE = sfb_memmap_pkg::PG_TE;
  localparam int P_DMA = sfb_memmap_pkg::PG_DMA,    P_PERF = sfb_memmap_pkg::PG_DFPERF;

  sfv_sysctrl u_sysctrl (
    .clk, .rst_n(sys_rst_n), .por_rst_n,
    .rb_sel(rb_sel[P_SC]), .rb_we, .rb_addr, .rb_wdata,
    .rb_rdata(rb_rdata[P_SC*32 +: 32]), .rb_err(rb_err[P_SC]),
    .boot_straps(boot_ovr ? boot_ovr_mode : straps_s), .jtag_cpu_hold(jtag_hold),
    .berr_evt, .berr_addr, .berr_master(berr_m), .berr_we,
    .mbist_start(mb_start), .mbist_bg(mb_bg), .mbist_group(mb_grp),
    .mbist_busy(mb_busy), .mbist_done(mb_done), .mbist_fail(mb_fail),
    .mbist_fail_bank(mb_fbank), .mbist_fail_elem(mb_felem),
    .mbist_fail_addr(16'(mb_faddr)),
    .soft_reset, .tile_cg_off, .test_pass, .test_fail, .test_status,
    .irq_berr, .irq_mbist, .irq_dbg
  );

  sfv_intc #(.N(NIRQ)) u_intc (
    .clk, .rst_n(sys_rst_n),
    .rb_sel(rb_sel[P_IC]), .rb_we, .rb_addr, .rb_wdata,
    .rb_rdata(rb_rdata[P_IC*32 +: 32]), .rb_err(rb_err[P_IC]),
    .src(irq_src), .irq_ext
  );
  always_comb begin
    irq_src = '0;
    irq_src[sfb_memmap_pkg::IRQ_UART]   = irq_uart;
    irq_src[sfb_memmap_pkg::IRQ_SPI]    = irq_spi;
    irq_src[sfb_memmap_pkg::IRQ_GPIO]   = irq_gpio;
    irq_src[sfb_memmap_pkg::IRQ_VE]     = irq_ve;
    irq_src[sfb_memmap_pkg::IRQ_TE]     = irq_te;
    irq_src[sfb_memmap_pkg::IRQ_MBIST]  = irq_mbist;
    irq_src[sfb_memmap_pkg::IRQ_BUSERR] = irq_berr;
    irq_src[sfb_memmap_pkg::IRQ_DBG]    = irq_dbg;
    irq_src[sfb_memmap_pkg::IRQ_DMA]    = irq_dma;
  end

  sfv_timer u_timer (
    .clk, .rst_n(sys_rst_n),
    .rb_sel(rb_sel[P_TM]), .rb_we, .rb_addr, .rb_wdata,
    .rb_rdata(rb_rdata[P_TM*32 +: 32]), .rb_err(rb_err[P_TM]),
    .irq_timer, .irq_soft
  );

  sfv_uart #(.BAUD_RESET(UART_BAUD_RESET)) u_uart (
    .clk, .rst_n(sys_rst_n),
    .rb_sel(rb_sel[P_UA]), .rb_we, .rb_addr, .rb_wdata,
    .rb_rdata(rb_rdata[P_UA*32 +: 32]), .rb_err(rb_err[P_UA]),
    .txd(uart_tx), .rxd(uart_rx), .irq(irq_uart)
  );

  sfv_spi u_spi (
    .clk, .rst_n(sys_rst_n),
    .rb_sel(rb_sel[P_SP]), .rb_we, .rb_addr, .rb_wdata,
    .rb_rdata(rb_rdata[P_SP*32 +: 32]), .rb_err(rb_err[P_SP]),
    .sck(spi_sck), .mosi(spi_mosi), .miso(spi_miso), .cs0_n(spi_cs0_n), .irq(irq_spi)
  );

  sfv_gpio #(.N(GPIO_N)) u_gpio (
    .clk, .rst_n(sys_rst_n),
    .rb_sel(rb_sel[P_GP]), .rb_we, .rb_addr, .rb_wdata,
    .rb_rdata(rb_rdata[P_GP*32 +: 32]), .rb_err(rb_err[P_GP]),
    .gpio_i, .gpio_o, .gpio_oe, .irq(irq_gpio)
  );

  // ------------------------------------------------------------ DMA (DataFabric)
  logic        dma_busy, dma_done_ev;
  logic [31:0] dma_bytes;
  logic [7:0]  dma_fifo_level;
  silicaflux_dma #(.DW(32), .ENGINE(DMA_ENGINE), .FIFO_DEPTH(DMA_FIFO_DEPTH), .BURST(DMA_BURST),
                   .DUAL_PORT(0), .MAX_OUT(2), .MAX_LEN_LOG2(24), .PERF(PERF)) u_dma (
    .clk, .rst_n(sys_rst_n),
    .rb_sel(rb_sel[P_DMA]), .rb_we, .rb_addr, .rb_wdata,
    .rb_rdata(rb_rdata[P_DMA*32 +: 32]), .rb_err(rb_err[P_DMA]), .irq(irq_dma),
    .m_req_valid(m_req[MDMA]), .m_req_ready(m_gnt[MDMA]), .m_req_write(m_we[MDMA]),
    .m_req_addr(m_addr[MDMA*32 +: 32]), .m_req_wdata(m_wdata[MDMA*32 +: 32]), .m_req_wstrb(m_be[MDMA*4 +: 4]),
    .m_rsp_valid(m_rvalid[MDMA]), .m_rsp_ready(m_rsp_ready[MDMA]), .m_rsp_rdata(m_rdata[MDMA*32 +: 32]),
    .m_rsp_error(m_err[MDMA]),
    .busy(dma_busy), .ev_done(dma_done_ev), .bytes_done(dma_bytes), .fifo_level(dma_fifo_level)
  );

  // ------------------------------------------------------------ DataFabric performance counters
  if (PERF != 0) begin : g_perf
    sfb_perf_counters #(.NM(NM), .CW(32)) u_perf (
      .clk, .rst_n(sys_rst_n),
      .rb_sel(rb_sel[P_PERF]), .rb_we, .rb_addr, .rb_wdata,
      .rb_rdata(rb_rdata[P_PERF*32 +: 32]), .rb_err(rb_err[P_PERF]),
      .ev_accept(ev_acc), .ev_write(m_we), .ev_req_stall(ev_stall), .ev_arb_loss(ev_loss),
      .ev_rsp_stall(ev_rstall), .ev_rsp_error(m_rvalid & m_rsp_ready & m_err),
      .dma_busy, .dma_done(dma_done_ev), .dma_bytes, .fifo_level(dma_fifo_level)
    );
  end else begin : g_noperf
    // area-minimised build: fabric events and DMA status are left unobserved
    /* verilator lint_off UNUSEDSIGNAL */
    wire unused_perf = ^{ev_acc, ev_stall, ev_loss, ev_rstall, dma_busy, dma_done_ev, dma_bytes, dma_fifo_level};
    /* verilator lint_on UNUSEDSIGNAL */
  end

  // ------------------------------------------------------------ compute tile (unchanged)
  sfv_tile #(.LANES(LANES), .MUL_W(MUL_W), .TSPM_WORDS(TSPM_WORDS)) u_tile (
    .clk, .rst_n(sys_rst_n), .test_mode, .cg_off(tile_cg_off),
    .req(s_req[S_TSPM]), .gnt(s_gnt[S_TSPM]), .addr(s_addr[S_TSPM*32 +: 32]), .we(s_we[S_TSPM]),
    .be(s_be[S_TSPM*4 +: 4]), .wdata(s_wdata[S_TSPM*32 +: 32]), .rvalid(s_rvalid[S_TSPM]),
    .rdata(s_rdata[S_TSPM*32 +: 32]), .err(s_err[S_TSPM]),
    .ve_sel(rb_sel[P_VE]), .te_sel(rb_sel[P_TE]), .rb_we, .rb_addr, .rb_wdata,
    .ve_rdata(rb_rdata[P_VE*32 +: 32]), .ve_err(rb_err[P_VE]),
    .te_rdata(rb_rdata[P_TE*32 +: 32]), .te_err(rb_err[P_TE]),
    .irq_ve, .irq_te,
    .bist_en(mb_en && mb_grp), .bist_ce(mb_ce), .bist_we(mb_we),
    .bist_addr(mb_addr[TAW-1:0]), .bist_wdata(mb_wdata), .bist_rdata(mb_rd_tspm)
  );
endmodule

`default_nettype wire
