// =============================================================================
// SilicaFlux-V :: sfv_clkgate  -- integrated clock gate (ICG) WRAPPER
//
// Generic behavioural model of a positive-edge ICG:
//   * enable latch is transparent while clk is LOW, so `en` / `test_en` need
//     only meet setup to the next RISING edge (full-cycle path, no glitches);
//   * gclk = clk & latched_enable.
// test_en (scan mode / clock-test override) forces the clock on.
//
// This is the ONLY intentional latch in the design.  Lint/synthesis reports
// whitelist exactly this instance type (scripts/check_latches.py).
//
// Target substitution (same module name, same ports):
//   SFV_NO_CLOCK_GATE   -> gclk = clk (FPGA builds: gating is a pure power
//                          optimisation; functional behaviour is identical
//                          because every gated block also qualifies its flops)
//   asic/tech/sky130/sfv_clkgate.sv     -> sky130_fd_sc_hd__sdlclkp_1
//   asic/tech/ihp_sg13g2/sfv_clkgate.sv -> sg13g2_slgcp_1
// =============================================================================
`default_nettype none

module sfv_clkgate (
  input  wire logic clk,
  input  wire logic en,
  input  wire logic test_en,
  output logic      gclk
);
`ifdef SFV_NO_CLOCK_GATE
  assign gclk = clk;
  wire unused_ok = en ^ test_en;
`else
  logic en_l;
  /* verilator lint_off LATCH */
  always_latch begin
    if (!clk) en_l = en | test_en;
  end
  /* verilator lint_on LATCH */
  assign gclk = clk & en_l;
`endif
endmodule

`default_nettype wire
