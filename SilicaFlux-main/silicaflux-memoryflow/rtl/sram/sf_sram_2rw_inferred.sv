// =============================================================================
// SilicaFlux MemoryFlow :: sf_sram_2rw_inferred
// True dual-port (2RW, common clock) synchronous SRAM.  Either port may read
// or write each cycle.
//   * Same-address write/write from both ports in one cycle is a usage error
//     (undefined in real macros) -- flagged by a simulation assertion.
//   * Same-address read on one port + write on the other returns OLD data.
// Note: true dual-port macros cost ~1.6-2x the area of 1RW at mature nodes;
// the MemoryFlow area model (memoryflow.models.area) accounts for this.
// Classification: SYNTHESIZABLE (inferred memory)
// =============================================================================
`default_nettype none

module sf_sram_2rw_inferred #(
  parameter int LANE_W = 8,
  parameter int LANES  = 8,
  parameter int DEPTH  = 1024,
  localparam int WIDTH = LANE_W * LANES,
  localparam int AW    = (DEPTH > 1) ? $clog2(DEPTH) : 1
) (
  input  logic             clk,
  input  logic             a_ce,
  input  logic             a_we,
  input  logic [LANES-1:0] a_lane_we,
  input  logic [AW-1:0]    a_addr,
  input  logic [WIDTH-1:0] a_wdata,
  output logic [WIDTH-1:0] a_rdata,
  input  logic             b_ce,
  input  logic             b_we,
  input  logic [LANES-1:0] b_lane_we,
  input  logic [AW-1:0]    b_addr,
  input  logic [WIDTH-1:0] b_wdata,
  output logic [WIDTH-1:0] b_rdata
);
  logic [WIDTH-1:0] mem [DEPTH];

  always_ff @(posedge clk) begin
    if (a_ce && !a_we) a_rdata <= mem[a_addr];
    if (b_ce && !b_we) b_rdata <= mem[b_addr];
    if (a_ce && a_we) begin
      for (int l = 0; l < LANES; l++)
        if (a_lane_we[l]) mem[a_addr][l*LANE_W +: LANE_W] <= a_wdata[l*LANE_W +: LANE_W];
    end
    if (b_ce && b_we) begin
      for (int l = 0; l < LANES; l++)
        if (b_lane_we[l]) mem[b_addr][l*LANE_W +: LANE_W] <= b_wdata[l*LANE_W +: LANE_W];
    end
  end

`ifndef SYNTHESIS
  // pragma translate_off
  always_ff @(posedge clk) begin
    if (a_ce && a_we && b_ce && b_we && (a_addr == b_addr) && |(a_lane_we & b_lane_we))
      $error("sf_sram_2rw_inferred: write/write collision at addr %0d", a_addr);
  end
  // pragma translate_on
`endif

endmodule

`default_nettype wire
