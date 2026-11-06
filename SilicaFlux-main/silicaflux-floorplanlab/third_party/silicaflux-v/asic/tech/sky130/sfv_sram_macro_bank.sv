// =============================================================================
// SilicaFlux-V SRAM bank on OpenRAM sky130_sram_1rw1r_128x256_8 macros.
// Logical bank: DEPTH x 32 bit, byte enables, 1-cycle read (sfv_sram_sp).
// Mapping: 4 words folded per 128-bit macro row (byte write mask selects the
// word lane), depth tiled over NM macros, registered macro/lane select on the
// read path.  Port 1 (read-only) of the 1RW1R macro is unused and disabled.
// =============================================================================
module sfv_sram_macro_bank #(
  parameter int DEPTH = 8192,
  localparam int AW = $clog2(DEPTH)
) (
  input  wire logic          clk,
  input  wire logic          ce,
  input  wire logic          we,
  input  wire logic [3:0]    be,
  input  wire logic [AW-1:0] addr,
  input  wire logic [31:0]   wdata,
  output logic [31:0]        rdata
);
  localparam int MD = 256, MAW = 8, F = 4, FW = 2;
  localparam int ROWS = DEPTH / F;
  localparam int NM = (ROWS + MD - 1) / MD;
  localparam int SW = (NM > 1) ? $clog2(NM) : 1;
  wire [FW-1:0]  lane = addr[FW-1:0];
  wire [MAW-1:0] row  = addr[FW+MAW-1:FW];
  logic [SW-1:0] msel;
  if (NM > 1) begin : g_msel
    assign msel = addr[AW-1:FW+MAW];
  end else begin : g_one
    assign msel = '0;
  end
  logic [15:0] wmask;
  always_comb begin
    wmask = 16'd0;
    wmask[lane*4 +: 4] = be;
  end
  logic [FW-1:0] lane_q;
  logic [SW-1:0] msel_q;
  always_ff @(posedge clk) if (ce && !we) begin lane_q <= lane; msel_q <= msel; end
  logic [127:0] dout [0:NM-1];
  for (genvar m = 0; m < NM; m++) begin : g_m
    logic [127:0] unused_dout1;
    sky130_sram_1rw1r_128x256_8 u_mac (
      .clk0(clk), .csb0(!(ce && msel == SW'(m))), .web0(!we), .wmask0(wmask),
      .addr0(row), .din0({4{wdata}}), .dout0(dout[m]),
      .clk1(1'b0), .csb1(1'b1), .addr1(8'd0), .dout1(unused_dout1));
  end
  assign rdata = dout[msel_q][lane_q*32 +: 32];
endmodule
