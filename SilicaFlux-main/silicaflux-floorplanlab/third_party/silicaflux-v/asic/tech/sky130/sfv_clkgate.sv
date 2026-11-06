// SilicaFlux-V ICG for SkyWater sky130_fd_sc_hd: scan-enabled latch clock gate.
module sfv_clkgate (input wire logic clk, input wire logic en, input wire logic test_en,
                    output logic gclk);
  sky130_fd_sc_hd__sdlclkp_1 u_icg (.CLK(clk), .GATE(en), .SCE(test_en), .GCLK(gclk));
endmodule
