// =============================================================================
// SilicaFlux MemoryFlow :: sf_sram_1rw_inferred
// Single-port (1RW) synchronous SRAM, written in the canonical inference
// template recognised by FPGA tools (Xilinx/Intel/Lattice BRAM, Yosys memory
// mapping) and usable for initial RTL simulation.
//
//   * WIDTH = LANES * LANE_W, with one write-enable per lane (byte enables when
//     LANE_W = 8, or 9 when a parity bit rides with each byte).
//   * Synchronous read, 1-cycle latency; rdata HOLDS when not reading.
//   * A write cycle does not update rdata (no write-through).
//
// IMPORTANT: this is NOT a hard macro.  An ASIC flow will turn this array into
// flops + muxes (huge).  For silicon, select IMPL=1 in sf_sram_1rw, which maps
// the logical array onto foundry macro instances (rtl/sram/sf_sram_1rw.sv).
//
// Test-only stuck-at fault injection parameters (SA_EN) model a defective bit
// cell on the read path so MBIST can be verified.  Default: disabled.
// Classification: SYNTHESIZABLE (inferred memory)
// =============================================================================
`default_nettype none

module sf_sram_1rw_inferred #(
  parameter int LANE_W  = 8,
  parameter int LANES   = 8,
  parameter int DEPTH   = 1024,
  // --- test-only fault model (sim / MBIST verification) ---
  parameter bit SA_EN   = 1'b0,
  parameter int SA_ADDR = 0,
  parameter int SA_BIT  = 0,
  parameter bit SA_VAL  = 1'b0,
  localparam int WIDTH  = LANE_W * LANES,
  localparam int AW     = (DEPTH > 1) ? $clog2(DEPTH) : 1
) (
  input  logic             clk,
  input  logic             ce,        // chip enable (active high)
  input  logic             we,        // 1 = write, 0 = read
  input  logic [LANES-1:0] lane_we,   // per-lane write enable
  input  logic [AW-1:0]    addr,
  input  logic [WIDTH-1:0] wdata,
  output logic [WIDTH-1:0] rdata
);
  logic [WIDTH-1:0] mem [DEPTH];
  logic [WIDTH-1:0] q;

  always_ff @(posedge clk) begin
    if (ce) begin
      if (we) begin
        for (int l = 0; l < LANES; l++) begin
          if (lane_we[l]) mem[addr][l*LANE_W +: LANE_W] <= wdata[l*LANE_W +: LANE_W];
        end
      end else begin
        q <= mem[addr];
      end
    end
  end

  // Stuck-at fault overlay (constant-false when SA_EN == 0; optimised away).
  logic sa_hit_q;
  always_ff @(posedge clk) begin
    if (ce && !we) sa_hit_q <= SA_EN && (addr == AW'(SA_ADDR));
  end

  always_comb begin
    rdata = q;
    if (SA_EN && sa_hit_q) rdata[SA_BIT] = SA_VAL;
  end

endmodule

`default_nettype wire
