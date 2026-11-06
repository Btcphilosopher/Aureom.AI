// =============================================================================
// SilicaFlux-V :: sfv_sram_sp -- single-port (1RW) SRAM abstraction
//
// Contract (identical for every implementation):
//   * 32-bit word, 4 byte write enables, DEPTH words, synchronous.
//   * ce & we  : write enabled bytes at addr.
//   * ce & !we : read; rdata valid in the NEXT cycle.  rdata is only
//                guaranteed in that cycle (no hold / no write-through
//                assumption -- matches foundry compiler and OpenRAM macros).
//
// Implementations
//   default            behavioural array in the canonical inference template
//                      (simulation + FPGA block RAM: Lattice EBR / Xilinx BRAM).
//                      NOT for ASIC: it would synthesise to flops.
//   SFV_SRAM_MACRO     instantiates sfv_sram_macro_bank, provided per PDK by
//                      asic/tech/<pdk>/sfv_sram_macro_bank.sv, which tiles the
//                      foundry/OpenRAM macros and owns the pin mapping.
// Derivation: interface contract and inference template follow the
// repository's memoryflow sf_sram_1rw / sf_sram_1rw_inferred.
// =============================================================================
`default_nettype none

module sfv_sram_sp #(
  parameter int DEPTH = 1024,
  localparam int AW = (DEPTH > 1) ? $clog2(DEPTH) : 1
) (
  input  wire logic          clk,
  input  wire logic          ce,
  input  wire logic          we,
  input  wire logic [3:0]    be,
  input  wire logic [AW-1:0] addr,
  input  wire logic [31:0]   wdata,
  output logic [31:0]        rdata
);
`ifdef SFV_SRAM_MACRO
  sfv_sram_macro_bank #(.DEPTH(DEPTH)) u_macro (
    .clk, .ce, .we, .be, .addr, .wdata, .rdata
  );
`else
  logic [31:0] mem [0:DEPTH-1];
  logic [31:0] q;
  always_ff @(posedge clk) begin
    if (ce) begin
      if (we) begin
        if (be[0]) mem[addr][7:0]   <= wdata[7:0];
        if (be[1]) mem[addr][15:8]  <= wdata[15:8];
        if (be[2]) mem[addr][23:16] <= wdata[23:16];
        if (be[3]) mem[addr][31:24] <= wdata[31:24];
      end else begin
        q <= mem[addr];
      end
    end
  end
`ifndef SYNTHESIS
  // Simulation-only stuck-at fault on the read path, armed by a testbench
  // through hierarchical assignment (MBIST / POST fault-detection tests).
  // Excluded from every synthesis flow (SYNTHESIS is defined there).
  logic        fi_en   = 1'b0;
  logic [31:0] fi_addr = 32'd0;
  logic [4:0]  fi_bit  = 5'd0;
  logic        fi_val  = 1'b0;
  logic        fi_hit;
  always_ff @(posedge clk) if (ce && !we) fi_hit <= fi_en && ({{(32-AW){1'b0}}, addr} == fi_addr);
  always_comb begin
    rdata = q;
    if (fi_hit) rdata[fi_bit] = fi_val;
  end
`else
  assign rdata = q;
`endif
`endif
endmodule

`default_nettype wire
