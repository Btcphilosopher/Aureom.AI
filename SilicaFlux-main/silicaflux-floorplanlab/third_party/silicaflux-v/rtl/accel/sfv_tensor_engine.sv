// =============================================================================
// SilicaFlux-V :: sfv_tensor_engine -- 4x4 INT8 multiply-accumulate engine
//
//   C[i][j] (+)= sum_{k<K} A[i][k] * B[k][j]        i, j in 0..3
//
// Operand loading from the tile scratchpad (configurable):
//   A is read column-wise: word k at A_ADDR + k*A_STRIDE holds A[0..3][k] in
//   bytes 0..3 (i.e. A stored transposed / column-major, the natural layout
//   for an output-stationary outer-product array).
//   B is read row-wise: word k at B_ADDR + k*B_STRIDE holds B[k][0..3].
//   A_SIGNED/B_SIGNED select int8 or uint8 per operand.
// Result output: 16 x 32-bit accumulators, readable at ACC0..ACC15
//   (row-major) and optionally written back (CFG.WB) as 4 rows of 4 words at
//   C_ADDR + i*C_STRIDE (16-byte aligned rows).
//
// Registers (byte offsets in the TE page):
//   0x00 CTRL    W [0] START [2] CLEAR (zero accumulators, when idle)
//                RW [1] IRQ_EN
//   0x04 STATUS  [0] BUSY [1] DONE (W1C) [2] ERR (W1C) [7:4] ERRCODE
//   0x08 CFG     [0] ACC (accumulate onto ACC registers; else start from 0)
//                [1] WB  [2] A_UNSIGNED [3] B_UNSIGNED
//   0x0C A_ADDR  0x10 B_ADDR  0x14 C_ADDR  0x18 K [10:0] (1..1024)
//   0x1C A_STRIDE 0x20 B_STRIDE 0x24 C_STRIDE (bytes; 0 selects 4/4/16)
//   0x28 CYCLES (RO)  0x2C INFO (RO)  0x40..0x7C ACC[0..15] (RO)
// Deterministic completion: CYCLES (= cycles with BUSY=1) = 3 + 2*K + (WB ? 4
// : 0) when the TSPM lock is free, independent of data and of fabric traffic
// (the engine has TSPM priority).  Overhead: lock, prologue read, drain.
// Peak: 16 MAC per 2 cycles (A and B words fetched sequentially from
// single-port banks).  Operand double-buffering to reach 16 MAC/cycle is a
// recorded next-revision item (docs/ISSUE_REGISTER.md).
// =============================================================================
`default_nettype none

// -----------------------------------------------------------------------------
// Output-stationary DIM x DIM MAC array.  MAC structure follows the
// repository's memoryflow sf_tensor_array.sv (one accumulator per PE, A
// column broadcast along rows, B row broadcast along columns); input FIFOs
// and accumulator double-buffering removed, reset/clear and per-operand
// signedness added.
// -----------------------------------------------------------------------------
module sfv_mac_array #(
  parameter int DIM = 4,
  parameter int IW  = 8,
  parameter int AW  = 32
) (
  input  wire logic              clk,
  input  wire logic              rst_n,
  input  wire logic              clr,          // synchronous zero
  input  wire logic              step,         // one rank-1 update
  input  wire logic              first,        // step overwrites (acc = a*b)
  input  wire logic              a_uns,
  input  wire logic              b_uns,
  input  wire logic [DIM*IW-1:0] a_col,        // A[0..DIM-1][k]
  input  wire logic [DIM*IW-1:0] b_row,        // B[k][0..DIM-1]
  output logic [DIM*DIM*AW-1:0]  acc           // row-major
);
  genvar gi, gj;
  for (gi = 0; gi < DIM; gi++) begin : g_i
    for (gj = 0; gj < DIM; gj++) begin : g_j
      wire signed [IW:0]     ai = {a_uns ? 1'b0 : a_col[gi*IW + IW-1], a_col[gi*IW +: IW]};
      wire signed [IW:0]     bj = {b_uns ? 1'b0 : b_row[gj*IW + IW-1], b_row[gj*IW +: IW]};
      wire signed [2*IW+1:0] p  = ai * bj;
      wire        [AW-1:0]   pe = {{(AW-2*IW-2){p[2*IW+1]}}, p};
      logic [AW-1:0] q;
      always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)    q <= '0;
        else if (clr)  q <= '0;
        else if (step) q <= (first ? '0 : q) + pe;
      end
      assign acc[(gi*DIM + gj)*AW +: AW] = q;
    end
  end
endmodule

module sfv_tensor_engine #(
  parameter int TSPM_WORDS = 4096,
  localparam int NB  = 4,                              // banks = DIM
  localparam int RAW = $clog2(TSPM_WORDS / NB)
) (
  input  wire logic                clk,
  input  wire logic                rst_n,
  input  wire logic                rb_sel,
  input  wire logic                rb_we,
  input  wire logic [11:0]         rb_addr,
  input  wire logic [31:0]         rb_wdata,
  output logic [31:0]              rb_rdata,
  output logic                     rb_err,
  output logic                     irq,
  output logic                     busy,
  output logic                     lock_req,
  input  wire logic                lock_gnt,
  output logic [NB-1:0]            e_ce,
  output logic                     e_we,
  output logic [NB*RAW-1:0]        e_row,
  output logic [NB*32-1:0]         e_wdata,
  input  wire logic [NB*32-1:0]    e_rdata
);
  localparam int TSPM_BYTES = TSPM_WORDS * 4;

  logic        ien_q, done_q, err_q, accf_q, wb_q, au_q, bu_q;
  logic [3:0]  ecode_q;
  logic [31:0] aa_q, ba_q, ca_q, as_q, bs_q, cs_q, cyc_q;
  logic [10:0] k_q;

  wire wr       = rb_sel && rb_we;
  wire start_wr = wr && rb_addr == 12'h000 && rb_wdata[0];
  wire clear_wr = wr && rb_addr == 12'h000 && rb_wdata[2];

  wire [31:0] as_e = (as_q == 32'd0) ? 32'd4  : as_q;
  wire [31:0] bs_e = (bs_q == 32'd0) ? 32'd4  : bs_q;
  wire [31:0] cs_e = (cs_q == 32'd0) ? 32'd16 : cs_q;

  // ------------------------------------------------------------ legality
  // last word of A/B: base + (K-1)*stride; last byte of C: base + 3*cs + 15
  wire [10:0] km1   = k_q - 11'd1;
  wire [42:0] a_end = {11'd0, aa_q} + {32'd0, km1} * {11'd0, as_e} + 43'd4;
  wire [42:0] b_end = {11'd0, ba_q} + {32'd0, km1} * {11'd0, bs_e} + 43'd4;
  wire [33:0] c_end = {2'd0, ca_q} + 34'd3 * {2'd0, cs_e} + 34'd16;
  logic [3:0] chk;
  always_comb begin
    chk = sfv_pkg::AERR_NONE;
    if (k_q == 11'd0 || k_q > 11'd1024) chk = sfv_pkg::AERR_RANGE;
    else if (aa_q[1:0] != 0 || ba_q[1:0] != 0 || as_e[1:0] != 0 || bs_e[1:0] != 0 ||
             (wb_q && (ca_q[3:0] != 0 || cs_e[3:0] != 0)))
      chk = sfv_pkg::AERR_ALIGN;
    else if (a_end > 43'(TSPM_BYTES) || b_end > 43'(TSPM_BYTES) ||
             (wb_q && c_end > 34'(TSPM_BYTES)))
      chk = sfv_pkg::AERR_RANGE;
  end

  // ------------------------------------------------------------ sequencer
  typedef enum logic [2:0] {S_IDLE, S_LOCK, S_PRO, S_RUN, S_DRAIN, S_WB} st_e;
  st_e         st;
  logic [10:0] kk;            // current k in the [RB, RA'] pattern
  logic        slot;          // 0: RB(k)  1: RA'(k+1)
  logic [1:0]  wrow;
  logic [31:0] pa, pb, pc;    // byte pointers
  logic        first_q;       // next MAC overwrites (no ACC)

  wire last_k = (kk == k_q - 11'd1);
  wire iss_a  = (st == S_PRO) || (st == S_RUN && slot && !last_k);
  wire iss_b  = (st == S_RUN && !slot);
  wire iss_w  = (st == S_WB);

  // read-in-flight tags
  logic rt_a_q, rt_b_q;
  logic [31:0] areg_q;
  logic [1:0]  ra_bank_q, rb_bank_q;

  logic [16*32-1:0] acc;
  wire [31:0] b_word = e_rdata[rb_bank_q*32 +: 32];
  wire        mac    = rt_b_q;

  sfv_mac_array #(.DIM(4), .IW(8), .AW(32)) u_mac (
    .clk, .rst_n, .clr(clear_wr && st == S_IDLE), .step(mac), .first(first_q),
    .a_uns(au_q), .b_uns(bu_q), .a_col(areg_q), .b_row(b_word), .acc(acc)
  );

  always_comb begin
    e_ce    = '0;
    e_we    = 1'b0;
    e_row   = '0;
    e_wdata = acc[wrow*128 +: 128];
    if (iss_a) begin
      e_ce[pa[3:2]] = 1'b1;
      for (int b = 0; b < NB; b++) e_row[b*RAW +: RAW] = pa[RAW+3:4];
    end else if (iss_b) begin
      e_ce[pb[3:2]] = 1'b1;
      for (int b = 0; b < NB; b++) e_row[b*RAW +: RAW] = pb[RAW+3:4];
    end else if (iss_w) begin
      e_ce = '1;
      e_we = 1'b1;
      for (int b = 0; b < NB; b++) e_row[b*RAW +: RAW] = pc[RAW+3:4];
    end
  end
  assign lock_req = (st != S_IDLE);
  assign busy     = (st != S_IDLE);

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      ien_q <= 1'b0; done_q <= 1'b0; err_q <= 1'b0; ecode_q <= '0;
      accf_q <= 1'b0; wb_q <= 1'b0; au_q <= 1'b0; bu_q <= 1'b0;
      aa_q <= '0; ba_q <= '0; ca_q <= '0; as_q <= '0; bs_q <= '0; cs_q <= '0;
      cyc_q <= '0; k_q <= 11'd1;
      st <= S_IDLE; kk <= '0; slot <= 1'b0; wrow <= '0;
      pa <= '0; pb <= '0; pc <= '0; first_q <= 1'b0;
      rt_a_q <= 1'b0; rt_b_q <= 1'b0; areg_q <= '0; ra_bank_q <= '0; rb_bank_q <= '0;
    end else begin
      if (wr) begin
        case (rb_addr)
          12'h000: ien_q <= rb_wdata[1];
          12'h004: begin
            if (rb_wdata[1]) done_q <= 1'b0;
            if (rb_wdata[2]) begin err_q <= 1'b0; ecode_q <= '0; end
          end
          12'h008: if (st == S_IDLE) begin
            accf_q <= rb_wdata[0]; wb_q <= rb_wdata[1]; au_q <= rb_wdata[2]; bu_q <= rb_wdata[3];
          end
          12'h00C: if (st == S_IDLE) aa_q <= rb_wdata;
          12'h010: if (st == S_IDLE) ba_q <= rb_wdata;
          12'h014: if (st == S_IDLE) ca_q <= rb_wdata;
          12'h018: if (st == S_IDLE) k_q  <= rb_wdata[10:0];
          12'h01C: if (st == S_IDLE) as_q <= rb_wdata;
          12'h020: if (st == S_IDLE) bs_q <= rb_wdata;
          12'h024: if (st == S_IDLE) cs_q <= rb_wdata;
          default: ;
        endcase
      end

      // read-response pipeline
      rt_a_q    <= iss_a;
      rt_b_q    <= iss_b;
      ra_bank_q <= pa[3:2];
      rb_bank_q <= pb[3:2];
      if (rt_a_q) areg_q <= e_rdata[ra_bank_q*32 +: 32];
      if (mac)    first_q <= 1'b0;

      if (st != S_IDLE) cyc_q <= cyc_q + 32'd1;
      case (st)
        S_IDLE: if (start_wr) begin
          if (chk != sfv_pkg::AERR_NONE) begin
            err_q <= 1'b1; ecode_q <= chk;
          end else begin
            st      <= S_LOCK;
            done_q  <= 1'b0;
            cyc_q   <= 32'd0;
            kk      <= '0;
            slot    <= 1'b0;
            wrow    <= '0;
            pa      <= aa_q;
            pb      <= ba_q;
            pc      <= ca_q;
            first_q <= !accf_q;
          end
        end
        S_LOCK: if (lock_gnt) st <= S_PRO;
        S_PRO: begin
          pa <= pa + as_e;
          st <= S_RUN;
        end
        S_RUN: begin
          if (iss_a) pa <= pa + as_e;
          if (iss_b) pb <= pb + bs_e;
          slot <= !slot;
          if (slot) begin
            kk <= kk + 11'd1;
            if (last_k) st <= S_DRAIN;
          end
        end
        S_DRAIN: st <= wb_q ? S_WB : S_IDLE;   // accumulators final from here
        default: begin                          // S_WB
          pc   <= pc + cs_e;
          wrow <= wrow + 2'd1;
          if (wrow == 2'd3) st <= S_IDLE;
        end
      endcase
      if ((st == S_DRAIN && !wb_q) || (st == S_WB && wrow == 2'd3)) done_q <= 1'b1;
      if (start_wr && st != S_IDLE) begin err_q <= 1'b1; ecode_q <= sfv_pkg::AERR_BUSY; end
    end
  end

  assign irq = ien_q && (done_q || err_q);

  always_comb begin
    rb_rdata = 32'd0;
    rb_err   = 1'b0;
    if (rb_addr >= 12'h040 && rb_addr <= 12'h07C && rb_addr[1:0] == 2'b00) begin
      rb_rdata = acc[rb_addr[5:2]*32 +: 32];
    end else begin
      case (rb_addr)
        12'h000: rb_rdata = {30'd0, ien_q, 1'b0};
        12'h004: rb_rdata = {24'd0, ecode_q, 1'b0, err_q, done_q, busy};
        12'h008: rb_rdata = {28'd0, bu_q, au_q, wb_q, accf_q};
        12'h00C: rb_rdata = aa_q;
        12'h010: rb_rdata = ba_q;
        12'h014: rb_rdata = ca_q;
        12'h018: rb_rdata = {21'd0, k_q};
        12'h01C: rb_rdata = as_q;
        12'h020: rb_rdata = bs_q;
        12'h024: rb_rdata = cs_q;
        12'h028: rb_rdata = cyc_q;
        12'h02C: rb_rdata = {16'(TSPM_BYTES / 1024), 8'd8, 8'd4};   // KiB, IW, DIM
        default: rb_err = 1'b1;
      endcase
    end
  end
endmodule

`default_nettype wire
