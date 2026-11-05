// =============================================================================
// SilicaFlux MemoryFlow :: sf_sram_1r1w_inferred
// Simple dual-port (1 read port + 1 write port, common clock) synchronous SRAM.
// Matches the "two-port register-file / 2P SRAM" macro class.
//   * Read-during-write to the same address returns the OLD data (read-first).
//   * Per-lane write enables.
// Classification: SYNTHESIZABLE (inferred memory)
// =============================================================================
`default_nettype none

module sf_sram_1r1w_inferred #(
  parameter int LANE_W = 8,
  parameter int LANES  = 8,
  parameter int DEPTH  = 1024,
  localparam int WIDTH = LANE_W * LANES,
  localparam int AW    = (DEPTH > 1) ? $clog2(DEPTH) : 1
) (
  input  logic             clk,
  // write port
  input  logic             we,
  input  logic [LANES-1:0] lane_we,
  input  logic [AW-1:0]    waddr,
  input  logic [WIDTH-1:0] wdata,
  // read port
  input  logic             re,
  input  logic [AW-1:0]    raddr,
  output logic [WIDTH-1:0] rdata
);
  logic [WIDTH-1:0] mem [DEPTH];

  always_ff @(posedge clk) begin
    if (we) begin
      for (int l = 0; l < LANES; l++) begin
        if (lane_we[l]) mem[waddr][l*LANE_W +: LANE_W] <= wdata[l*LANE_W +: LANE_W];
      end
    end
  end

  always_ff @(posedge clk) begin
    if (re) rdata <= mem[raddr];
  end

endmodule

`default_nettype wire
