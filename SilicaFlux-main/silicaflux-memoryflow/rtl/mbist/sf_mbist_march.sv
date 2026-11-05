// =============================================================================
// SilicaFlux MemoryFlow :: sf_mbist_march
// March C- memory BIST controller driving NBANKS identical banks in parallel
// through their raw (check-bit inclusive) BIST ports.
//
//   M0: up/down (w0)      M1: up (r0,w1)     M2: up (r1,w0)
//   M3: down (r0,w1)      M4: down (r1,w0)   M5: up/down (r0)
//   10N operations -> detects SAF, TF, CFin, CFid, unlinked CFst, AF.
//
// "0" = data background `bg`, "1" = ~bg (run with bg = 0 and a checkerboard to
// raise coverage of intra-word coupling).  Read latency of the array is one
// cycle, so every read is compared in the following cycle.
// Results: sticky per-bank fail mask, first failing address and element.
// This is the MemoryFlow reference controller; a production flow normally
// swaps in the EDA vendor's MBIST (Tessent/Synopsys SMS) at the same bist_*
// hook in sf_sram_bank -- the hook, not this controller, is the contract.
// Classification: SYNTHESIZABLE
// =============================================================================
`default_nettype none

module sf_mbist_march #(
  parameter int SW     = 72,
  parameter int DEPTH  = 1024,
  parameter int NBANKS = 4,
  localparam int AW    = (DEPTH > 1) ? $clog2(DEPTH) : 1
) (
  input  logic               clk,
  input  logic               rst_n,
  input  logic               start,
  input  logic [SW-1:0]      bg,
  output logic               busy,
  output logic               done,
  output logic               fail,
  output logic [NBANKS-1:0]  fail_bank,
  output logic [AW-1:0]      fail_addr,
  output logic [2:0]         fail_elem,
  // to banks (broadcast)
  output logic               bist_en,
  output logic               bist_ce,
  output logic               bist_we,
  output logic [AW-1:0]      bist_addr,
  output logic [SW-1:0]      bist_wdata,
  input  logic [NBANKS*SW-1:0] bist_rdata
);
  typedef enum logic [1:0] {IDLE, RUN, FIN} st_t;
  st_t          st;
  logic [2:0]   elem;
  logic [AW-1:0] addr;
  logic         phase;           // 0: read/issue, 1: compare(+write)

  // element properties
  logic        e_has_rd, e_has_wr, e_down, e_rd_val, e_wr_val;
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

  wire [SW-1:0] d_rd = e_rd_val ? ~bg : bg;
  wire [SW-1:0] d_wr = e_wr_val ? ~bg : bg;

  wire last_addr = e_down ? (addr == '0) : (addr == AW'(DEPTH - 1));
  // one address finished this cycle?
  wire addr_step = (st == RUN) && (!e_has_rd || phase);

  // drive array
  always_comb begin
    bist_en    = (st == RUN);
    bist_ce    = 1'b0;
    bist_we    = 1'b0;
    bist_addr  = addr;
    bist_wdata = d_wr;
    if (st == RUN) begin
      if (e_has_rd && !phase) begin
        bist_ce = 1'b1;               // issue read
      end else if (e_has_wr) begin
        bist_ce = 1'b1;               // write (after compare, or write-only)
        bist_we = 1'b1;
      end
    end
  end

  // compare
  logic [NBANKS-1:0] mism;
  always_comb begin
    for (int b = 0; b < NBANKS; b++)
      mism[b] = (st == RUN) && e_has_rd && phase && (bist_rdata[b*SW +: SW] != d_rd);
  end

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      st        <= IDLE;
      elem      <= '0;
      addr      <= '0;
      phase     <= 1'b0;
      done      <= 1'b0;
      fail      <= 1'b0;
      fail_bank <= '0;
      fail_addr <= '0;
      fail_elem <= '0;
    end else begin
      case (st)
        IDLE: if (start) begin
          st        <= RUN;
          elem      <= 3'd0;
          addr      <= '0;
          phase     <= 1'b0;
          done      <= 1'b0;
          fail      <= 1'b0;
          fail_bank <= '0;
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
          if (e_has_rd && !phase) begin
            phase <= 1'b1;
          end else begin
            phase <= 1'b0;
          end
          if (addr_step) begin
            if (last_addr) begin
              if (elem == 3'd5) begin
                st <= FIN;
              end else begin
                elem <= elem + 3'd1;
                // next element direction: M3, M4 run downwards
                addr <= ((elem + 3'd1) == 3'd3 || (elem + 3'd1) == 3'd4) ? AW'(DEPTH - 1) : '0;
              end
            end else begin
              addr <= e_down ? addr - AW'(1) : addr + AW'(1);
            end
          end
        end
        default: begin // FIN
          done <= 1'b1;
          st   <= IDLE;
        end
      endcase
    end
  end

  assign busy = (st != IDLE);

endmodule

`default_nettype wire
