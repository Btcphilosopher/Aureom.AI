// =============================================================================
// SilicaFlux-V :: sfv_mbist -- March C- memory BIST controller
//
// Derived from the repository's memoryflow sf_mbist_march.sv (March C-,
// NBANKS identical banks tested in parallel, sticky per-bank fail mask, first
// failing address/element).  Changes for SilicaFlux-V:
//   * runtime address limit `last` so one controller serves bank groups of
//     different depth (main SRAM banks, tile scratchpad banks);
//   * data background selectable: solid (bg=0) or checkerboard per address
//     parity (bg=1), raising coverage of intra-word / row coupling faults.
//
// Algorithm (10N): M0 {w0}  M1 up{r0,w1}  M2 up{r1,w0}  M3 dn{r0,w1}
//                  M4 dn{r1,w0}  M5 {r0}
// Detects stuck-at, transition, address-decoder and unlinked coupling faults.
// Read latency 1: each read is compared in the following cycle.
// A production flow normally replaces this controller with the EDA vendor's
// MBIST (Tessent / SMS) at the same collar hook (sfv_sram_slave bist_*).
// =============================================================================
`default_nettype none

module sfv_mbist #(
  parameter int AW     = 13,
  parameter int NBANKS = 4
) (
  input  wire logic              clk,
  input  wire logic              rst_n,
  input  wire logic              start,
  input  wire logic              bg_chk,       // 0 solid, 1 checkerboard
  input  wire logic [AW-1:0]     last,         // highest word address
  output logic                   busy,
  output logic                   done,         // sticky until next start
  output logic                   fail,
  output logic [NBANKS-1:0]      fail_bank,
  output logic [AW-1:0]          fail_addr,
  output logic [2:0]             fail_elem,
  // to banks (broadcast)
  output logic                   bist_en,
  output logic                   bist_ce,
  output logic                   bist_we,
  output logic [AW-1:0]          bist_addr,
  output logic [31:0]            bist_wdata,
  input  wire logic [NBANKS*32-1:0] bist_rdata
);
  typedef enum logic [1:0] {IDLE, RUN, FIN} st_e;
  st_e         st;
  logic [2:0]  elem;
  logic [AW-1:0] addr, addr_q;
  logic        phase;          // 0: issue read, 1: compare (+ write)

  logic e_has_rd, e_has_wr, e_down, e_rd_val, e_wr_val;
  always_comb begin
    e_has_rd = 1'b1; e_has_wr = 1'b1; e_down = 1'b0; e_rd_val = 1'b0; e_wr_val = 1'b1;
    case (elem)
      3'd0: begin e_has_rd = 1'b0; e_wr_val = 1'b0; end
      3'd1: begin e_rd_val = 1'b0; e_wr_val = 1'b1; end
      3'd2: begin e_rd_val = 1'b1; e_wr_val = 1'b0; end
      3'd3: begin e_down = 1'b1; e_rd_val = 1'b0; e_wr_val = 1'b1; end
      3'd4: begin e_down = 1'b1; e_rd_val = 1'b1; e_wr_val = 1'b0; end
      default: begin e_has_wr = 1'b0; e_rd_val = 1'b0; end   // M5
    endcase
  end

  // background for an address: checkerboard flips on address parity
  wire        par    = bg_chk & ^addr;
  wire [31:0] bgw    = bg_chk ? 32'hAAAA_AAAA : 32'h0000_0000;
  wire [31:0] base   = par ? ~bgw : bgw;
  wire [31:0] d_rd   = e_rd_val ? ~base : base;
  wire [31:0] d_wr   = e_wr_val ? ~base : base;

  wire last_addr = e_down ? (addr == '0) : (addr == last);
  wire addr_step = (st == RUN) && (!e_has_rd || phase);

  always_comb begin
    bist_en    = (st == RUN);
    bist_ce    = 1'b0;
    bist_we    = 1'b0;
    bist_addr  = addr;
    bist_wdata = d_wr;
    if (st == RUN) begin
      if (e_has_rd && !phase) begin
        bist_ce = 1'b1;
      end else if (e_has_wr) begin
        bist_ce = 1'b1;
        bist_we = 1'b1;
      end
    end
  end

  logic [NBANKS-1:0] mism;
  always_comb begin
    for (int b = 0; b < NBANKS; b++)
      mism[b] = (st == RUN) && e_has_rd && phase && (bist_rdata[b*32 +: 32] != d_rd);
  end

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      st        <= IDLE;
      elem      <= '0;
      addr      <= '0;
      addr_q    <= '0;
      phase     <= 1'b0;
      done      <= 1'b0;
      fail      <= 1'b0;
      fail_bank <= '0;
      fail_addr <= '0;
      fail_elem <= '0;
    end else begin
      addr_q <= addr;
      case (st)
        IDLE: if (start) begin
          st        <= RUN;
          elem      <= 3'd0;
          addr      <= '0;
          phase     <= 1'b0;
          done      <= 1'b0;
          fail      <= 1'b0;
          fail_bank <= '0;
          fail_addr <= '0;
          fail_elem <= '0;
        end
        RUN: begin
          if (|mism) begin
            if (!fail) begin
              fail_addr <= addr;
              fail_elem <= elem;
            end
            fail      <= 1'b1;
            fail_bank <= fail_bank | mism;
          end
          phase <= e_has_rd && !phase;
          if (addr_step) begin
            if (last_addr) begin
              if (elem == 3'd5) begin
                st <= FIN;
              end else begin
                elem <= elem + 3'd1;
                addr <= ((elem + 3'd1) == 3'd3 || (elem + 3'd1) == 3'd4) ? last : '0;
              end
            end else begin
              addr <= e_down ? addr - 1'b1 : addr + 1'b1;
            end
          end
        end
        default: begin
          done <= 1'b1;
          st   <= IDLE;
        end
      endcase
    end
  end
  assign busy = (st != IDLE);
  wire unused_ok = ^addr_q;
endmodule

`default_nettype wire
