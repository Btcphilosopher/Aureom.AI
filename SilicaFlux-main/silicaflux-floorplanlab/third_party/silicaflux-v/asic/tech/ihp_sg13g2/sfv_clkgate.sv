// SilicaFlux-V ICG for IHP SG13G2: scan-enabled latch clock gate.
module sfv_clkgate (input wire logic clk, input wire logic en, input wire logic test_en,
                    output logic gclk);
  sg13g2_slgcp_1 u_icg (.CLK(clk), .GATE(en), .SCE(test_en), .GCLK(gclk));
endmodule
