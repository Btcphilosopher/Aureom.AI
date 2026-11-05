// =============================================================================
// SilicaFlux MemoryFlow :: sf_macro_1rw_leaf  (BEHAVIOURAL MODEL - NOT RTL)
// Generic stand-in for ONE foundry-compiled single-port SRAM macro instance.
// Pin semantics mirror the common compiler convention (active-low controls):
//   CLK, CEN (chip enable_n), GWEN (global write enable_n),
//   WEN[W-1:0] (bit write enable_n), A, D, Q,
//   SLP (light sleep, retains data, no access), SD (shut down, data lost).
//
// In a real tape-out flow this file is REPLACED by the memory compiler's
// Verilog view + LIB/LEF/GDS for the chosen bitcell (HD/HC), Vt and mux.
// Pin names differ per foundry -- only sf_sram_1rw (IMPL=1) instantiates this
// leaf, so a foundry port-map change is confined to one file.
// For synthesis, rtl/macro_stubs/sf_macro_1rw_leaf_bb.sv supplies a blackbox.
// Classification: BEHAVIOURAL (simulation model of a hard macro)
// =============================================================================
`default_nettype none

module sf_macro_1rw_leaf #(
  parameter int W  = 72,
  parameter int D  = 1024,
  localparam int AW = (D > 1) ? $clog2(D) : 1
) (
  input  logic          CLK,
  input  logic          CEN,
  input  logic          GWEN,
  input  logic [W-1:0]  WEN,
  input  logic [AW-1:0] A,
  input  logic [W-1:0]  D_IN,
  output logic [W-1:0]  Q,
  input  logic          SLP,
  input  logic          SD
);
  logic [W-1:0] mem [D];
  logic [W-1:0] wbits;

  always_comb begin
    for (int b = 0; b < W; b++) wbits[b] = WEN[b] ? mem[A][b] : D_IN[b];
  end

  always @(posedge CLK) begin
    if (SD) begin
      // shutdown: array contents are not retained (blocking: behavioural only)
      /* verilator lint_off BLKSEQ */
      for (int i = 0; i < D; i++) mem[i] = 'x;
      /* verilator lint_on BLKSEQ */
      Q <= 'x;
    end else if (!SLP && !CEN) begin
      if (!GWEN) mem[A] <= wbits;
      else       Q      <= mem[A];
    end
  end

endmodule

`default_nettype wire
