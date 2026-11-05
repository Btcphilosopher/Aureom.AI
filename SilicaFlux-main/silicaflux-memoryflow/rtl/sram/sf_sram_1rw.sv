// =============================================================================
// SilicaFlux MemoryFlow :: sf_sram_1rw  -- logical SRAM abstraction layer
// Every SRAM in MemoryFlow instantiates THIS module, never a primitive.
//
//   IMPL = 0 : inferred array (sf_sram_1rw_inferred) -- FPGA + RTL simulation
//   IMPL = 1 : foundry-macro tiling -- the logical LANES*LANE_W x DEPTH array
//              is built from a grid of sf_macro_1rw_leaf instances of size
//              MACRO_W x MACRO_D (column tiling for width, row tiling for depth
//              with a registered output mux).  Unused padding bits are tied.
//
// Inferred arrays are never silently assumed to become hard macros: selecting
// a macro is an explicit IMPL=1 + MACRO_W/MACRO_D decision, and the tiling is
// mirrored by memoryflow.models.area.plan_macro_tiling() for area reports.
// Behaviour is identical for both IMPLs (1-cycle read, rdata holds), which the
// unit testbench checks by running both side by side.
// Classification: SYNTHESIZABLE (IMPL=1 requires macro views / blackbox)
// =============================================================================
`default_nettype none

module sf_sram_1rw #(
  parameter int LANE_W  = 8,
  parameter int LANES   = 8,
  parameter int DEPTH   = 1024,
  parameter int IMPL    = 0,
  parameter int MACRO_W = 72,
  parameter int MACRO_D = 512,     // must be a power of two when IMPL = 1
  // test-only fault model, forwarded to the inferred implementation
  parameter bit SA_EN   = 1'b0,
  parameter int SA_ADDR = 0,
  parameter int SA_BIT  = 0,
  parameter bit SA_VAL  = 1'b0,
  localparam int WIDTH  = LANE_W * LANES,
  localparam int AW     = (DEPTH > 1) ? $clog2(DEPTH) : 1
) (
  input  logic             clk,
  input  logic             ce,
  input  logic             we,
  input  logic [LANES-1:0] lane_we,
  input  logic [AW-1:0]    addr,
  input  logic [WIDTH-1:0] wdata,
  output logic [WIDTH-1:0] rdata,
  input  logic             lp_sleep,     // low-power hooks (macros only)
  input  logic             lp_shutdown
);

  generate
    if (IMPL == 0) begin : g_inferred
      sf_sram_1rw_inferred #(
        .LANE_W(LANE_W), .LANES(LANES), .DEPTH(DEPTH),
        .SA_EN(SA_EN), .SA_ADDR(SA_ADDR), .SA_BIT(SA_BIT), .SA_VAL(SA_VAL)
      ) u_mem (
        .clk, .ce, .we, .lane_we, .addr, .wdata, .rdata
      );
      wire unused_lp = lp_sleep ^ lp_shutdown;
    end else begin : g_macro
      localparam int NC  = (WIDTH + MACRO_W - 1) / MACRO_W;   // macro columns
      localparam int NR  = (DEPTH + MACRO_D - 1) / MACRO_D;   // macro rows
      localparam int PWD = NC * MACRO_W;                      // padded width
      localparam int MAW = (MACRO_D > 1) ? $clog2(MACRO_D) : 1;
      localparam int RW  = (NR > 1) ? $clog2(NR) : 1;

      // bit-level write enables (active high), padded
      logic [PWD-1:0] bwe, wd_pad;
      always_comb begin
        bwe    = '0;
        wd_pad = '0;
        for (int b = 0; b < WIDTH; b++) begin
          bwe[b]    = lane_we[b / LANE_W];
          wd_pad[b] = wdata[b];
        end
      end

      logic [RW-1:0]  row, row_q;
      logic [MAW-1:0] laddr;
      if (NR > 1) begin : g_rowsel
        assign row   = RW'(addr >> MAW);
        assign laddr = addr[MAW-1:0];
      end else begin : g_onerow
        assign row   = '0;
        assign laddr = MAW'(addr);
      end

      always_ff @(posedge clk) begin
        if (ce && !we) row_q <= row;
      end

      logic [PWD-1:0] q_row [NR];
      for (genvar r = 0; r < NR; r++) begin : g_r
        wire sel = ce && (row == RW'(r));
        for (genvar c = 0; c < NC; c++) begin : g_c
          (* keep *)            // hard macro: never optimise away
          sf_macro_1rw_leaf #(.W(MACRO_W), .D(MACRO_D)) u_macro (
            .CLK  (clk),
            .CEN  (~sel),
            .GWEN (~we),
            .WEN  (~bwe[c*MACRO_W +: MACRO_W]),
            .A    (laddr),
            .D_IN (wd_pad[c*MACRO_W +: MACRO_W]),
            .Q    (q_row[r][c*MACRO_W +: MACRO_W]),
            .SLP  (lp_sleep),
            .SD   (lp_shutdown)
          );
        end
      end

      /* verilator lint_off UNUSEDSIGNAL */
      logic [PWD-1:0] q_sel;           // padding bits unused
      /* verilator lint_on UNUSEDSIGNAL */
      always_comb begin
        q_sel = q_row[0];
        for (int r = 1; r < NR; r++) if (row_q == RW'(r)) q_sel = q_row[r];
      end
      assign rdata = q_sel[WIDTH-1:0];
    end
  endgenerate

endmodule

`default_nettype wire
