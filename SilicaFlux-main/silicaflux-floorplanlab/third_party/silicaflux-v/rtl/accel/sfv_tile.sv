// =============================================================================
// SilicaFlux-V :: sfv_tile -- compute tile: vector engine + tensor engine +
//                 tile scratchpad (TSPM), the SilicaFlux "compute tile"
//                 reduced to its minimum (cf. SilicaFlux v1.0 compute_tile).
//
// TSPM: NB = LANES word-interleaved single-port banks (bank = addr[3:2] for
//   LANES = 4), each sfv_sram_sp of TSPM_WORDS/NB words.
// Access arbitration (per bank, per cycle, fixed priority):
//   1. MBIST (whole TSPM, test mode only)
//   2. the engine holding the TSPM lock (VE or TE, one command at a time;
//      lock arbitration TE > VE when both request in the same cycle)
//   3. the SFB fabric port (CPU / debug) -- not granted while the addressed
//      bank is used by the engine in that cycle.
//   Engine timing is therefore independent of fabric traffic (deterministic
//   completion); the CPU sees wait states only on bank conflicts.
// Clocking: each engine runs on its own ICG output; the gate opens while the
//   engine is busy or its register page is accessed, and is forced open by
//   test_mode or SYSCTRL.CLK_CTRL.TILE_CG_OFF.  Engines qualify all state
//   updates, so behaviour is identical with gating disabled
//   (SFV_NO_CLOCK_GATE) -- verified by running the regression both ways.
// =============================================================================
`default_nettype none

module sfv_tile #(
  parameter int LANES      = 4,
  parameter int MUL_W      = 32,
  parameter int TSPM_WORDS = 4096,         // 16 KiB
  localparam int NB  = LANES,
  localparam int BW  = $clog2(TSPM_WORDS / NB),
  localparam int LW  = $clog2(NB)
) (
  input  wire logic          clk,
  input  wire logic          rst_n,
  input  wire logic          test_mode,
  input  wire logic          cg_off,
  // SFB slave (TSPM window)
  input  wire logic          req,
  output logic               gnt,
  input  wire logic [31:0]   addr,
  input  wire logic          we,
  input  wire logic [3:0]    be,
  input  wire logic [31:0]   wdata,
  output logic               rvalid,
  output logic [31:0]        rdata,
  output logic               err,
  // register-bus pages
  input  wire logic          ve_sel,
  input  wire logic          te_sel,
  input  wire logic          rb_we,
  input  wire logic [11:0]   rb_addr,
  input  wire logic [31:0]   rb_wdata,
  output logic [31:0]        ve_rdata,
  output logic               ve_err,
  output logic [31:0]        te_rdata,
  output logic               te_err,
  output logic               irq_ve,
  output logic               irq_te,
  // MBIST port (all banks in parallel)
  input  wire logic          bist_en,
  input  wire logic          bist_ce,
  input  wire logic          bist_we,
  input  wire logic [BW-1:0] bist_addr,
  input  wire logic [31:0]   bist_wdata,
  output logic [NB*32-1:0]   bist_rdata
);
  // ------------------------------------------------------------ clock gates
  logic ve_busy, te_busy, gclk_ve, gclk_te;
  sfv_clkgate u_cg_ve (.clk, .en(ve_sel || ve_busy || cg_off), .test_en(test_mode), .gclk(gclk_ve));
  sfv_clkgate u_cg_te (.clk, .en(te_sel || te_busy || cg_off), .test_en(test_mode), .gclk(gclk_te));

  // ------------------------------------------------------------ engines
  logic          ve_lreq, te_lreq, ve_lgnt, te_lgnt;
  logic [NB-1:0] ve_ce, te_ce;
  logic          ve_we, te_we;
  logic [NB*BW-1:0] ve_row, te_row;
  logic [NB*32-1:0] ve_wd, te_wd, bank_q;

  sfv_vec_engine #(.LANES(LANES), .MUL_W(MUL_W), .TSPM_WORDS(TSPM_WORDS)) u_ve (
    .clk(gclk_ve), .rst_n,
    .rb_sel(ve_sel), .rb_we, .rb_addr, .rb_wdata, .rb_rdata(ve_rdata), .rb_err(ve_err),
    .irq(irq_ve), .busy(ve_busy),
    .lock_req(ve_lreq), .lock_gnt(ve_lgnt),
    .e_ce(ve_ce), .e_we(ve_we), .e_row(ve_row), .e_wdata(ve_wd), .e_rdata(bank_q)
  );

  sfv_tensor_engine #(.TSPM_WORDS(TSPM_WORDS)) u_te (
    .clk(gclk_te), .rst_n,
    .rb_sel(te_sel), .rb_we, .rb_addr, .rb_wdata, .rb_rdata(te_rdata), .rb_err(te_err),
    .irq(irq_te), .busy(te_busy),
    .lock_req(te_lreq), .lock_gnt(te_lgnt),
    .e_ce(te_ce), .e_we(te_we), .e_row(te_row), .e_wdata(te_wd), .e_rdata(bank_q)
  );

  // ------------------------------------------------------------ lock
  logic own_ve_q, own_te_q;
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      own_ve_q <= 1'b0; own_te_q <= 1'b0;
    end else begin
      if (own_te_q && !te_lreq) own_te_q <= 1'b0;
      if (own_ve_q && !ve_lreq) own_ve_q <= 1'b0;
      if (!own_te_q && !own_ve_q) begin
        if (te_lreq)      own_te_q <= 1'b1;
        else if (ve_lreq) own_ve_q <= 1'b1;
      end
    end
  end
  // grant in the request cycle when the TSPM is free (TE wins a tie); the
  // owner flop then holds the lock until the engine drops its request.
  wire lock_free = !own_te_q && !own_ve_q;
  assign te_lgnt = own_te_q || (lock_free && te_lreq);
  assign ve_lgnt = own_ve_q || (lock_free && ve_lreq && !te_lreq);

  // engine port of the lock owner
  logic [NB-1:0]    en_ce;
  logic             en_we;
  logic [NB*BW-1:0] en_row;
  logic [NB*32-1:0] en_wd;
  always_comb begin
    en_ce = '0; en_we = 1'b0; en_row = ve_row; en_wd = ve_wd;
    if (own_te_q) begin en_ce = te_ce; en_we = te_we; en_row = te_row; en_wd = te_wd; end
    else if (own_ve_q) begin en_ce = ve_ce; en_we = ve_we; end
  end

  // ------------------------------------------------------------ fabric port
  wire [LW-1:0] f_bank = addr[LW+1:2];
  wire [BW-1:0] f_row  = addr[BW+LW+1:LW+2];
  assign gnt = !bist_en && !en_ce[f_bank];
  wire f_go = req && gnt;

  logic          f_rd_q;
  logic [LW-1:0] f_bank_q;
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      rvalid <= 1'b0; f_rd_q <= 1'b0; f_bank_q <= '0;
    end else begin
      rvalid   <= f_go;
      f_rd_q   <= f_go && !we;
      f_bank_q <= f_bank;
    end
  end
  assign rdata = f_rd_q ? bank_q[f_bank_q*32 +: 32] : 32'd0;
  assign err   = 1'b0;

  // ------------------------------------------------------------ banks
  genvar gb;
  for (gb = 0; gb < NB; gb++) begin : g_bank
    logic          ce, bwe;
    logic [3:0]    bbe;
    logic [BW-1:0] ba;
    logic [31:0]   bwd;
    always_comb begin
      if (bist_en) begin
        ce = bist_ce; bwe = bist_we; bbe = 4'b1111; ba = bist_addr; bwd = bist_wdata;
      end else if (en_ce[gb]) begin
        ce = 1'b1; bwe = en_we; bbe = 4'b1111; ba = en_row[gb*BW +: BW]; bwd = en_wd[gb*32 +: 32];
      end else begin
        ce = f_go && (f_bank == LW'(gb)); bwe = we; bbe = be; ba = f_row; bwd = wdata;
      end
    end
    sfv_sram_sp #(.DEPTH(TSPM_WORDS / NB)) u_ram (
      .clk, .ce, .we(bwe), .be(bbe), .addr(ba), .wdata(bwd), .rdata(bank_q[gb*32 +: 32])
    );
  end
  assign bist_rdata = bank_q;
endmodule

`default_nettype wire
