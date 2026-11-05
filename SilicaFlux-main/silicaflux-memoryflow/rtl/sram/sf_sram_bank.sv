// =============================================================================
// SilicaFlux MemoryFlow :: sf_sram_bank
// One protected SRAM bank: logical SRAM + error protection + byte-enable
// handling + MBIST access port + error-injection hook.
//
// ECC_MODE
//   0 : none                  stored width = DW
//   1 : even parity per byte  stored width = DW/8 * 9   (detect only; byte
//                             writes are native -- each byte owns its parity)
//   2 : SECDED per word       stored width = DW + R + 1 (72 for DW=64)
//                             partial (sub-word) writes use read-modify-write:
//                             cycle t read, cycle t+1 correct/merge/encode/write
//                             (bank not ready during t+1).  If the RMW read is
//                             UNCORRECTABLE the write is suppressed so corrupt
//                             data is never re-encoded as "good".
//
// Timing: fixed 2-cycle response latency for reads and write acks
//         (SRAM read stage + decode/output register).  No response
//         backpressure: the parent (sf_spm_banked) reserves response space.
//
// MBIST: when bist_en=1 the functional port is blocked and the raw stored
//        word (including check bits) is accessed, so every bit-cell is tested.
// Error injection: while inj_en=1, every array write XORs inj_mask into the
//        stored word (RAS/DFT feature; used by ECC verification).
// Classification: SYNTHESIZABLE
// =============================================================================
`default_nettype none

module sf_sram_bank #(
  parameter int DW       = 64,
  parameter int DEPTH    = 1024,
  parameter int ECC_MODE = 2,
  parameter int TAGW     = 2,
  parameter int IMPL     = 0,
  parameter int MACRO_W  = 72,
  parameter int MACRO_D  = 512,
  parameter bit SA_EN    = 1'b0,
  parameter int SA_ADDR  = 0,
  parameter int SA_BIT   = 0,
  parameter bit SA_VAL   = 1'b0,
  localparam int NB      = DW / 8,
  localparam int R       = $clog2(DW + 1 + $clog2(DW + 1)),
  localparam int SW      = (ECC_MODE == 2) ? (DW + R + 1) :
                           (ECC_MODE == 1) ? (NB * 9) : DW,
  localparam int AW      = (DEPTH > 1) ? $clog2(DEPTH) : 1
) (
  input  logic            clk,
  input  logic            rst_n,
  // functional request
  input  logic            req_valid,
  output logic            req_ready,
  input  logic            req_we,
  input  logic [AW-1:0]   req_addr,     // word index inside the bank
  input  logic [DW-1:0]   req_wdata,
  input  logic [NB-1:0]   req_wstrb,
  input  logic [TAGW-1:0] req_tag,
  // response (fixed latency, always accepted)
  output logic            rsp_valid,
  output logic            rsp_we,
  output logic [DW-1:0]   rsp_rdata,
  output logic [TAGW-1:0] rsp_tag,
  output logic            rsp_corr,
  output logic            rsp_uncorr,
  // error injection
  input  logic            inj_en,
  input  logic [SW-1:0]   inj_mask,
  // MBIST raw access
  input  logic            bist_en,
  input  logic            bist_ce,
  input  logic            bist_we,
  input  logic [AW-1:0]   bist_addr,
  input  logic [SW-1:0]   bist_wdata,
  output logic [SW-1:0]   bist_rdata,
  // low-power hooks
  input  logic            lp_sleep,
  input  logic            lp_shutdown
);
  localparam int LANES  = (ECC_MODE == 2) ? 1 : NB;
  localparam int LANE_W = (ECC_MODE == 2) ? SW : ((ECC_MODE == 1) ? 9 : 8);

  // ---------------------------------------------------------------- encode
  logic [DW-1:0] enc_in;
  logic [SW-1:0] enc_out;

  generate
    if (ECC_MODE == 2) begin : g_enc_secded
      sf_ecc_secded_enc #(.K(DW)) u_enc (.data(enc_in), .code(enc_out));
    end else if (ECC_MODE == 1) begin : g_enc_par
      for (genvar b = 0; b < NB; b++) begin : g_b
        assign enc_out[b*9 +: 8] = enc_in[b*8 +: 8];
        assign enc_out[b*9 + 8]  = ^enc_in[b*8 +: 8];
      end
    end else begin : g_enc_none
      assign enc_out = enc_in;
    end
  endgenerate

  // ---------------------------------------------------------------- decode
  logic [SW-1:0] q;
  logic [DW-1:0] dec_data;
  logic          dec_corr, dec_uncorr;

  generate
    if (ECC_MODE == 2) begin : g_dec_secded
      logic [R-1:0] syn_unused;
      sf_ecc_secded_dec #(.K(DW)) u_dec (
        .code(q), .data(dec_data), .err_corr(dec_corr),
        .err_uncorr(dec_uncorr), .syndrome(syn_unused)
      );
    end else if (ECC_MODE == 1) begin : g_dec_par
      logic [NB-1:0] perr;
      for (genvar b = 0; b < NB; b++) begin : g_b
        assign dec_data[b*8 +: 8] = q[b*9 +: 8];
        assign perr[b]            = (^q[b*9 +: 8]) ^ q[b*9 + 8];
      end
      assign dec_uncorr = |perr;
      assign dec_corr   = 1'b0;
    end else begin : g_dec_none
      assign dec_data   = q;
      assign dec_corr   = 1'b0;
      assign dec_uncorr = 1'b0;
    end
  endgenerate

  // ---------------------------------------------------------------- control
  logic            s1_valid, s1_we, s1_rmw;
  logic [TAGW-1:0] s1_tag;
  logic [AW-1:0]   s1_addr;
  logic [DW-1:0]   s1_wdata;
  logic [NB-1:0]   s1_wstrb;

  wire full_word = &req_wstrb;
  wire need_rmw  = (ECC_MODE == 2) && req_we && !full_word;

  assign req_ready = !bist_en && !s1_rmw;
  wire   accept    = req_valid && req_ready;

  // merged RMW data (valid in the cycle after a partial write was accepted)
  logic [DW-1:0] merged;
  always_comb begin
    for (int b = 0; b < NB; b++)
      merged[b*8 +: 8] = s1_wstrb[b] ? s1_wdata[b*8 +: 8] : dec_data[b*8 +: 8];
  end

  // SRAM port mux
  logic             m_ce, m_we;
  logic [LANES-1:0] m_lane_we;
  logic [AW-1:0]    m_addr;
  logic [SW-1:0]    m_wdata;

  always_comb begin
    enc_in    = req_wdata;
    m_ce      = 1'b0;
    m_we      = 1'b0;
    m_lane_we = '0;
    m_addr    = req_addr;
    m_wdata   = '0;
    if (bist_en) begin
      m_ce      = bist_ce;
      m_we      = bist_we;
      m_lane_we = '1;
      m_addr    = bist_addr;
      m_wdata   = bist_wdata;
    end else if (s1_rmw) begin
      enc_in    = merged;
      m_ce      = !dec_uncorr;           // suppress write of corrupt word
      m_we      = 1'b1;
      m_lane_we = '1;
      m_addr    = s1_addr;
      m_wdata   = enc_out ^ (inj_en ? inj_mask : '0);
    end else if (accept) begin
      m_ce    = 1'b1;
      m_we    = req_we && !need_rmw;
      m_addr  = req_addr;
      m_wdata = enc_out ^ (inj_en ? inj_mask : '0);
      if (ECC_MODE == 2) m_lane_we = '1;
      else               m_lane_we = LANES'(req_wstrb);
    end
  end

  sf_sram_1rw #(
    .LANE_W(LANE_W), .LANES(LANES), .DEPTH(DEPTH),
    .IMPL(IMPL), .MACRO_W(MACRO_W), .MACRO_D(MACRO_D),
    .SA_EN(SA_EN), .SA_ADDR(SA_ADDR), .SA_BIT(SA_BIT), .SA_VAL(SA_VAL)
  ) u_sram (
    .clk, .ce(m_ce), .we(m_we), .lane_we(m_lane_we), .addr(m_addr),
    .wdata(m_wdata), .rdata(q), .lp_sleep, .lp_shutdown
  );

  assign bist_rdata = q;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      s1_valid  <= 1'b0;
      s1_rmw    <= 1'b0;
      rsp_valid <= 1'b0;
    end else begin
      s1_valid  <= accept;
      s1_rmw    <= accept && need_rmw;
      rsp_valid <= s1_valid;
    end
  end

  always_ff @(posedge clk) begin
    if (accept) begin
      s1_we    <= req_we;
      s1_tag   <= req_tag;
      s1_addr  <= req_addr;
      s1_wdata <= req_wdata;
      s1_wstrb <= req_wstrb;
    end
    if (s1_valid) begin
      rsp_we     <= s1_we;
      rsp_tag    <= s1_tag;
      rsp_rdata  <= s1_we ? '0 : dec_data;
      // reads report decode status; RMW writes report the merge-read status
      rsp_corr   <= (!s1_we || s1_rmw) ? dec_corr   : 1'b0;
      rsp_uncorr <= (!s1_we || s1_rmw) ? dec_uncorr : 1'b0;
    end
  end

endmodule

`default_nettype wire
