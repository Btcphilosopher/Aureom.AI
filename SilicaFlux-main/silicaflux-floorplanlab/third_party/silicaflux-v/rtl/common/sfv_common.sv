// =============================================================================
// SilicaFlux-V :: common primitives
//   sfv_sync      N-flop level synchroniser (async input -> clk domain)
//   sfv_rst_sync  reset synchroniser: async assert, sync de-assert, test bypass
//   sfv_fifo      small synchronous FIFO (flop based, power-of-two depth)
//
// Technology-specific cells (clock gate, synchroniser cell) are isolated in
// sfv_clkgate.sv / tech/<pdk>/ so that a foundry library cell can be swapped
// in without touching functional RTL.
// =============================================================================
`default_nettype none

// -----------------------------------------------------------------------------
// Level synchroniser.  Use only for single-bit, quasi-static or toggle/handshake
// signals.  The first stage is the metastability-capturing flop; a production
// flow should replace this with the library's dedicated synchroniser cell
// (dont_touch, MTBF characterised) -- see docs/CLOCK_RESET.md.
// -----------------------------------------------------------------------------
module sfv_sync #(
  parameter int STAGES = 2,
  parameter bit RESET_VAL = 1'b0
) (
  input  wire logic clk,
  input  wire logic rst_n,
  input  wire logic d,
  output logic      q
);
  logic [STAGES-1:0] s;
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) s <= {STAGES{RESET_VAL}};
    else        s <= {s[STAGES-2:0], d};
  end
  assign q = s[STAGES-1];
endmodule

// -----------------------------------------------------------------------------
// Reset synchroniser.  rst_n_o asserts asynchronously with rst_ni and
// de-asserts synchronously to clk after STAGES rising edges.
// In scan/test mode the output is driven directly by the reset pin so that the
// tester controls every asynchronous reset (DFT rule DFT-R1).
// -----------------------------------------------------------------------------
module sfv_rst_sync #(
  parameter int STAGES = 2
) (
  input  wire logic clk,
  input  wire logic rst_ni,
  input  wire logic test_mode,
  input  wire logic test_rst_ni,
  output logic      rst_no
);
  logic [STAGES-1:0] s;
  always_ff @(posedge clk or negedge rst_ni) begin
    if (!rst_ni) s <= '0;
    else         s <= {s[STAGES-2:0], 1'b1};
  end
  assign rst_no = test_mode ? test_rst_ni : s[STAGES-1];
endmodule

// -----------------------------------------------------------------------------
// Synchronous FIFO.  Storage flops are not reset (datapath); pointers are.
// push is ignored when full, pop is ignored when empty (callers check flags).
// -----------------------------------------------------------------------------
module sfv_fifo #(
  parameter int WIDTH = 8,
  parameter int DEPTH = 4            // power of two, >= 2
) (
  input  wire logic             clk,
  input  wire logic             rst_n,
  input  wire logic             clr,
  input  wire logic             push,
  input  wire logic [WIDTH-1:0] wdata,
  input  wire logic             pop,
  output logic [WIDTH-1:0]      rdata,
  output logic                  empty,
  output logic                  full,
  output logic [$clog2(DEPTH):0] count
);
  localparam int AW = $clog2(DEPTH);
  logic [WIDTH-1:0] mem [0:DEPTH-1];
  logic [AW:0]      wp, rp;
  wire do_push = push && !full;
  wire do_pop  = pop  && !empty;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      wp <= '0;
      rp <= '0;
    end else if (clr) begin
      wp <= '0;
      rp <= '0;
    end else begin
      if (do_push) wp <= wp + 1'b1;
      if (do_pop)  rp <= rp + 1'b1;
    end
  end

  always_ff @(posedge clk) begin
    if (do_push) mem[wp[AW-1:0]] <= wdata;
  end

  assign rdata = mem[rp[AW-1:0]];
  assign count = wp - rp;
  assign empty = (wp == rp);
  assign full  = (wp[AW-1:0] == rp[AW-1:0]) && (wp[AW] != rp[AW]);
endmodule

`default_nettype wire
