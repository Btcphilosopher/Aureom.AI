// =============================================================================
// SilicaFlux-V :: sfv_vec_engine -- LANES-wide integer SIMD engine
//
// Memory-to-memory streaming over the tile scratchpad (TSPM).  One "beat" is
// LANES consecutive 32-bit elements = one row across the LANES TSPM banks.
//
// Registers (byte offsets in the VE page):
//   0x00 CTRL    W [0] START  RW [1] IRQ_EN
//   0x04 STATUS  [0] BUSY [1] DONE (W1C) [2] ERR (W1C) [7:4] ERRCODE
//   0x08 CMD     [3:0] OP  [8] BSCALAR (b = SCALAR)  [9] ACC (DOT adds to
//                RESULT instead of clearing it)  [10] WRES (DOT: store RESULT
//                to DST)
//   0x0C SRC_A   0x10 SRC_B   0x14 DST   (byte offsets inside the TSPM)
//   0x18 LEN     [15:0] elements (0 = no-op)
//   0x1C SCALAR  0x20 RESULT (RW)   0x24 CYCLES (RO, last command)
//   0x28 INFO    [7:0] LANES [15:8] MUL_W [31:16] TSPM KiB
// Ops (sfv_pkg::VOP_*): ADD SUB MUL MIN MAX AND OR XOR SLL SRA SRL DOT.
//   Element arithmetic is 32-bit two's complement, wrapping.  MUL / DOT use
//   the signed product of the low MUL_W bits of each operand, truncated to
//   32 bits (MUL_W = 32 -> exact C int32 multiply).  Shifts use b[4:0].
// Legality checked at START (ERR, command not executed):
//   ALIGN  SRC_A/SRC_B/DST not LANES*4-aligned (DOT DST: 4-aligned)
//   RANGE  an operand exceeds the TSPM
//   BADOP  OP > VOP_DOT          BUSY  START while busy (running cmd continues)
// Timing (deterministic, no TSPM contention by construction):
//   CYCLES (= cycles with BUSY=1) = 3 + B*P (+1 for DOT with WRES),
//   B = ceil(LEN/LANES) beats, P = 3 (vector-vector), 2 (vector-scalar or
//   DOT vector-vector), 1 (DOT vector-scalar); LEN = 0 -> 2.
//   (P is the number of single-port bank accesses per beat: optimal.)
//   Fixed overhead: lock (1) + prologue read (1) + final stage (1).
// =============================================================================
`default_nettype none

module sfv_vec_engine #(
  parameter int LANES      = 4,
  parameter int MUL_W      = 32,
  parameter int TSPM_WORDS = 4096,
  localparam int RAW = $clog2(TSPM_WORDS / LANES),   // row address width
  localparam int LW  = $clog2(LANES)
) (
  input  wire logic                  clk,
  input  wire logic                  rst_n,
  // register bus
  input  wire logic                  rb_sel,
  input  wire logic                  rb_we,
  input  wire logic [11:0]           rb_addr,
  input  wire logic [31:0]           rb_wdata,
  output logic [31:0]                rb_rdata,
  output logic                       rb_err,
  output logic                       irq,
  output logic                       busy,
  // TSPM engine port
  output logic                       lock_req,
  input  wire logic                  lock_gnt,
  output logic [LANES-1:0]           e_ce,
  output logic                       e_we,
  output logic [LANES*RAW-1:0]       e_row,
  output logic [LANES*32-1:0]        e_wdata,
  input  wire logic [LANES*32-1:0]   e_rdata
);
  localparam int TSPM_BYTES = TSPM_WORDS * 4;
  localparam int BEAT_BYTES = LANES * 4;

  // ------------------------------------------------------------ registers
  logic        ien_q, done_q, err_q;
  logic [3:0]  ecode_q;
  logic [3:0]  op_q;
  logic        bsc_q, accf_q, wres_q;
  logic [31:0] sa_q, sb_q, dst_q, scal_q, res_q, cyc_q;
  logic [15:0] len_q;

  wire wr = rb_sel && rb_we;
  wire start_wr = wr && rb_addr == 12'h000 && rb_wdata[0];

  // ------------------------------------------------------------ legality
  wire is_dot  = (op_q == sfv_pkg::VOP_DOT);
  wire has_b   = !bsc_q;
  wire has_w   = !is_dot;
  wire [17:0] nbytes = {len_q, 2'b00};
  function automatic logic fits(input logic [31:0] base, input logic [17:0] n);
    fits = ({1'b0, base} + {15'd0, n}) <= 33'(TSPM_BYTES);
  endfunction
  logic [3:0] chk;
  always_comb begin
    chk = sfv_pkg::AERR_NONE;
    if (op_q > sfv_pkg::VOP_LAST) chk = sfv_pkg::AERR_BADOP;
    else if ((sa_q % BEAT_BYTES) != 0 || (has_b && (sb_q % BEAT_BYTES) != 0) ||
             (has_w && (dst_q % BEAT_BYTES) != 0) ||
             (is_dot && wres_q && dst_q[1:0] != 2'b00))
      chk = sfv_pkg::AERR_ALIGN;
    else if (!fits(sa_q, nbytes) || (has_b && !fits(sb_q, nbytes)) ||
             (has_w && !fits(dst_q, nbytes)) || (is_dot && wres_q && !fits(dst_q, 18'd4)))
      chk = sfv_pkg::AERR_RANGE;
  end

  // ------------------------------------------------------------ sequencer
  typedef enum logic [2:0] {S_IDLE, S_LOCK, S_PRO, S_RUN, S_FACC, S_FWR} st_e;
  st_e         st;
  logic [15:0] nbeats, beat;      // beat being processed in the slot pattern
  logic [1:0]  slot;
  logic [RAW-1:0] row_a, row_b, row_d;

  // slot pattern: [RB if has_b] [RA'] [WR if has_w]
  wire [1:0] p_len  = 2'(has_b) + 2'd1 + 2'(has_w);
  wire [1:0] s_ra   = has_b ? 2'd1 : 2'd0;
  wire       sl_rb  = has_b && (slot == 2'd0);
  wire       sl_ra  = (slot == s_ra);
  wire       sl_wr  = has_w && (slot == s_ra + 2'd1);
  wire       last_slot = (slot == p_len - 2'd1);
  wire       last_beat = (beat == nbeats - 16'd1);

  // beat index of the read issued this cycle: RB reads `beat`, RA' reads
  // `beat+1`, the prologue reads beat 0.  Its tail-lane mask travels with it.
  wire [15:0] iss_beat = (st == S_PRO) ? 16'd0 : (sl_rb ? beat : beat + 16'd1);
  wire [15:0] remain_i = len_q - {iss_beat[15-LW:0], {LW{1'b0}}};
  function automatic logic [LANES-1:0] lmask(input logic [15:0] rem);
    for (int l = 0; l < LANES; l++) lmask[l] = (rem > 16'(l));
  endfunction

  // issue
  logic          iss_a, iss_b, iss_w;
  always_comb begin
    iss_a = 1'b0; iss_b = 1'b0; iss_w = 1'b0;
    if (st == S_PRO) iss_a = 1'b1;
    if (st == S_RUN) begin
      iss_b = sl_rb;
      iss_a = sl_ra && !last_beat;
      iss_w = sl_wr;
    end
  end

  // ------------------------------------------------------------ datapath
  // read-in-flight tag
  logic        rt_a_q, rt_b_q;
  logic [LANES-1:0] rt_mask_q;
  logic [LANES*32-1:0] areg_q, rreg_q;
  logic [LANES-1:0]    rmask_q;
  logic                rvld_q;

  wire cmp_now = has_b ? rt_b_q : rt_a_q;
  logic [LANES*32-1:0] lane_res;
  genvar gl;
  for (gl = 0; gl < LANES; gl++) begin : g_lane
    wire [31:0] a = has_b ? areg_q[gl*32 +: 32] : e_rdata[gl*32 +: 32];
    wire [31:0] b = has_b ? e_rdata[gl*32 +: 32] : scal_q;
    wire signed [MUL_W-1:0]   am = a[MUL_W-1:0];
    wire signed [MUL_W-1:0]   bm = b[MUL_W-1:0];
    wire signed [2*MUL_W-1:0] pr = am * bm;
    wire signed [31:0] as = a;
    wire signed [31:0] bs = b;
    wire [31:0] sra_v = as >>> b[4:0];
    logic [31:0] r;
    always_comb begin
      case (op_q)
        sfv_pkg::VOP_ADD: r = a + b;
        sfv_pkg::VOP_SUB: r = a - b;
        sfv_pkg::VOP_MIN: r = (as < bs) ? a : b;
        sfv_pkg::VOP_MAX: r = (as > bs) ? a : b;
        sfv_pkg::VOP_AND: r = a & b;
        sfv_pkg::VOP_OR:  r = a | b;
        sfv_pkg::VOP_XOR: r = a ^ b;
        sfv_pkg::VOP_SLL: r = a << b[4:0];
        sfv_pkg::VOP_SRA: r = sra_v;
        sfv_pkg::VOP_SRL: r = a >> b[4:0];
        default:          r = pr[31:0];          // MUL, DOT
      endcase
    end
    assign lane_res[gl*32 +: 32] = r;
  end

  logic [31:0] lane_sum;
  always_comb begin
    lane_sum = 32'd0;
    for (int l = 0; l < LANES; l++)
      if (rmask_q[l]) lane_sum = lane_sum + rreg_q[l*32 +: 32];
  end

  // TSPM port
  always_comb begin
    e_ce    = '0;
    e_we    = 1'b0;
    e_row   = '0;
    e_wdata = rreg_q;
    if (iss_a || iss_b) begin
      e_ce = '1;
      for (int l = 0; l < LANES; l++) e_row[l*RAW +: RAW] = iss_b ? row_b : row_a;
    end else if (iss_w) begin
      e_ce = rmask_q;
      e_we = 1'b1;
      for (int l = 0; l < LANES; l++) e_row[l*RAW +: RAW] = row_d;
    end else if (st == S_FWR) begin
      // DOT result: one word at dst
      for (int l = 0; l < LANES; l++) begin
        e_ce[l] = (dst_q[LW+1:2] == LW'(l));
        e_row[l*RAW +: RAW] = dst_q[RAW+LW+1:LW+2];
        e_wdata[l*32 +: 32] = res_q;
      end
      e_we = 1'b1;
    end
  end
  assign lock_req = (st != S_IDLE);
  assign busy     = (st != S_IDLE);

  // ------------------------------------------------------------ sequential
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      ien_q <= 1'b0; done_q <= 1'b0; err_q <= 1'b0; ecode_q <= '0;
      op_q <= '0; bsc_q <= 1'b0; accf_q <= 1'b0; wres_q <= 1'b0;
      sa_q <= '0; sb_q <= '0; dst_q <= '0; scal_q <= '0; res_q <= '0; cyc_q <= '0;
      len_q <= '0;
      st <= S_IDLE; nbeats <= '0; beat <= '0; slot <= '0;
      row_a <= '0; row_b <= '0; row_d <= '0;
      rt_a_q <= 1'b0; rt_b_q <= 1'b0; rt_mask_q <= '0;
      areg_q <= '0; rreg_q <= '0; rmask_q <= '0; rvld_q <= 1'b0;
    end else begin
      // ---------------- register writes
      if (wr) begin
        case (rb_addr)
          12'h000: ien_q <= rb_wdata[1];
          12'h004: begin
            if (rb_wdata[1]) done_q <= 1'b0;
            if (rb_wdata[2]) begin err_q <= 1'b0; ecode_q <= '0; end
          end
          12'h008: if (st == S_IDLE) begin
            op_q <= rb_wdata[3:0]; bsc_q <= rb_wdata[8]; accf_q <= rb_wdata[9]; wres_q <= rb_wdata[10];
          end
          12'h00C: if (st == S_IDLE) sa_q   <= rb_wdata;
          12'h010: if (st == S_IDLE) sb_q   <= rb_wdata;
          12'h014: if (st == S_IDLE) dst_q  <= rb_wdata;
          12'h018: if (st == S_IDLE) len_q  <= rb_wdata[15:0];
          12'h01C: if (st == S_IDLE) scal_q <= rb_wdata;
          12'h020: if (st == S_IDLE) res_q  <= rb_wdata;
          default: ;
        endcase
      end

      // ---------------- read-response pipeline
      rt_a_q    <= iss_a;
      rt_b_q    <= iss_b;
      rt_mask_q <= lmask(remain_i);
      rvld_q    <= 1'b0;
      if (rt_a_q && has_b) areg_q <= e_rdata;
      if (cmp_now) begin
        rreg_q  <= lane_res;
        rmask_q <= rt_mask_q;
        rvld_q  <= 1'b1;
      end
      if (rvld_q && is_dot) res_q <= res_q + lane_sum;

      // ---------------- control
      if (st != S_IDLE) cyc_q <= cyc_q + 32'd1;
      case (st)
        S_IDLE: if (start_wr) begin
          if (chk != sfv_pkg::AERR_NONE) begin
            err_q <= 1'b1; ecode_q <= chk;
          end else begin
            st     <= S_LOCK;
            done_q <= 1'b0;
            cyc_q  <= 32'd0;
            nbeats <= (len_q + 16'(LANES - 1)) >> LW;
            beat   <= '0;
            slot   <= '0;
            row_a  <= sa_q[RAW+LW+1:LW+2];
            row_b  <= sb_q[RAW+LW+1:LW+2];
            row_d  <= dst_q[RAW+LW+1:LW+2];
            if (is_dot && !accf_q) res_q <= 32'd0;
          end
        end
        S_LOCK: if (lock_gnt) st <= (len_q == 16'd0) ? S_FACC : S_PRO;
        S_PRO: begin
          row_a <= row_a + 1'b1;
          st    <= S_RUN;
        end
        S_RUN: begin
          if (iss_a) row_a <= row_a + 1'b1;
          if (iss_b) row_b <= row_b + 1'b1;
          if (iss_w) row_d <= row_d + 1'b1;
          if (last_slot) begin
            slot <= '0;
            beat <= beat + 16'd1;
            if (last_beat) st <= S_FACC;
          end else begin
            slot <= slot + 2'd1;
          end
        end
        S_FACC: st <= (is_dot && wres_q && len_q != 16'd0) ? S_FWR : S_IDLE;
        default: st <= S_IDLE;                    // S_FWR
      endcase
      if ((st == S_FACC && !(is_dot && wres_q && len_q != 16'd0)) || st == S_FWR) done_q <= 1'b1;
      if (start_wr && st != S_IDLE) begin err_q <= 1'b1; ecode_q <= sfv_pkg::AERR_BUSY; end
    end
  end

  assign irq = ien_q && (done_q || err_q);

  always_comb begin
    rb_rdata = 32'd0;
    rb_err   = 1'b0;
    case (rb_addr)
      12'h000: rb_rdata = {30'd0, ien_q, 1'b0};
      12'h004: rb_rdata = {24'd0, ecode_q, 1'b0, err_q, done_q, busy};
      12'h008: rb_rdata = {21'd0, wres_q, accf_q, bsc_q, 4'd0, op_q};
      12'h00C: rb_rdata = sa_q;
      12'h010: rb_rdata = sb_q;
      12'h014: rb_rdata = dst_q;
      12'h018: rb_rdata = {16'd0, len_q};
      12'h01C: rb_rdata = scal_q;
      12'h020: rb_rdata = res_q;
      12'h024: rb_rdata = cyc_q;
      12'h028: rb_rdata = {16'(TSPM_BYTES / 1024), 8'(MUL_W), 8'(LANES)};
      default: rb_err = 1'b1;
    endcase
  end
endmodule

`default_nettype wire
