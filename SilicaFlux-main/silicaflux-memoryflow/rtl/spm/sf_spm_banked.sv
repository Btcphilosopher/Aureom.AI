// =============================================================================
// SilicaFlux MemoryFlow :: sf_spm_banked
// Multi-port, multi-bank scratchpad memory (SPM) built from sf_sram_bank.
//
//  * NPORTS valid/ready request ports, NBANKS single-port banks.
//  * Address interleaving (INTERLEAVE):
//       0 = word-modulo  : bank = word[log2B-1:0]
//       1 = XOR-hash     : bank = word[log2B-1:0] ^ word[log2B +: log2B]
//                          (breaks power-of-two stride conflicts)
//       2 = block        : bank = word[IDXW +: log2B] (contiguous regions)
//  * Per-bank round-robin arbitration across ports (one grant/bank/cycle).
//  * Every request gets exactly one response, IN ORDER per port (all banks
//    have identical fixed latency, a port issues <= 1 request/cycle).
//  * Response backpressure: per-port response FIFO + credit counter; a port
//    is only granted while (in-flight + queued) < RSP_DEPTH, so responses can
//    never be dropped and a stalled consumer only blocks its own port.
//  * Address overflow protection: byte address >= CAPACITY returns an error
//    response through a latency-matched path and never touches an array.
//  * MBIST: built-in March C- controller tests all banks in parallel; while
//    it runs every functional port is held not-ready.
//  * ECC: corrected / uncorrectable counters, per-bank error injection.
//  * Perf counters: bank-conflict cycles and port-stall cycles.
//
// Port-to-response latency: 3 cycles (accept -> rsp_valid), 1 req/cycle/port
// sustained when RSP_DEPTH >= 4 and there are no bank conflicts.
// Classification: SYNTHESIZABLE
// =============================================================================
`default_nettype none

module sf_spm_banked #(
  parameter int NPORTS     = 3,
  parameter int NBANKS     = 4,
  parameter int DW         = 64,
  parameter int BANK_DEPTH = 1024,          // words per bank
  parameter int AW         = 32,            // byte address width
  parameter int ECC_MODE   = 2,
  parameter int INTERLEAVE = 0,
  parameter int RSP_DEPTH  = 4,
  parameter int IMPL       = 0,
  parameter int MACRO_W    = 72,
  parameter int MACRO_D    = 512,
  // test-only stuck-at fault (applied to bank SA_BANK)
  parameter bit SA_EN      = 1'b0,
  parameter int SA_BANK    = 0,
  parameter int SA_ADDR    = 0,
  parameter int SA_BIT     = 0,
  parameter bit SA_VAL     = 1'b0,
  localparam int NB        = DW / 8,
  localparam int OFF       = $clog2(NB),
  localparam int BKW       = (NBANKS > 1) ? $clog2(NBANKS) : 1,
  localparam int IDXW      = (BANK_DEPTH > 1) ? $clog2(BANK_DEPTH) : 1,
  localparam int PIW       = (NPORTS > 1) ? $clog2(NPORTS) : 1,
  localparam int R         = $clog2(DW + 1 + $clog2(DW + 1)),
  localparam int SW        = (ECC_MODE == 2) ? (DW + R + 1) :
                             (ECC_MODE == 1) ? (NB * 9) : DW,
  localparam int CAPACITY   = NBANKS * BANK_DEPTH * NB   // bytes (< 2 GiB)
) (
  input  logic                 clk,
  input  logic                 rst_n,
  // request ports (flattened)
  input  logic [NPORTS-1:0]    req_valid,
  output logic [NPORTS-1:0]    req_ready,
  input  logic [NPORTS-1:0]    req_we,
  input  logic [NPORTS*AW-1:0] req_addr,
  input  logic [NPORTS*DW-1:0] req_wdata,
  input  logic [NPORTS*NB-1:0] req_wstrb,
  // response ports
  output logic [NPORTS-1:0]    rsp_valid,
  input  logic [NPORTS-1:0]    rsp_ready,
  output logic [NPORTS*DW-1:0] rsp_rdata,
  output logic [NPORTS-1:0]    rsp_err,      // address overflow or uncorrectable
  output logic [NPORTS-1:0]    rsp_corr,     // single-bit error corrected
  // RAS / ECC
  input  logic                 inj_en,
  input  logic [BKW-1:0]       inj_bank,
  input  logic [SW-1:0]        inj_mask,
  output logic [15:0]          cnt_corr,
  output logic [15:0]          cnt_uncorr,
  // MBIST
  input  logic                 mbist_start,
  input  logic [SW-1:0]        mbist_bg,
  output logic                 mbist_busy,
  output logic                 mbist_done,
  output logic                 mbist_fail,
  output logic [NBANKS-1:0]    mbist_fail_bank,
  output logic [IDXW-1:0]      mbist_fail_addr,
  // performance counters
  output logic [31:0]          cnt_conflict_cycles,
  output logic [31:0]          cnt_stall_cycles,
  // low power
  input  logic                 lp_sleep
);
  localparam int CW = $clog2(RSP_DEPTH + 1);

  // ------------------------------------------------------------ decode
  logic [BKW-1:0]  p_bank [NPORTS];
  logic [IDXW-1:0] p_idx  [NPORTS];
  logic            p_oor  [NPORTS];     // out of range

  genvar gd;
  generate
    for (gd = 0; gd < NPORTS; gd++) begin : g_dec
      wire [AW-1:0] a = req_addr[gd*AW +: AW];
      /* verilator lint_off UNUSEDSIGNAL */
      wire [AW-1:0] w = a >> OFF;      // only bank+index bits used
      /* verilator lint_on UNUSEDSIGNAL */
      assign p_oor[gd] = ({1'b0, a} >= (AW+1)'(CAPACITY));
      if (NBANKS == 1) begin : g_one
        assign p_bank[gd] = '0;
        assign p_idx[gd]  = IDXW'(w);
      end else if (INTERLEAVE == 2) begin : g_block
        assign p_bank[gd] = BKW'(w >> IDXW);
        assign p_idx[gd]  = IDXW'(w);
      end else if (INTERLEAVE == 1) begin : g_xor
        assign p_bank[gd] = BKW'(w) ^ BKW'(w >> BKW);
        assign p_idx[gd]  = IDXW'(w >> BKW);
      end else begin : g_mod
        assign p_bank[gd] = BKW'(w);
        assign p_idx[gd]  = IDXW'(w >> BKW);
      end
    end
  endgenerate

  // ------------------------------------------------------------ credits
  logic [CW-1:0]     outstanding [NPORTS];
  logic [NPORTS-1:0] credit;
  logic [NPORTS-1:0] p_accept;
  logic [NPORTS-1:0] p_pop;

  always_comb begin
    for (int p = 0; p < NPORTS; p++) credit[p] = (outstanding[p] < CW'(RSP_DEPTH));
  end

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      for (int p = 0; p < NPORTS; p++) outstanding[p] <= '0;
    end else begin
      for (int p = 0; p < NPORTS; p++) begin
        case ({p_accept[p], p_pop[p]})
          2'b10:   outstanding[p] <= outstanding[p] + CW'(1);
          2'b01:   outstanding[p] <= outstanding[p] - CW'(1);
          default: outstanding[p] <= outstanding[p];
        endcase
      end
    end
  end

  // ------------------------------------------------------------ MBIST
  logic              bist_en, bist_ce, bist_we;
  logic [IDXW-1:0]   bist_addr;
  logic [SW-1:0]     bist_wdata;
  logic [NBANKS*SW-1:0] bist_rdata;
  logic [2:0]        bist_fail_elem_unused;

  sf_mbist_march #(.SW(SW), .DEPTH(BANK_DEPTH), .NBANKS(NBANKS)) u_mbist (
    .clk, .rst_n, .start(mbist_start), .bg(mbist_bg),
    .busy(mbist_busy), .done(mbist_done), .fail(mbist_fail),
    .fail_bank(mbist_fail_bank), .fail_addr(mbist_fail_addr),
    .fail_elem(bist_fail_elem_unused),
    .bist_en, .bist_ce, .bist_we, .bist_addr, .bist_wdata, .bist_rdata
  );

  // ------------------------------------------------------------ banks
  logic [NPORTS-1:0] b_grant  [NBANKS];
  logic [PIW-1:0]    b_gidx   [NBANKS];
  logic              b_gvalid [NBANKS];
  logic              b_ready  [NBANKS];
  logic              b_rsp_valid [NBANKS];
  /* verilator lint_off UNUSEDSIGNAL */
  logic              b_rsp_we    [NBANKS];   // reads/acks share one path
  /* verilator lint_on UNUSEDSIGNAL */
  logic [DW-1:0]     b_rsp_rdata [NBANKS];
  logic [PIW-1:0]    b_rsp_tag   [NBANKS];
  logic              b_rsp_corr  [NBANKS];
  logic              b_rsp_unc   [NBANKS];
  logic [NBANKS-1:0] b_conflict;

  genvar gb;
  generate
    for (gb = 0; gb < NBANKS; gb++) begin : g_bank
      logic [NPORTS-1:0] breq;
      always_comb begin
        for (int p = 0; p < NPORTS; p++)
          breq[p] = req_valid[p] && !p_oor[p] && credit[p] &&
                    (p_bank[p] == BKW'(gb)) && !mbist_busy;
      end
      assign b_conflict[gb] = |(breq & (breq - NPORTS'(1)));

      sf_rr_arbiter #(.N(NPORTS)) u_arb (
        .clk, .rst_n, .req(breq), .accept(b_ready[gb]),
        .grant(b_grant[gb]), .grant_idx(b_gidx[gb]), .grant_valid(b_gvalid[gb])
      );

      sf_sram_bank #(
        .DW(DW), .DEPTH(BANK_DEPTH), .ECC_MODE(ECC_MODE), .TAGW(PIW),
        .IMPL(IMPL), .MACRO_W(MACRO_W), .MACRO_D(MACRO_D),
        .SA_EN(SA_EN && (SA_BANK == gb)), .SA_ADDR(SA_ADDR), .SA_BIT(SA_BIT), .SA_VAL(SA_VAL)
      ) u_bank (
        .clk, .rst_n,
        .req_valid (b_gvalid[gb]),
        .req_ready (b_ready[gb]),
        .req_we    (req_we[b_gidx[gb]]),
        .req_addr  (p_idx[b_gidx[gb]]),
        .req_wdata (req_wdata[b_gidx[gb]*DW +: DW]),
        .req_wstrb (req_wstrb[b_gidx[gb]*NB +: NB]),
        .req_tag   (b_gidx[gb]),
        .rsp_valid (b_rsp_valid[gb]),
        .rsp_we    (b_rsp_we[gb]),
        .rsp_rdata (b_rsp_rdata[gb]),
        .rsp_tag   (b_rsp_tag[gb]),
        .rsp_corr  (b_rsp_corr[gb]),
        .rsp_uncorr(b_rsp_unc[gb]),
        .inj_en    (inj_en && (inj_bank == BKW'(gb))),
        .inj_mask  (inj_mask),
        .bist_en, .bist_ce, .bist_we, .bist_addr, .bist_wdata,
        .bist_rdata(bist_rdata[gb*SW +: SW]),
        .lp_sleep  (lp_sleep),
        .lp_shutdown(1'b0)
      );
    end
  endgenerate

  // ------------------------------------------------------------ accept
  logic [NPORTS-1:0] oor_accept;
  always_comb begin
    for (int p = 0; p < NPORTS; p++) begin
      oor_accept[p] = req_valid[p] && p_oor[p] && credit[p] && !mbist_busy;
      p_accept[p]   = oor_accept[p];
      for (int b = 0; b < NBANKS; b++)
        if (b_grant[b][p] && b_ready[b]) p_accept[p] = 1'b1;
    end
  end
  assign req_ready = p_accept;

  // latency-matched error path for out-of-range requests (2 cycles)
  logic [NPORTS-1:0] oor_d1, oor_d2;
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      oor_d1 <= '0;
      oor_d2 <= '0;
    end else begin
      oor_d1 <= oor_accept;
      oor_d2 <= oor_d1;
    end
  end

  // ------------------------------------------------------------ responses
  logic [NPORTS-1:0] f_push;
  logic [NPORTS-1:0] f_push_ready;     // always 1 by construction (credits)
  logic [DW+1:0]     f_din [NPORTS];   // {corr, err, rdata}

  always_comb begin
    for (int p = 0; p < NPORTS; p++) begin
      f_push[p] = oor_d2[p];
      f_din[p]  = {1'b0, oor_d2[p], {DW{1'b0}}};
      for (int b = 0; b < NBANKS; b++) begin
        if (b_rsp_valid[b] && (b_rsp_tag[b] == PIW'(p))) begin
          f_push[p] = 1'b1;
          f_din[p]  = {b_rsp_corr[b], b_rsp_unc[b], b_rsp_rdata[b]};
        end
      end
    end
  end

  genvar gp;
  generate
    for (gp = 0; gp < NPORTS; gp++) begin : g_port
      logic [DW+1:0] f_dout;
      logic [$clog2(RSP_DEPTH+1)-1:0] f_cnt_unused;
      sf_fifo #(.WIDTH(DW + 2), .DEPTH(RSP_DEPTH)) u_rsp_fifo (
        .clk, .rst_n,
        .push_valid(f_push[gp]), .push_ready(f_push_ready[gp]), .push_data(f_din[gp]),
        .pop_valid(rsp_valid[gp]), .pop_ready(rsp_ready[gp]), .pop_data(f_dout),
        .count(f_cnt_unused)
      );
      assign p_pop[gp]               = rsp_valid[gp] && rsp_ready[gp];
      assign rsp_rdata[gp*DW +: DW]  = f_dout[DW-1:0];
      assign rsp_err[gp]             = f_dout[DW];
      assign rsp_corr[gp]            = f_dout[DW+1];
    end
  endgenerate

  // ------------------------------------------------------------ counters
  logic any_corr, any_unc;
  logic [31:0] n_stall;
  always_comb begin
    n_stall = '0;
    for (int p = 0; p < NPORTS; p++)
      if (req_valid[p] && !req_ready[p]) n_stall = n_stall + 32'd1;
  end
  always_comb begin
    any_corr = 1'b0;
    any_unc  = 1'b0;
    for (int b = 0; b < NBANKS; b++) begin
      any_corr = any_corr | (b_rsp_valid[b] & b_rsp_corr[b]);
      any_unc  = any_unc  | (b_rsp_valid[b] & b_rsp_unc[b]);
    end
  end

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      cnt_corr            <= '0;
      cnt_uncorr          <= '0;
      cnt_conflict_cycles <= '0;
      cnt_stall_cycles    <= '0;
    end else begin
      if (any_corr && cnt_corr != 16'hFFFF)   cnt_corr   <= cnt_corr + 16'd1;
      if (any_unc  && cnt_uncorr != 16'hFFFF) cnt_uncorr <= cnt_uncorr + 16'd1;
      if (|b_conflict) cnt_conflict_cycles <= cnt_conflict_cycles + 32'd1;
      cnt_stall_cycles <= cnt_stall_cycles + n_stall;
    end
  end

`ifndef SYNTHESIS
  // pragma translate_off
  // At most one response per port per cycle (ordering invariant).
  /* verilator lint_off SYNCASYNCNET */
  always_ff @(posedge clk) begin
    if (rst_n) begin
      for (int p = 0; p < NPORTS; p++) begin
        int n;
        n = oor_d2[p] ? 1 : 0;
        for (int b = 0; b < NBANKS; b++)
          if (b_rsp_valid[b] && b_rsp_tag[b] == PIW'(p)) n++;
        if (n > 1) $error("sf_spm_banked: %0d responses to port %0d in one cycle", n, p);
        if (f_push[p] && !f_push_ready[p])
          $error("sf_spm_banked: response FIFO overflow on port %0d", p);
      end
    end
  end
  /* verilator lint_on SYNCASYNCNET */
  // pragma translate_on
`endif

endmodule

`default_nettype wire
