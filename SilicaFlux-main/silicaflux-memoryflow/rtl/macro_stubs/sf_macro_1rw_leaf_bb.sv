// =============================================================================
// SilicaFlux MemoryFlow :: sf_macro_1rw_leaf (SYNTHESIS BLACKBOX)
// Read by synthesis scripts INSTEAD of the behavioural model so that the macro
// is kept as a hard instance (never flattened into flops).
// Classification: BLACKBOX (placeholder for foundry macro)
// =============================================================================
`default_nettype none

(* blackbox *)
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
endmodule

`default_nettype wire
