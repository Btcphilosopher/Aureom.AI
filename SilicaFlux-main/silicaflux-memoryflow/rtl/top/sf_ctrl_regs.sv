// =============================================================================
// SilicaFlux MemoryFlow :: sf_ctrl_regs
// APB3 system-control register block: accelerator configuration, performance
// counters, SPM RAS (ECC injection / counters), MBIST control, low power.
//
//   0x000 ID            RO 0x5346_4358 ("SFCX")
//   0x004 VEC_OP        RW [1:0]           0x008 VEC_ALPHA   RW [15:0]
//   0x00C TEN_K         RW [15:0]          0x010 REUSE_REPLAY RW [7:0]
//   0x014 PERF_CLEAR    W1 pulse           0x018 CYCLE       RO free-running
//   0x020 TEN_MAC  0x024 TEN_STALL_IN  0x028 TEN_STALL_ACC  0x02C TEN_TILES  (RO)
//   0x030 VEC_ACTIVE  0x034 VEC_STARVE  0x038 VEC_OSTALL                     (RO)
//   0x040 SPM_INJ_CTRL  RW [0] inj_en  [11:8] inj_bank
//   0x044/48/4C SPM_INJ_MASK0..2 RW (stored-word bit mask, LSB first)
//   0x050 SPM_CNT_CORR  0x054 SPM_CNT_UNCORR  0x058 SPM_CONFLICT  0x05C SPM_STALL
//   0x060 MBIST_CTRL    W  [0] START (pulse) [1] checkerboard background
//   0x064 MBIST_STATUS  RO [0] busy [1] done [2] fail [31:16] fail_bank
//   0x068 MBIST_FAIL_ADDR RO
//   0x06C LP_CTRL       RW [0] SPM light-sleep
// Classification: SYNTHESIZABLE
// =============================================================================
`default_nettype none

module sf_ctrl_regs #(
  parameter int SW     = 72,       // SPM stored word width (inject mask: low 96 bits)
  parameter int NBANKS = 4,
  parameter int IDXW   = 10,
  localparam int BKW   = (NBANKS > 1) ? $clog2(NBANKS) : 1
) (
  input  logic              clk,
  input  logic              rst_n,
  input  logic              psel,
  input  logic              penable,
  input  logic              pwrite,
  input  logic [11:0]       paddr,
  input  logic [31:0]       pwdata,
  output logic [31:0]       prdata,
  output logic              pready,
  output logic              pslverr,
  // accelerator config
  output logic [1:0]        vec_op,
  output logic [15:0]       vec_alpha,
  output logic [15:0]       ten_k,
  output logic [7:0]        reuse_replay,
  output logic              perf_clear,
  // perf inputs
  input  logic [31:0]       ten_mac, ten_stall_in, ten_stall_acc, ten_tiles,
  input  logic [31:0]       vec_active, vec_starve, vec_ostall,
  // SPM RAS
  output logic              inj_en,
  output logic [BKW-1:0]    inj_bank,
  output logic [SW-1:0]     inj_mask,
  input  logic [15:0]       spm_cnt_corr, spm_cnt_uncorr,
  input  logic [31:0]       spm_conflict, spm_stall,
  // MBIST
  output logic              mbist_start,
  output logic [SW-1:0]     mbist_bg,
  input  logic              mbist_busy, mbist_done, mbist_fail,
  input  logic [NBANKS-1:0] mbist_fail_bank,
  input  logic [IDXW-1:0]   mbist_fail_addr,
  // low power
  output logic              lp_sleep
);
  logic [95:0] mask_q;
  logic [31:0] cycle;
  logic        bg_chk;
  logic [3:0]  inj_bank_q;

  wire wr = psel && penable && pwrite;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      vec_op       <= '0;
      vec_alpha    <= 16'd1;
      ten_k        <= 16'd8;
      reuse_replay <= 8'd1;
      perf_clear   <= 1'b0;
      inj_en       <= 1'b0;
      inj_bank_q   <= '0;
      mask_q       <= '0;
      mbist_start  <= 1'b0;
      bg_chk       <= 1'b0;
      lp_sleep     <= 1'b0;
      cycle        <= '0;
    end else begin
      cycle       <= cycle + 32'd1;
      perf_clear  <= wr && (paddr == 12'h014) && pwdata[0];
      mbist_start <= wr && (paddr == 12'h060) && pwdata[0];
      if (wr) begin
        case (paddr)
          12'h004: vec_op       <= pwdata[1:0];
          12'h008: vec_alpha    <= pwdata[15:0];
          12'h00C: ten_k        <= pwdata[15:0];
          12'h010: reuse_replay <= pwdata[7:0];
          12'h040: begin inj_en <= pwdata[0]; inj_bank_q <= pwdata[11:8]; end
          12'h044: mask_q[31:0]  <= pwdata;
          12'h048: mask_q[63:32] <= pwdata;
          12'h04C: mask_q[95:64] <= pwdata;
          12'h060: bg_chk       <= pwdata[1];
          12'h06C: lp_sleep     <= pwdata[0];
          default: ;
        endcase
      end
    end
  end

  assign inj_bank = BKW'(inj_bank_q);
  // injection mask covers stored-word bits [95:0]; wider words (DW=128 SECDED
  // = 137 bits) zero-extend, which still reaches every data bit < 96, the
  // check bits are reachable through the MBIST raw port.
  generate
    if (SW <= 96) begin : g_mask_narrow
      assign inj_mask = mask_q[SW-1:0];
    end else begin : g_mask_wide
      assign inj_mask = {{(SW-96){1'b0}}, mask_q};
    end
  endgenerate
  always_comb begin
    for (int b = 0; b < SW; b++) mbist_bg[b] = bg_chk ? b[0] : 1'b0;
  end

  assign pready  = 1'b1;
  assign pslverr = 1'b0;

  always_comb begin
    prdata = 32'd0;
    case (paddr)
      12'h000: prdata = 32'h5346_4358;
      12'h004: prdata = {30'd0, vec_op};
      12'h008: prdata = {16'd0, vec_alpha};
      12'h00C: prdata = {16'd0, ten_k};
      12'h010: prdata = {24'd0, reuse_replay};
      12'h018: prdata = cycle;
      12'h020: prdata = ten_mac;
      12'h024: prdata = ten_stall_in;
      12'h028: prdata = ten_stall_acc;
      12'h02C: prdata = ten_tiles;
      12'h030: prdata = vec_active;
      12'h034: prdata = vec_starve;
      12'h038: prdata = vec_ostall;
      12'h040: prdata = {20'd0, inj_bank_q, 7'd0, inj_en};
      12'h044: prdata = mask_q[31:0];
      12'h048: prdata = mask_q[63:32];
      12'h04C: prdata = mask_q[95:64];
      12'h050: prdata = {16'd0, spm_cnt_corr};
      12'h054: prdata = {16'd0, spm_cnt_uncorr};
      12'h058: prdata = spm_conflict;
      12'h05C: prdata = spm_stall;
      12'h060: prdata = {30'd0, bg_chk, 1'b0};
      12'h064: prdata = {16'(mbist_fail_bank), 13'd0, mbist_fail, mbist_done, mbist_busy};
      12'h068: prdata = 32'(mbist_fail_addr);
      12'h06C: prdata = {31'd0, lp_sleep};
      default: prdata = 32'd0;
    endcase
  end

endmodule

`default_nettype wire
