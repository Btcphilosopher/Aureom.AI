// =============================================================================
// SilicaFlux-V SRAM bank on IHP SG13G2 RM_IHPSG13_1P_*x64 compiled macros.
// Logical bank: DEPTH x 32 bit, byte enables, 1-cycle read (sfv_sram_sp).
// Mapping: 2 words folded per 64-bit macro row (bit mask selects the word
// lane); macro size chosen from the folded depth (2048/1024/512/256 rows);
// depth tiled over NM macros.  The macro's built-in BIST port is tied off:
// SilicaFlux-V's MBIST drives the functional port through sfv_sram_slave.
// A_DLY must be tied high (IHP datasheet / model check).
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
  localparam int ROWS = DEPTH / 2;
  localparam int MD   = (ROWS >= 2048) ? 2048 : ROWS;      // 2048/1024/512/256
  localparam int MAW  = $clog2(MD);
  localparam int NM   = (ROWS + MD - 1) / MD;
  localparam int SW   = (NM > 1) ? $clog2(NM) : 1;
  wire           lane = addr[0];
  wire [MAW-1:0] row  = addr[MAW:1];
  logic [SW-1:0] msel;
  if (NM > 1) begin : g_msel
    assign msel = addr[AW-1:MAW+1];
  end else begin : g_one
    assign msel = '0;
  end
  logic [63:0] bm;
  always_comb begin
    bm = 64'd0;
    for (int b = 0; b < 4; b++) bm[lane*32 + b*8 +: 8] = {8{be[b]}};
  end
  logic          lane_q;
  logic [SW-1:0] msel_q;
  always_ff @(posedge clk) if (ce && !we) begin lane_q <= lane; msel_q <= msel; end
  logic [63:0] dout [0:NM-1];
  for (genvar m = 0; m < NM; m++) begin : g_m
    wire men = ce && (msel == SW'(m));
    if (MD == 2048) begin : g2k
      RM_IHPSG13_1P_2048x64_c2_bm_bist u_mac (
        .A_CLK(clk), .A_MEN(men), .A_WEN(we), .A_REN(!we), .A_ADDR(row), .A_DIN({2{wdata}}),
        .A_DLY(1'b1), .A_DOUT(dout[m]), .A_BM(bm),
        .A_BIST_CLK(1'b0), .A_BIST_EN(1'b0), .A_BIST_MEN(1'b0), .A_BIST_WEN(1'b0),
        .A_BIST_REN(1'b0), .A_BIST_ADDR('0), .A_BIST_DIN(64'd0), .A_BIST_BM(64'd0));
    end else if (MD == 1024) begin : g1k
      RM_IHPSG13_1P_1024x64_c2_bm_bist u_mac (
        .A_CLK(clk), .A_MEN(men), .A_WEN(we), .A_REN(!we), .A_ADDR(row), .A_DIN({2{wdata}}),
        .A_DLY(1'b1), .A_DOUT(dout[m]), .A_BM(bm),
        .A_BIST_CLK(1'b0), .A_BIST_EN(1'b0), .A_BIST_MEN(1'b0), .A_BIST_WEN(1'b0),
        .A_BIST_REN(1'b0), .A_BIST_ADDR('0), .A_BIST_DIN(64'd0), .A_BIST_BM(64'd0));
    end else if (MD == 512) begin : g512
      RM_IHPSG13_1P_512x64_c2_bm_bist u_mac (
        .A_CLK(clk), .A_MEN(men), .A_WEN(we), .A_REN(!we), .A_ADDR(row), .A_DIN({2{wdata}}),
        .A_DLY(1'b1), .A_DOUT(dout[m]), .A_BM(bm),
        .A_BIST_CLK(1'b0), .A_BIST_EN(1'b0), .A_BIST_MEN(1'b0), .A_BIST_WEN(1'b0),
        .A_BIST_REN(1'b0), .A_BIST_ADDR('0), .A_BIST_DIN(64'd0), .A_BIST_BM(64'd0));
    end else begin : g256
      RM_IHPSG13_1P_256x64_c2_bm_bist u_mac (
        .A_CLK(clk), .A_MEN(men), .A_WEN(we), .A_REN(!we), .A_ADDR(row), .A_DIN({2{wdata}}),
        .A_DLY(1'b1), .A_DOUT(dout[m]), .A_BM(bm),
        .A_BIST_CLK(1'b0), .A_BIST_EN(1'b0), .A_BIST_MEN(1'b0), .A_BIST_WEN(1'b0),
        .A_BIST_REN(1'b0), .A_BIST_ADDR('0), .A_BIST_DIN(64'd0), .A_BIST_BM(64'd0));
    end
  end
  assign rdata = dout[msel_q][lane_q*32 +: 32];
endmodule
