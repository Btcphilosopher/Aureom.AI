// =============================================================================
// SilicaFlux-V :: memory bus slaves
//   sfv_sram_slave  SFB slave for one SRAM bank, with MBIST collar
//   sfv_bootrom     SFB slave for the mask-programmed boot ROM
// =============================================================================
`default_nettype none

// -----------------------------------------------------------------------------
// One SRAM bank on the crossbar.  1 cycle latency, back-to-back accesses.
// MBIST collar: while bist_en=1 the bank belongs to the MBIST controller and
// functional requests are not granted (deterministic: firmware must not
// touch a bank under test; the ROM boot code runs MBIST before using SRAM).
// -----------------------------------------------------------------------------
module sfv_sram_slave #(
  parameter int DEPTH = 8192,
  localparam int AW = $clog2(DEPTH)
) (
  input  wire logic          clk,
  input  wire logic          rst_n,
  input  wire logic          req,
  output logic               gnt,
  input  wire logic [31:0]   addr,
  input  wire logic          we,
  input  wire logic [3:0]    be,
  input  wire logic [31:0]   wdata,
  output logic               rvalid,
  output logic [31:0]        rdata,
  output logic               err,
  // MBIST test port
  input  wire logic          bist_en,
  input  wire logic          bist_ce,
  input  wire logic          bist_we,
  input  wire logic [AW-1:0] bist_addr,
  input  wire logic [31:0]   bist_wdata,
  output logic [31:0]        bist_rdata
);
  logic          ce, mwe;
  logic [3:0]    mbe;
  logic [AW-1:0] maddr;
  logic [31:0]   mwdata, q;

  assign gnt = !bist_en;
  always_comb begin
    if (bist_en) begin
      ce = bist_ce; mwe = bist_we; mbe = 4'b1111; maddr = bist_addr; mwdata = bist_wdata;
    end else begin
      ce = req; mwe = we; mbe = be; maddr = addr[AW+1:2]; mwdata = wdata;
    end
  end

  sfv_sram_sp #(.DEPTH(DEPTH)) u_ram (
    .clk, .ce, .we(mwe), .be(mbe), .addr(maddr), .wdata(mwdata), .rdata(q)
  );

  logic rd_q;
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      rvalid <= 1'b0;
      rd_q   <= 1'b0;
    end else begin
      rvalid <= req && gnt;
      rd_q   <= req && gnt && !we;
    end
  end
  assign rdata      = rd_q ? q : 32'd0;
  assign err        = 1'b0;
  assign bist_rdata = q;
endmodule

// -----------------------------------------------------------------------------
// Boot ROM.  The image is a generated combinational module
// (sfv_bootrom_image, from firmware/bootrom via scripts/gen_rom.py) addressed
// by a registered word address -- synthesises to logic, or is replaced by a
// foundry via/metal-programmable ROM macro of the same contract.
// Writes return a bus error.
// -----------------------------------------------------------------------------
module sfv_bootrom #(
  parameter int WORDS = 1024,
  localparam int AW = $clog2(WORDS)
) (
  input  wire logic        clk,
  input  wire logic        rst_n,
  input  wire logic        req,
  output logic             gnt,
  input  wire logic [31:0] addr,
  input  wire logic        we,
  input  wire logic [3:0]  be,
  input  wire logic [31:0] wdata,
  output logic             rvalid,
  output logic [31:0]      rdata,
  output logic             err
);
  logic [AW-1:0] a_q;
  logic          rd_q, range_q;
  logic [31:0]   img;
  wire unused_ok = ^{be, wdata};

  assign gnt = 1'b1;
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      rvalid  <= 1'b0;
      err     <= 1'b0;
      rd_q    <= 1'b0;
      range_q <= 1'b0;
      a_q     <= '0;
    end else begin
      rvalid <= req;
      err    <= req && we;
      rd_q   <= req && !we;
      if (req && !we) begin
        a_q     <= addr[AW+1:2];
        range_q <= ({1'b0, addr[13:2]} < 13'(WORDS));
      end
    end
  end

  sfv_bootrom_image u_img (.addr(a_q), .data(img));
  assign rdata = (rd_q && range_q) ? img : 32'd0;
endmodule

`default_nettype wire
