// =============================================================================
// SilicaFlux DataFabric :: dma_fifo -- synchronous flop FIFO for the buffered DMA
// Power-of-two DEPTH >= 2, first-word fall-through (rdata = head, stable until
// pop).  push/pop are only issued by the engine under credit, so push never
// hits a full FIFO and pop never an empty one (asserted in simulation).
// Storage flops are not reset (datapath); pointers are.  For DEPTH * WIDTH
// large enough to justify a macro, replace the array with a sramlib sram_1r1w
// (2-cycle head latency then needs a prefetch register).
// =============================================================================
`default_nettype none

module dma_fifo #(
  parameter int WIDTH = 32,
  parameter int DEPTH = 4,
  localparam int AW   = (DEPTH > 1) ? $clog2(DEPTH) : 1
) (
  input  wire logic             clk,
  input  wire logic             rst_n,
  input  wire logic             clr,
  input  wire logic             push,
  input  wire logic [WIDTH-1:0] wdata,
  input  wire logic             pop,
  output logic [WIDTH-1:0]      rdata,
  output logic [AW:0]           count
);
  logic [WIDTH-1:0] mem [0:DEPTH-1];
  logic [AW:0]      wp, rp;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      wp <= '0;
      rp <= '0;
    end else if (clr) begin
      wp <= '0;
      rp <= '0;
    end else begin
      if (push) wp <= wp + 1'b1;
      if (pop)  rp <= rp + 1'b1;
    end
  end
  always_ff @(posedge clk) if (push && !clr) mem[wp[AW-1:0]] <= wdata;

  assign rdata = mem[rp[AW-1:0]];
  assign count = wp - rp;

`ifndef SYNTHESIS
  // simulation-only usage check (samples rst_n as data)
  /* verilator lint_off SYNCASYNCNET */
  always_ff @(posedge clk) if (rst_n && !clr) begin
    if (push && !pop && count == (AW+1)'(DEPTH)) $error("dma_fifo: push while full");
    if (pop && count == '0) $error("dma_fifo: pop while empty");
  end
  /* verilator lint_on SYNCASYNCNET */
`endif
endmodule

`default_nettype wire
