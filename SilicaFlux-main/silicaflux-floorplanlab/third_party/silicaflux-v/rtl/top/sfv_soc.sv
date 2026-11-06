// =============================================================================
// SilicaFlux-V :: sfv_soc -- core SoC (pad-less)
//
//   sfv_cpu (RV32I_Zicsr) --I/D--+
//   JTAG SBA master -------------+--> sfv_xbar --> ROM | SRAM bank 0..3 |
//                                                  TSPM (tile) | periph bridge
//   periph bridge pages: SYSCTRL INTC TIMER UART SPI GPIO | VE TE (tile)
//   sfv_mbist: group 0 = main SRAM banks, group 1 = TSPM banks
//
// Clock: single functional clock `clk` (+ JTAG `tck`).  Resets (all async
// assert, sync de-assert; bypassed to the pin in test_mode):
//   por_rst_n  pin reset           -> JTAG debug sys-side, SYSCTRL soft-reset gen
//   sys_rst_n  por & !soft & !jtag -> bus, memories ctrl, peripherals, tile
//   cpu_rst_n  sys & !jtag_hold    -> CPU
// Memory map: sfv_pkg / docs/MEMORY_MAP.md.
// =============================================================================
`default_nettype none

module sfv_soc #(
  parameter int          SRAM_BANKS      = 4,
  parameter int          SRAM_BANK_WORDS = 8192,      // 32 KiB per bank
  parameter int          TSPM_WORDS      = 4096,      // 16 KiB
  parameter int          ROM_WORDS       = 1024,      // 4 KiB
  parameter int          LANES           = 4,
  parameter int          MUL_W           = 32,
  parameter int          GPIO_N          = 8,
  parameter logic [15:0] UART_BAUD_RESET = 16'd217
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
  localparam int NM = sfv_pkg::NUM_MASTERS;
  localparam int NS = SRAM_BANKS + 3;           // ROM, banks, TSPM, PERIPH
  localparam int S_ROM = 0, S_TSPM = SRAM_BANKS + 1, S_PER = SRAM_BANKS + 2;
  localparam int BANK_BYTES = SRAM_BANK_WORDS * 4;
  localparam int TSPM_BYTES = TSPM_WORDS * 4;
  localparam int ROM_BYTES  = ROM_WORDS * 4;
  localparam int BAW = $clog2(SRAM_BANK_WORDS);
  localparam int TAW = $clog2(TSPM_WORDS / LANES);

  function automatic logic [NS*32-1:0] f_base();
    f_base = '0;
    f_base[S_ROM*32 +: 32] = sfv_pkg::ROM_BASE;
    for (int b = 0; b < SRAM_BANKS; b++)
      f_base[(b+1)*32 +: 32] = sfv_pkg::SRAM_BASE + 32'(b * BANK_BYTES);
    f_base[S_TSPM*32 +: 32] = sfv_pkg::TSPM_BASE;
    f_base[S_PER*32 +: 32]  = sfv_pkg::PERIPH_BASE;
  endfunction
  function automatic logic [NS*32-1:0] f_mask();
    f_mask = '0;
    f_mask[S_ROM*32 +: 32] = ~32'(ROM_BYTES - 1);
    for (int b = 0; b < SRAM_BANKS; b++) f_mask[(b+1)*32 +: 32] = ~32'(BANK_BYTES - 1);
    f_mask[S_TSPM*32 +: 32] = ~32'(TSPM_BYTES - 1);
    f_mask[S_PER*32 +: 32]  = sfv_pkg::PERIPH_MASK;
  endfunction
  // execute-never: the instruction port cannot reach the peripheral window
  function automatic logic [NM*NS-1:0] f_en();
    f_en = '1;
    f_en[sfv_pkg::M_CPUI*NS + S_PER] = 1'b0;
  endfunction

  // ------------------------------------------------------------ resets
  logic por_rst_n, sys_rst_n, cpu_rst_n, soft_reset, jtag_hold, jtag_srst;
  sfv_rst_sync u_rs_por (.clk, .rst_ni(rst_ni), .test_mode, .test_rst_ni(rst_ni), .rst_no(por_rst_n));
  sfv_rst_sync u_rs_sys (.clk, .rst_ni(por_rst_n && !soft_reset && !jtag_srst), .test_mode,
                         .test_rst_ni(rst_ni), .rst_no(sys_rst_n));
  sfv_rst_sync u_rs_cpu (.clk, .rst_ni(sys_rst_n && !jtag_hold), .test_mode,
                         .test_rst_ni(rst_ni), .rst_no(cpu_rst_n));

  // ------------------------------------------------------------ crossbar
  logic [NM-1:0]    m_req, m_gnt, m_we, m_rvalid, m_err;
  logic [NM*32-1:0] m_addr, m_wdata, m_rdata;
  logic [NM*4-1:0]  m_be;
  logic [NS-1:0]    s_req, s_gnt, s_we, s_rvalid, s_err;
  logic [NS*32-1:0] s_addr, s_wdata, s_rdata;
  logic [NS*4-1:0]  s_be;
  logic             berr_evt, berr_we;
  logic [31:0]      berr_addr;
  logic [1:0]       berr_m;

  sfv_xbar #(.NM(NM), .NS(NS), .SLV_BASE(f_base()), .SLV_MASK(f_mask()), .MST_SLV_EN(f_en())) u_xbar (
    .clk, .rst_n(sys_rst_n),
    .m_req, .m_gnt, .m_addr, .m_we, .m_be, .m_wdata, .m_rvalid, .m_rdata, .m_err,
    .s_req, .s_gnt, .s_addr, .s_we, .s_be, .s_wdata, .s_rvalid, .s_rdata, .s_err,
    .err_evt(berr_evt), .err_addr(berr_addr), .err_master(berr_m), .err_we(berr_we)
  );

  // ------------------------------------------------------------ CPU
  logic irq_ext, irq_timer, irq_soft;
  localparam int MI = sfv_pkg::M_CPUI, MD = sfv_pkg::M_CPUD, MG = sfv_pkg::M_DBG;
  logic [31:0] cpu_i_addr;
  /* verilator lint_off PINCONNECTEMPTY */
  sfv_cpu #(.BOOT_ADDR(sfv_pkg::ROM_BASE)) u_cpu (
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

  // ------------------------------------------------------------ JTAG debug
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

  // ------------------------------------------------------------ boot ROM
  sfv_bootrom #(.WORDS(ROM_WORDS)) u_rom (
    .clk, .rst_n(sys_rst_n),
    .req(s_req[S_ROM]), .gnt(s_gnt[S_ROM]), .addr(s_addr[S_ROM*32 +: 32]), .we(s_we[S_ROM]),
    .be(s_be[S_ROM*4 +: 4]), .wdata(s_wdata[S_ROM*32 +: 32]), .rvalid(s_rvalid[S_ROM]),
    .rdata(s_rdata[S_ROM*32 +: 32]), .err(s_err[S_ROM])
  );

  // ------------------------------------------------------------ MBIST
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
    sfv_sram_slave #(.DEPTH(SRAM_BANK_WORDS)) u_bank (
      .clk, .rst_n(sys_rst_n),
      .req(s_req[gb+1]), .gnt(s_gnt[gb+1]), .addr(s_addr[(gb+1)*32 +: 32]), .we(s_we[gb+1]),
      .be(s_be[(gb+1)*4 +: 4]), .wdata(s_wdata[(gb+1)*32 +: 32]), .rvalid(s_rvalid[gb+1]),
      .rdata(s_rdata[(gb+1)*32 +: 32]), .err(s_err[gb+1]),
      .bist_en(mb_en && !mb_grp), .bist_ce(mb_ce), .bist_we(mb_we),
      .bist_addr(mb_addr[BAW-1:0]), .bist_wdata(mb_wdata),
      .bist_rdata(mb_rd_sram[gb*32 +: 32])
    );
  end

  // ------------------------------------------------------------ peripherals
  localparam int NP = sfv_pkg::NUM_PAGES;
  logic [NP-1:0]    rb_sel;
  wire  [NP-1:0]    rb_err;
  logic             rb_we;
  logic [11:0]      rb_addr;
  logic [31:0]      rb_wdata;
  wire  [NP*32-1:0] rb_rdata;
  localparam logic [31:0] PAGE_EN = (32'd1 << sfv_pkg::PG_SYSCTRL) | (32'd1 << sfv_pkg::PG_INTC) |
                                    (32'd1 << sfv_pkg::PG_TIMER) | (32'd1 << sfv_pkg::PG_UART) |
                                    (32'd1 << sfv_pkg::PG_SPI) | (32'd1 << sfv_pkg::PG_GPIO) |
                                    (32'd1 << sfv_pkg::PG_VE) | (32'd1 << sfv_pkg::PG_TE);
  sfv_periph_bridge #(.NP(NP), .PAGE_EN(PAGE_EN)) u_pbr (
    .clk, .rst_n(sys_rst_n),
    .req(s_req[S_PER]), .gnt(s_gnt[S_PER]), .addr(s_addr[S_PER*32 +: 32]), .we(s_we[S_PER]),
    .be(s_be[S_PER*4 +: 4]), .wdata(s_wdata[S_PER*32 +: 32]), .rvalid(s_rvalid[S_PER]),
    .rdata(s_rdata[S_PER*32 +: 32]), .err(s_err[S_PER]),
    .rb_sel, .rb_we, .rb_addr, .rb_wdata, .rb_rdata, .rb_err
  );
  // unused pages: tie off (the bridge never selects them)
  genvar gp;
  for (gp = 0; gp < NP; gp++) begin : g_page
    if (!PAGE_EN[gp]) begin : g_unused
      assign rb_rdata[gp*32 +: 32] = 32'd0;
      assign rb_err[gp]            = 1'b1;
    end
  end

  logic [sfv_pkg::NUM_IRQ-1:0] irq_src;
  logic irq_uart, irq_spi, irq_gpio, irq_ve, irq_te, irq_mbist, irq_berr, irq_dbg, tile_cg_off;

  logic [1:0] straps_s;
  sfv_sync u_st0 (.clk, .rst_n(por_rst_n), .d(gpio_i[0]), .q(straps_s[0]));
  sfv_sync u_st1 (.clk, .rst_n(por_rst_n), .d(gpio_i[1]), .q(straps_s[1]));

  localparam int P_SC = sfv_pkg::PG_SYSCTRL, P_IC = sfv_pkg::PG_INTC, P_TM = sfv_pkg::PG_TIMER;
  localparam int P_UA = sfv_pkg::PG_UART, P_SP = sfv_pkg::PG_SPI, P_GP = sfv_pkg::PG_GPIO;
  localparam int P_VE = sfv_pkg::PG_VE, P_TE = sfv_pkg::PG_TE;

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

  sfv_intc #(.N(sfv_pkg::NUM_IRQ)) u_intc (
    .clk, .rst_n(sys_rst_n),
    .rb_sel(rb_sel[P_IC]), .rb_we, .rb_addr, .rb_wdata,
    .rb_rdata(rb_rdata[P_IC*32 +: 32]), .rb_err(rb_err[P_IC]),
    .src(irq_src), .irq_ext
  );
  assign irq_src = {irq_dbg, irq_berr, irq_mbist, irq_te, irq_ve, irq_gpio, irq_spi, irq_uart};

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

  // ------------------------------------------------------------ compute tile
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
