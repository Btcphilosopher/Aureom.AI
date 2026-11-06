// =============================================================================
// SilicaFlux-V :: sfv_pkg
// Architectural constants shared by RTL, firmware (firmware/common/sfv_map.h is
// generated to match) and verification.
//
// Coding rule (see docs/RTL_CODING_RULES.md): reference members explicitly as
// sfv_pkg::NAME. Wildcard imports are not used because the Yosys 0.33
// frontend used by the baseline ASIC flow does not accept them.
// =============================================================================
`default_nettype none

package sfv_pkg;

  // ---------------------------------------------------------------- identity
  localparam logic [31:0] CHIP_ID   = 32'h5346_5601;  // "SFV" rev 0x01
  localparam logic [31:0] MIMPID    = 32'h0001_0000;  // CPU impl. v1.0
  // JTAG IDCODE: [31:28] version, [27:12] part, [11:1] JEDEC mfr, [0]=1
  // The JEDEC manufacturer field is a PLACEHOLDER (0x000) until an ID is
  // assigned (see docs/ISSUE_REGISTER.md, ISS-010).
  localparam logic [15:0] JTAG_PART = 16'h5F05;
  localparam logic [10:0] JTAG_MFR  = 11'h000;

  // ---------------------------------------------------------------- memory map
  localparam logic [31:0] ROM_BASE    = 32'h0000_0000;
  localparam logic [31:0] ROM_MASK    = 32'hFFFF_C000;  // 16 KiB window
  localparam logic [31:0] SRAM_BASE   = 32'h1000_0000;
  localparam logic [31:0] TSPM_BASE   = 32'h2000_0000;
  localparam logic [31:0] TSPM_MASK   = 32'hFFFF_0000;  // 64 KiB window
  localparam logic [31:0] PERIPH_BASE = 32'h4000_0000;
  localparam logic [31:0] PERIPH_MASK = 32'hFFFE_0000;  // 128 KiB window

  // Peripheral pages (4 KiB each) inside PERIPH window: addr[16:12]
  localparam int PG_SYSCTRL = 0;   // 0x4000_0000
  localparam int PG_INTC    = 1;   // 0x4000_1000
  localparam int PG_TIMER   = 2;   // 0x4000_2000
  localparam int PG_UART    = 3;   // 0x4000_3000
  localparam int PG_SPI     = 4;   // 0x4000_4000
  localparam int PG_GPIO    = 5;   // 0x4000_5000
  localparam int PG_VE      = 16;  // 0x4001_0000
  localparam int PG_TE      = 17;  // 0x4001_1000
  localparam int NUM_PAGES  = 32;

  // ---------------------------------------------------------------- bus masters
  localparam int M_DBG  = 0;   // JTAG system-bus access (highest priority)
  localparam int M_CPUD = 1;   // CPU data port
  localparam int M_CPUI = 2;   // CPU instruction port (lowest priority)
  localparam int NUM_MASTERS = 3;

  // ---------------------------------------------------------------- interrupts
  localparam int IRQ_UART   = 0;
  localparam int IRQ_SPI    = 1;
  localparam int IRQ_GPIO   = 2;
  localparam int IRQ_VE     = 3;
  localparam int IRQ_TE     = 4;
  localparam int IRQ_MBIST  = 5;
  localparam int IRQ_BUSERR = 6;
  localparam int IRQ_DBG    = 7;   // JTAG doorbell
  localparam int NUM_IRQ    = 8;

  // ---------------------------------------------------------------- vector ops
  localparam logic [3:0] VOP_ADD = 4'd0;
  localparam logic [3:0] VOP_SUB = 4'd1;
  localparam logic [3:0] VOP_MUL = 4'd2;
  localparam logic [3:0] VOP_MIN = 4'd3;
  localparam logic [3:0] VOP_MAX = 4'd4;
  localparam logic [3:0] VOP_AND = 4'd5;
  localparam logic [3:0] VOP_OR  = 4'd6;
  localparam logic [3:0] VOP_XOR = 4'd7;
  localparam logic [3:0] VOP_SLL = 4'd8;
  localparam logic [3:0] VOP_SRA = 4'd9;
  localparam logic [3:0] VOP_SRL = 4'd10;
  localparam logic [3:0] VOP_DOT = 4'd11;
  localparam logic [3:0] VOP_LAST = 4'd11;

  // Accelerator error codes (STATUS[7:4])
  localparam logic [3:0] AERR_NONE     = 4'd0;
  localparam logic [3:0] AERR_ALIGN    = 4'd1;
  localparam logic [3:0] AERR_RANGE    = 4'd2;
  localparam logic [3:0] AERR_BADOP    = 4'd3;
  localparam logic [3:0] AERR_BUSY     = 4'd4;

endpackage

`default_nettype wire
